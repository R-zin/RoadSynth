"""Shared fixtures: no SUMO tools on the test runner — every fixture that
touches the toolchain mocks the lookup and/or the subprocess layer."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

import app.worker as worker_mod
from app.settings import Settings
from app.store import JobStore
from app.worker import PipelineRunner
from main import create_app

OSM_BYTES = b"""<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="test">
  <node id="1" lat="52.0" lon="13.0"/>
</osm>
"""


@pytest.fixture()
def settings(tmp_path) -> Settings:
    """Per-test settings rooted at a tmp dir (bypasses get_settings cache)."""
    return Settings(
        data_dir=tmp_path,
        static_dir=tmp_path / "static-absent",
        api_key=None,
        max_upload_mb=1,
        job_retention_max=200,
        job_retention_days=7,
        timeout_default_s=5.0,
        timeout_sumo_s=5.0,
        timeout_trace_export_s=5.0,
        max_concurrent_jobs=4,
    )


@pytest.fixture(autouse=True)
def no_sumo(monkeypatch):
    """Pretend every SUMO binary/script exists at a fixed (mock) path."""
    monkeypatch.setattr(
        worker_mod, "_find_binary", lambda names: f"/mock/bin/{names[0]}"
    )
    monkeypatch.setattr(
        worker_mod,
        "_find_sumo_script",
        lambda filename, sumo_home="": f"/mock/tools/{filename}",
    )


class SubprocessMock:
    """Replaces PipelineRunner._run_async; records every invocation.

    mode: "ok" (rc=0), "fail" (rc=1), "slow" (sleeps until cancelled).
    on_stage: optional callback receiving (job_id, cmd) per invocation.
    """

    def __init__(self, mode: str = "ok", on_stage=None):
        self.mode = mode
        self.calls = []
        self.on_stage = on_stage

    async def __call__(self, job_id, cmd, workdir, timeout):
        self.calls.append({"job_id": job_id, "cmd": list(cmd), "timeout": timeout})
        if self.on_stage:
            self.on_stage(job_id, cmd)
        if self.mode == "slow":
            await asyncio.sleep(3600)
            raise AssertionError("unreachable: slow mock must be cancelled")
        if self.mode == "fail":
            return 1, "", "mock failure"
        # Successful stages must materialise files the pipeline copies.
        if "--ns2-output" in cmd:
            out = Path(cmd[cmd.index("--ns2-output") + 1])
            out.write_text("mock trace")
        Path(workdir / "fcd-output.xml").write_text("<fcd/>")
        Path(workdir / "tripinfo.xml").write_text("<tripinfo/>")
        Path(workdir / "summary.xml").write_text("<summary/>")
        return 0, "ok", ""


@pytest.fixture()
def mock_subprocess(monkeypatch) -> SubprocessMock:
    mock = SubprocessMock(mode="ok")
    monkeypatch.setattr(PipelineRunner, "_run_async", mock)
    return mock


@pytest.fixture()
def store(settings) -> JobStore:
    return JobStore(
        settings.db_path,
        retention_max=settings.job_retention_max,
        retention_days=settings.job_retention_days,
    )


@pytest.fixture()
def runner(settings, store) -> PipelineRunner:
    return PipelineRunner(settings, store)


@pytest.fixture()
async def app(settings):
    application = create_app(settings)
    async with LifespanManager(application):
        yield application


@pytest.fixture()
async def client(app):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as c:
        yield c


@pytest.fixture()
def authed_settings(tmp_path) -> Settings:
    """Separate app with API-key auth enabled (init kwargs, not mutation —
    pydantic-settings resolves every field at construction)."""
    return Settings(
        data_dir=tmp_path,
        static_dir=tmp_path / "static-absent",
        api_key="test-secret",
        max_upload_mb=1,
    )


@pytest.fixture()
async def authed_client(authed_settings):
    application = create_app(authed_settings)
    async with LifespanManager(application):
        async with AsyncClient(
            transport=ASGITransport(app=application), base_url="http://test"
        ) as c:
            yield c


async def wait_for_status(client, job_id: str, want: set[str], timeout: float = 5.0):
    """Poll GET /jobs/{id} until status ∈ want; returns final payload."""
    deadline = asyncio.get_event_loop().time() + timeout
    while True:
        r = await client.get(f"/jobs/{job_id}")
        r.raise_for_status()
        data = r.json()
        if data["status"] in want:
            return data
        if asyncio.get_event_loop().time() > deadline:
            raise AssertionError(
                f"job {job_id} stuck at {data['status']!r}, wanted {want}"
            )
        await asyncio.sleep(0.02)


async def post_job(
    client,
    config: dict | None = None,
    filename="map.osm",
    content: bytes = OSM_BYTES,
    headers: dict | None = None,
):
    files = {"osm_file": (filename, content, "application/octet-stream")}
    data = {"config": json.dumps(config or {})}
    return await client.post("/jobs", files=files, data=data, headers=headers or {})
