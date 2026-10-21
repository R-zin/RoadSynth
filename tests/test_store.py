"""Unit tests for the SQLite JobStore: round-trips, recovery, retention."""

import asyncio
from datetime import datetime, timedelta, timezone

from app.models import JobStatus, StageStatus


def make_job(job_id: str, status: StageStatus = StageStatus.pending) -> JobStatus:
    return JobStatus(
        job_id=job_id,
        status=status,
        stages={
            "netconvert": StageStatus.pending,
            "random_trips": StageStatus.pending,
            "duarouter": StageStatus.pending,
            "sumo": StageStatus.pending,
            "trace_export": StageStatus.pending,
        },
        stage_logs={},
        created_at=datetime.now(timezone.utc).isoformat(),
    )


async def test_create_get_roundtrip(store):
    job = make_job("j1")
    job.warnings = ["w1", "w2"]
    job.outputs = ["/outputs/j1/ns_movements"]
    job.current_stage = "sumo"
    job.stages["netconvert"] = StageStatus.done
    job.stage_logs["netconvert"] = {
        "status": "done",
        "stdout": "out",
        "stderr": None,
        "duration": 1.2,
    }
    await store.init()
    await store.create(job, '{"sumo": {"seed": 7}}')

    got = await store.get("j1")
    assert got is not None
    assert got.model_dump() == job.model_dump()

    cfg = await store.get_config("j1")
    assert cfg == {"sumo": {"seed": 7}}


async def test_unknown_job(store):
    await store.init()
    assert await store.get("nope") is None
    assert await store.get_config("nope") is None


async def test_upsert_and_list(store):
    await store.init()
    job = make_job("j2")
    await store.create(job, None)
    job.status = StageStatus.done
    job.completed_at = datetime.now(timezone.utc).isoformat()
    await store.upsert(job)

    jobs = await store.list()
    assert [j.job_id for j in jobs] == ["j2"]
    assert jobs[0].status == StageStatus.done
    assert jobs[0].completed_at is not None


async def test_delete(store):
    await store.init()
    await store.create(make_job("j3"), None)
    await store.delete("j3")
    assert await store.get("j3") is None


async def test_startup_recovery_fails_interrupted_jobs(store):
    """pending/running rows from a previous process become failed."""
    await store.init()
    running = make_job("j-run", status=StageStatus.running)
    running.stages["netconvert"] = StageStatus.done
    running.stages["sumo"] = StageStatus.running
    waiting = make_job("j-wait", status=StageStatus.pending)
    finished = make_job("j-done", status=StageStatus.done)
    running.completed_at = None
    for j in (running, waiting, finished):
        await store.create(j, None)

    # Simulate the next process booting over the same DB file.
    recovered = await store._recover_interrupted()
    assert set(recovered) == {"j-run", "j-wait"}

    j = await store.get("j-run")
    assert j.status == StageStatus.failed
    assert j.error == "Interrupted by server restart"
    assert j.completed_at is not None
    assert j.stages["sumo"] == StageStatus.failed
    assert j.stages["netconvert"] == StageStatus.done  # untouched

    assert (await store.get("j-done")).status == StageStatus.done


async def test_prune_by_age(store):
    store._retention_days = 1
    await store.init()
    old = make_job("j-old", status=StageStatus.done)
    old.completed_at = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
    fresh = make_job("j-fresh", status=StageStatus.done)
    fresh.completed_at = datetime.now(timezone.utc).isoformat()
    active = make_job("j-active", status=StageStatus.running)
    for j in (old, fresh, active):
        await store.create(j, None)

    pruned = await store.prune()
    assert pruned == ["j-old"]
    assert await store.get("j-old") is None
    assert await store.get("j-fresh") is not None
    assert await store.get("j-active") is not None


async def test_prune_by_count(store):
    await store.init()
    now = datetime.now(timezone.utc)
    for i in range(5):
        j = make_job(f"j-{i}", status=StageStatus.done)
        j.completed_at = (now + timedelta(seconds=i)).isoformat()
        await store.create(j, None)

    store._retention_max = 2  # keep only the 2 newest finished jobs
    pruned = await store.prune()
    remaining = {j.job_id for j in await store.list()}
    assert remaining == {"j-4", "j-3"}
    assert set(pruned) == {"j-0", "j-1", "j-2"}


async def test_concurrent_upserts(store):
    await store.init()
    jobs = [make_job(f"cc-{i}") for i in range(10)]
    for j in jobs:
        await store.create(j, None)

    async def bump(j):
        j.status = StageStatus.done
        j.warnings.append("x")
        await store.upsert(j)

    await asyncio.gather(*[bump(j) for j in jobs])
    listed = await store.list()
    assert len(listed) == 10
    assert all(j.status == StageStatus.done for j in listed)
    assert all(j.warnings == ["x"] for j in listed)
