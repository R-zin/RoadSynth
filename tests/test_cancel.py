"""Focused tests for the cancellation machinery in PipelineRunner."""

import asyncio
import signal

from app.models import ConversionRequest, StageStatus

from .conftest import OSM_BYTES, SubprocessMock


async def _launch(runner, tmp_path, config=None):
    upload = tmp_path / "upload.osm"
    upload.write_bytes(OSM_BYTES)
    job = await runner.create_and_launch(upload, config or ConversionRequest())
    return job


async def test_cancel_kills_subprocess_group(runner, store, monkeypatch, tmp_path):
    """cancel() must kill the whole process group before task.cancel()."""
    killed_pids = []

    def spy_killpg(pid, sig):
        killed_pids.append((pid, sig))

    monkeypatch.setattr("app.worker.os.killpg", spy_killpg)

    # Slow mock: the pipeline never finishes a stage on its own, so the job
    # stays pending/running through the cancel — deterministic regardless of
    # how the event loop schedules the freshly-launched background task.
    runner._run_async = SubprocessMock(mode="slow")

    class FakeProc:
        def __init__(self):
            self.pid = 4242
            self.returncode = 0

    fake = FakeProc()
    fake.returncode = None  # still running

    await store.init()
    job = await _launch(runner, tmp_path)
    await store.get(job.job_id)  # row materialised
    runner._procs.setdefault(job.job_id, set()).add(fake)

    result = await runner.cancel(job.job_id)
    assert result == "cancelled"
    assert killed_pids == [(4242, signal.SIGKILL)]

    job = await store.get(job.job_id)
    assert job.status == StageStatus.cancelled
    assert job.error == "Cancelled by user"

    # Task unwinds and registries are cleaned.
    await asyncio.sleep(0.05)
    assert job.job_id not in runner._tasks
    assert job.job_id not in runner._procs


async def test_cancel_queued_pending_job(runner, store, tmp_path):
    """A job waiting on the concurrency semaphore can be cancelled."""
    runner._semaphore = asyncio.Semaphore(0)  # never grants a slot

    # Prevent the pipeline from touching the fake workdir deeply: the slow
    # mock never runs because the semaphore blocks first.
    runner._run_async = SubprocessMock(mode="slow")

    await store.init()
    job = await _launch(runner, tmp_path)
    # Give _guarded_run a chance to reach the semaphore.
    for _ in range(50):
        persisted = await store.get(job.job_id)
        if persisted.status != StageStatus.cancelled:
            break
        await asyncio.sleep(0.01)

    assert (await runner.cancel(job.job_id)) == "cancelled"
    job = await store.get(job.job_id)
    assert job.status == StageStatus.cancelled
    assert all(s == StageStatus.pending for s in job.stages.values())


async def test_cancel_unknown_and_finished(runner, store, mock_subprocess, tmp_path):
    await store.init()
    try:
        await runner.cancel("ghost")
        assert False, "expected LookupError"
    except LookupError:
        pass

    job = await _launch(runner, tmp_path)
    # Let the fully-mocked pipeline finish.
    for _ in range(500):
        j = await store.get(job.job_id)
        if j.status == StageStatus.done:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("pipeline did not finish")

    result = await runner.cancel(job.job_id)
    assert result == "done"  # not cancellable anymore


async def test_cancelled_error_survives_guarded_run_cleanly(
    runner, store, monkeypatch, tmp_path
):
    """_guarded_run swallows CancelledError and leaves no registry entries."""
    runner._run_async = SubprocessMock(mode="slow")

    await store.init()
    job = await _launch(runner, tmp_path)

    # Wait for the task to actually be running a stage.
    for _ in range(500):
        j = await store.get(job.job_id)
        if j.status == StageStatus.running:
            break
        await asyncio.sleep(0.01)
    else:
        raise AssertionError("job never entered running state")

    task = runner._tasks[job.job_id]
    result = await runner.cancel(job.job_id)
    assert result == "cancelled"

    await asyncio.sleep(0.05)  # let _guarded_run's finally run
    assert task.done()
    assert not task.cancelled()  # _guarded_run swallowed it deliberately
    assert job.job_id not in runner._tasks
    assert job.job_id not in runner._procs

    j = await store.get(job.job_id)
    assert j.status == StageStatus.cancelled
    assert j.stages["netconvert"] == StageStatus.cancelled
    assert j.stages["random_trips"] == StageStatus.pending
    assert j.completed_at is not None
