"""
SQLite-backed job store.

Replaces the previous in-memory ``_jobs`` dict: jobs survive server restarts,
and retention pruning is possible. Single-node scope — stdlib ``sqlite3``
with WAL journaling, one short-lived connection per call, executed via
``asyncio.to_thread`` so the event loop is never blocked.

On startup, jobs left in ``pending``/``running`` state by a previous
(crash-)shutdown are recovered to ``failed`` — their subprocesses cannot
survive a process restart, so failing with a reason is the honest outcome.
"""

from __future__ import annotations

import asyncio
import builtins
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .models import JobStatus, StageStatus

logger = logging.getLogger("osm2ns3.store")

SCHEMA_VERSION = "1"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id         TEXT PRIMARY KEY,
    status         TEXT NOT NULL,
    stage_statuses TEXT NOT NULL,
    stage_logs     TEXT NOT NULL,
    current_stage  TEXT,
    error          TEXT,
    outputs        TEXT NOT NULL,
    warnings       TEXT NOT NULL,
    config_json    TEXT,
    created_at     TEXT NOT NULL,
    completed_at   TEXT
);
CREATE TABLE IF NOT EXISTS kv (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

_FINISHED = (
    StageStatus.done.value,
    StageStatus.failed.value,
    StageStatus.cancelled.value,
)


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _job_to_row(job: JobStatus, config_json: str | None) -> tuple:
    d = job.model_dump(mode="json")
    return (
        d["job_id"],
        d["status"],
        json.dumps(d["stages"]),
        json.dumps(d["stage_logs"]),
        d["current_stage"],
        d["error"],
        json.dumps(d["outputs"]),
        json.dumps(d["warnings"]),
        config_json,
        d["created_at"],
        d["completed_at"],
    )


def _row_to_job(row: sqlite3.Row) -> JobStatus:
    return JobStatus.model_validate(
        {
            "job_id": row["job_id"],
            "status": row["status"],
            "stages": json.loads(row["stage_statuses"]),
            "stage_logs": json.loads(row["stage_logs"]),
            "current_stage": row["current_stage"],
            "error": row["error"],
            "outputs": json.loads(row["outputs"]),
            "warnings": json.loads(row["warnings"]),
            "created_at": row["created_at"],
            "completed_at": row["completed_at"],
        }
    )


class JobStore:
    """Durable job registry. All methods are async; blocking sqlite3 work
    runs in the default executor via asyncio.to_thread."""

    def __init__(
        self, db_path: Path, retention_max: int = 200, retention_days: int = 7
    ):
        self._path = Path(db_path)
        self._retention_max = retention_max
        self._retention_days = retention_days

    # ── Sync helpers (run in thread) ─────────────────────────

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path, timeout=30)
        conn.row_factory = sqlite3.Row
        return conn

    # ── Lifecycle ─────────────────────────────────────────────

    async def init(self) -> None:
        await asyncio.to_thread(self._init_sync)
        recovered = await self._recover_interrupted()
        for job_id in recovered:
            logger.warning(
                "job %s was pending/running at startup — marked failed "
                "(interrupted by server restart)",
                job_id,
            )

    def _init_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(_SCHEMA)
            conn.execute(
                "INSERT OR REPLACE INTO kv (key, value) VALUES ('schema_version', ?)",
                (SCHEMA_VERSION,),
            )

    async def _recover_interrupted(self) -> builtins.list[str]:
        interrupted = [
            j
            for j in await self.list()
            if j.status in (StageStatus.pending, StageStatus.running)
        ]
        for job in interrupted:
            job.status = StageStatus.failed
            job.error = "Interrupted by server restart"
            job.completed_at = _utcnow()
            for stage, st in job.stages.items():
                if st == StageStatus.running:
                    job.stages[stage] = StageStatus.failed
            await self.upsert(job)
        return [j.job_id for j in interrupted]

    # ── CRUD ──────────────────────────────────────────────────

    async def create(self, job: JobStatus, config_json: str | None) -> None:
        row = _job_to_row(job, config_json)

        def _op() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO jobs (job_id, status, stage_statuses, stage_logs,
                                      current_stage, error, outputs, warnings,
                                      config_json, created_at, completed_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    row,
                )

        await asyncio.to_thread(_op)
        logger.debug("created job row %s", job.job_id)

    async def get(self, job_id: str) -> JobStatus | None:
        def _op() -> JobStatus | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
            return _row_to_job(row) if row else None

        return await asyncio.to_thread(_op)

    async def list(self) -> builtins.list[JobStatus]:
        def _op() -> list[JobStatus]:
            with self._connect() as conn:
                rows = conn.execute("SELECT * FROM jobs").fetchall()
            return [_row_to_job(r) for r in rows]

        return await asyncio.to_thread(_op)

    async def upsert(self, job: JobStatus) -> None:
        """Full-row rewrite — called on every job state change."""

        def _op() -> None:
            with self._connect() as conn:
                conn.execute(
                    """
                    UPDATE jobs SET status = ?, stage_statuses = ?, stage_logs = ?,
                                    current_stage = ?, error = ?, outputs = ?,
                                    warnings = ?, completed_at = ?
                    WHERE job_id = ?
                    """,
                    (
                        job.status.value,
                        json.dumps(job.model_dump(mode="json")["stages"]),
                        json.dumps(job.model_dump(mode="json")["stage_logs"]),
                        job.current_stage,
                        job.error,
                        json.dumps(job.outputs),
                        json.dumps(job.warnings),
                        job.completed_at,
                        job.job_id,
                    ),
                )

        await asyncio.to_thread(_op)

    async def get_config(self, job_id: str) -> dict | None:
        def _op() -> dict | None:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT config_json FROM jobs WHERE job_id = ?", (job_id,)
                ).fetchone()
            if not row or row["config_json"] is None:
                return None
            return json.loads(row["config_json"])

        return await asyncio.to_thread(_op)

    async def delete(self, job_id: str) -> None:
        def _op() -> None:
            with self._connect() as conn:
                conn.execute("DELETE FROM jobs WHERE job_id = ?", (job_id,))

        await asyncio.to_thread(_op)

    # ── Retention ─────────────────────────────────────────────

    async def prune(self) -> builtins.list[str]:
        """Delete finished jobs beyond retention limits; returns pruned ids
        so the caller can remove their files."""

        def _op() -> list[str]:
            with self._connect() as conn:
                cutoff = (
                    datetime.now(timezone.utc) - timedelta(days=self._retention_days)
                ).isoformat()
                by_age = conn.execute(
                    f"SELECT job_id FROM jobs WHERE status IN ({','.join('?' * len(_FINISHED))}) "
                    "AND completed_at IS NOT NULL AND completed_at < ?",
                    (*_FINISHED, cutoff),
                ).fetchall()
                by_count = conn.execute(
                    f"""
                    SELECT job_id FROM jobs
                    WHERE status IN ({','.join('?' * len(_FINISHED))})
                    ORDER BY completed_at DESC
                    LIMIT -1 OFFSET ?
                    """,
                    (*_FINISHED, self._retention_max),
                ).fetchall()
                ids = sorted(
                    {r["job_id"] for r in by_age} | {r["job_id"] for r in by_count}
                )
                if ids:
                    conn.execute(
                        f"DELETE FROM jobs WHERE job_id IN ({','.join('?' * len(ids))})",
                        ids,
                    )
            return ids

        pruned = await asyncio.to_thread(_op)
        if pruned:
            logger.info("retention prune removed %d finished job(s)", len(pruned))
        return pruned
