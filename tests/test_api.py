"""API integration tests — full ASGI app with SUMO subprocesses mocked out."""

import asyncio

import pytest

from .conftest import post_job, wait_for_status

# ── Happy path ────────────────────────────────────────────────


async def test_job_lifecycle_end_to_end(client, mock_subprocess):
    r = await post_job(
        client,
        config={
            "random_trips": {"end": 100.0},
            "sumo": {"end": 90.0, "fcd_output_period": 1.0},
            "trace_exporter": {"sampling_period": 1.0},
        },
    )
    assert r.status_code == 202, r.text
    job_id = r.json()["job_id"]
    assert r.json()["config_snapshot"]["sumo"]["end"] == 90.0

    final = await wait_for_status(client, job_id, {"done", "failed"})
    assert final["status"] == "done", final.get("error")
    assert all(s == "done" for s in final["stages"].values())
    assert final["completed_at"] is not None

    # All five pipeline stages actually invoked the subprocess layer…
    assert len(mock_subprocess.calls) == 6  # 4 stages + 2 exporters (both formats)


async def test_outputs_listed_and_downloadable(client, mock_subprocess):
    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})

    files = (await client.get(f"/jobs/{job_id}/files")).json()["files"]
    names = {f["filename"] for f in files}
    assert {"ns_movements", "mobility.tcl"}.issubset(names)
    assert {"tripinfo.xml", "summary.xml"}.issubset(names)

    dl = await client.get(f"/jobs/{job_id}/download/ns_movements")
    assert dl.status_code == 200
    assert dl.content  # the mock wrote bytes


async def test_ns_movements_only_format(client, mock_subprocess):
    r = await post_job(client, {"trace_exporter": {"output_format": "ns_movements"}})
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    names = {
        f["filename"]
        for f in (await client.get(f"/jobs/{job_id}/files")).json()["files"]
    }
    assert "ns_movements" in names
    assert "mobility.tcl" not in names


# ── Validation / upload guards ───────────────────────────────


async def test_bad_config_json_422(client):
    r = await client.post(
        "/jobs",
        files={"osm_file": ("map.osm", b"<osm/>", "application/octet-stream")},
        data={"config": "{not json"},
    )
    assert r.status_code == 422


async def test_invalid_config_values_422(client):
    r = await post_job(
        client, config={"sumo": {"end": 5000.0}}
    )  # > random_trips.end=3600
    assert r.status_code == 422
    assert "sumo.end" in r.json()["detail"]


async def test_bad_suffix_400(client):
    r = await post_job(client, filename="notes.txt")
    assert r.status_code == 400


async def test_missing_filename_rejected(client):
    # An empty filename is rejected before any job is created — FastAPI's own
    # multipart validation (422) or the handler's explicit guard (400).
    r = await client.post(
        "/jobs",
        files={"osm_file": ("", b"<osm/>", "application/octet-stream")},
        data={"config": "{}"},
    )
    assert r.status_code in (400, 422)


async def test_upload_size_limit_413(settings):
    """An app with a tiny cap rejects a bigger upload and leaves no junk."""
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from main import create_app

    settings.max_upload_mb = 0  # 0 MB → any content trips the cap
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            r = await post_job(c, content=b"x" * 1024 * 1024 + b"x")
            assert r.status_code == 413
            assert "limit" in r.json()["detail"].lower()
            # No partial upload left behind.
            leftovers = list(settings.upload_dir.iterdir())
            assert leftovers == []


# ── Cancellation + deletion ───────────────────────────────────


async def test_cancel_running_job(client):
    from .conftest import SubprocessMock

    # Slow pipeline keeps the job in-flight until we cancel.
    app = client._transport.app
    app.state.runner._run_async = SubprocessMock(mode="slow")

    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"running"})

    c = await client.post(f"/jobs/{job_id}/cancel")
    assert c.status_code == 202, c.text
    final = c.json()
    assert final["status"] == "cancelled"
    assert final["stages"]["netconvert"] == "cancelled"
    assert final["completed_at"] is not None

    # And it stays cancelled after the task unwinds.
    done = await wait_for_status(client, job_id, {"cancelled"})
    assert done["error"] == "Cancelled by user"

    # Cancelled jobs can be deleted.
    d = await client.delete(f"/jobs/{job_id}")
    assert d.status_code == 204
    gone = await client.get(f"/jobs/{job_id}")
    assert gone.status_code == 404


async def test_cancel_unknown_and_finished(client, mock_subprocess):
    r = await client.post("/jobs/does-not-exist/cancel")
    assert r.status_code == 404

    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    c = await client.post(f"/jobs/{job_id}/cancel")
    assert c.status_code == 409


async def test_delete_running_job_409(client):
    from .conftest import SubprocessMock

    LongRunner = SubprocessMock(mode="slow")
    client._transport.app.state.runner._run_async = LongRunner
    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"running"})
    d = await client.delete(f"/jobs/{job_id}")
    assert d.status_code == 409
    # Cleanup: cancel so the lingering task unwinds.
    await client.post(f"/jobs/{job_id}/cancel")


async def test_delete_done_job_removes_files(client, mock_subprocess, settings):
    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    assert (settings.out_dir / job_id).exists()

    d = await client.delete(f"/jobs/{job_id}")
    assert d.status_code == 204
    assert not (settings.out_dir / job_id).exists()
    assert list(settings.upload_dir.glob(f"{job_id}*")) == []


# ── Misc endpoints ────────────────────────────────────────────


async def test_list_jobs_most_recent_first(client, mock_subprocess):
    ids = []
    for _ in range(3):
        ids.append((await post_job(client)).json()["job_id"])
        await asyncio.sleep(0.01)
    listing = (await client.get("/jobs")).json()
    listed = [j["job_id"] for j in listing]
    assert listed[:3] == list(reversed(ids))
    for i in ids:
        await wait_for_status(client, i, {"done"})


async def test_get_unknown_job_404(client):
    assert (await client.get("/jobs/nope")).status_code == 404
    assert (await client.get("/jobs/nope/files")).status_code == 404
    assert (await client.get("/jobs/nope/logs")).status_code == 404
    assert (await client.get("/jobs/nope/config")).status_code == 404


async def test_download_path_traversal_400(client, mock_subprocess):
    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    r = await client.get(f"/jobs/{job_id}/download/..%2F..%2Fetc%2Fpasswd")
    assert r.status_code in (400, 404)  # never a 200 with file bytes


async def test_logs_endpoint_shape(client, mock_subprocess):
    r = await post_job(client)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    body = (await client.get(f"/jobs/{job_id}/logs")).json()
    assert set(body["stage_logs"]) == {
        "netconvert",
        "duarouter",
        "sumo",
        "traceExporter",
    }
    assert isinstance(body["warnings"], list)


async def test_config_roundtrip(client, mock_subprocess):
    cfg = {"random_trips": {"seed": 99, "end": 120.0}, "sumo": {"end": 100.0}}
    r = await post_job(client, config=cfg)
    job_id = r.json()["job_id"]
    await wait_for_status(client, job_id, {"done"})
    got = (await client.get(f"/jobs/{job_id}/config")).json()
    assert got["random_trips"]["seed"] == 99
    assert got["sumo"]["end"] == 100.0
    assert got["trace_exporter"]["output_format"] == "both"  # defaults filled


async def test_schema_and_defaults(client):
    schema = (await client.get("/schema")).json()
    assert "$defs" in schema and "NetconvertParams" in schema["$defs"]
    defaults = (await client.get("/defaults")).json()
    assert defaults["random_trips"]["end"] == 3600.0


async def test_system_endpoints(client):
    assert (await client.get("/live")).json() == {"status": "ok"}
    # no_sumo fixture pretends tools exist → ready 200
    ready = await client.get("/ready")
    assert ready.status_code == 200
    assert ready.json()["status"] == "ready"
    assert ready.json()["tools_available"] is True
    health = (await client.get("/health")).json()
    assert health["status"] == "ready"
    assert set(health["tools"]) == {
        "netconvert",
        "duarouter",
        "sumo",
        "traceExporter.py",
        "randomTrips.py",
    }


async def test_ready_503_when_tools_missing(settings, monkeypatch):
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from main import create_app

    def missing_tools(sumo_home: str = ""):
        return {
            "netconvert": False,
            "duarouter": True,
            "sumo": True,
            "traceExporter.py": True,
            "randomTrips.py": True,
        }

    monkeypatch.setattr("main.check_tools", missing_tools)
    app = create_app(settings)
    async with LifespanManager(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://t"
        ) as c:
            r = await c.get("/ready")
            assert r.status_code == 503
            assert r.json()["status"] == "not_ready"
            assert r.json()["tools"]["netconvert"] is False


# ── Auth ──────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "method,path",
    [
        ("GET", "/jobs"),
        ("POST", "/jobs"),
        ("GET", "/jobs/some-id"),
        ("GET", "/jobs/some-id/files"),
        ("GET", "/jobs/some-id/logs"),
        ("GET", "/jobs/some-id/config"),
        ("DELETE", "/jobs/some-id"),
        ("POST", "/jobs/some-id/cancel"),
        ("GET", "/jobs/some-id/download/x"),
    ],
)
async def test_jobs_routes_require_key_when_enabled(authed_client, method, path):
    r = await authed_client.request(method, path)
    assert r.status_code == 401
    r = await authed_client.request(method, path, headers={"X-API-Key": "wrong"})
    assert r.status_code == 401


async def test_auth_accepts_correct_key(authed_client):
    r = await authed_client.get("/jobs", headers={"X-API-Key": "test-secret"})
    assert r.status_code == 200


async def test_public_endpoints_open_with_auth_enabled(authed_client):
    for path in ("/live", "/ready", "/health", "/schema", "/defaults", "/docs"):
        r = await authed_client.get(path)
        assert r.status_code != 401, path


async def test_auth_disabled_by_default(client):
    assert (await client.get("/jobs")).status_code == 200


# ── Persistence across restarts ───────────────────────────────


async def test_jobs_survive_restart(settings):
    """A completed job is still listed after a 'restart' (new app + lifespan
    over the same data dir)."""
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from main import create_app

    from .conftest import SubprocessMock

    ok = SubprocessMock(mode="ok")

    app1 = create_app(settings)
    async with LifespanManager(app1):
        app1.state.runner._run_async = ok
        async with AsyncClient(
            transport=ASGITransport(app=app1), base_url="http://t"
        ) as c:
            job_id = (await post_job(c)).json()["job_id"]
            await wait_for_status(c, job_id, {"done"})

    app2 = create_app(settings)  # same data_dir = same jobs.db
    async with LifespanManager(app2):
        async with AsyncClient(
            transport=ASGITransport(app=app2), base_url="http://t"
        ) as c:
            r = await c.get(f"/jobs/{job_id}")
            assert r.status_code == 200
            assert r.json()["status"] == "done"


async def test_interrupted_running_job_fails_on_restart(settings):
    """A row stuck at "running" from a dead process is failed at startup.

    Exactly what a crashed server leaves behind: the DB keeps the last-write
    state and no API call ever marks it otherwise."""
    from asgi_lifespan import LifespanManager
    from httpx import ASGITransport, AsyncClient

    from app.models import JobStatus, StageStatus
    from app.store import JobStore
    from main import create_app

    seed_store = JobStore(settings.db_path)
    await seed_store.init()
    stuck = JobStatus(
        job_id="stuck-job",
        status=StageStatus.running,
        stages={
            "netconvert": StageStatus.done,
            "random_trips": StageStatus.done,
            "duarouter": StageStatus.done,
            "sumo": StageStatus.running,
            "trace_export": StageStatus.pending,
        },
        created_at="2026-08-26T00:00:00+00:00",
    )
    await seed_store.create(stuck, "{}")

    app2 = create_app(settings)
    async with LifespanManager(app2):
        async with AsyncClient(
            transport=ASGITransport(app=app2), base_url="http://t"
        ) as c:
            r = await c.get("/jobs/stuck-job")
            assert r.status_code == 200
            body = r.json()
            assert body["status"] == "failed"
            assert "Interrupted by server restart" in body["error"]
            assert body["stages"]["sumo"] == "failed"
