"""
Async pipeline executor for OSM → NS-3 conversion.

All subprocess calls use asyncio.create_subprocess_exec — no blocking calls
on the event loop. File I/O uses aiofiles. Job state is persisted to the
SQLite-backed JobStore on every transition, per-stage logs are persisted to
disk and returned via the /jobs/{id}/logs endpoint.

Command builders and XML writers are pure module-level functions (no I/O
beyond what their docstrings say) so they can be imported and unit-tested
directly. Execution state lives in ``PipelineRunner``, which owns the
asyncio task + subprocess registries needed for cancellation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import signal
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiofiles
import aiofiles.os

from .models import (
    ConversionRequest,
    JobStatus,
    LaneChangeMode,
    NetconvertParams,
    OutputFormat,
    RandomTripsParams,
    SpeedMode,
    StageLog,
    StageStatus,
    SumoParams,
    TraceExporterParams,
    VehicleClass,
)
from .settings import Settings
from .store import JobStore

logger = logging.getLogger("osm2ns3.worker")

# SUMO tool search paths (extend / override via Settings.sumo_home
# or the SUMO_HOME env var)
_SUMO_TOOL_DIRS = [
    "/usr/share/sumo/tools",
    "/usr/local/share/sumo/tools",
]

STAGE_NAMES = ("netconvert", "random_trips", "duarouter", "sumo", "trace_export")

# Stages whose `{stage}.log` files are written into the job workdir (the
# old /logs endpoint naming used the raw tool names; kept for backcompat).
LOG_STAGE_ALIASES = {
    "netconvert": "netconvert",
    "random_trips": "random_trips",
    "duarouter": "duarouter",
    "sumo": "sumo",
    "trace_export": "trace_export",
    "traceExporter": "trace_export",  # legacy name from the old endpoint
}

_CANCEL_SENTINEL = "Cancelled by user"


# ── Pure helpers (sync, no I/O) ───────────────────────────────


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _speed_mode_int(m: SpeedMode) -> int:
    return {"right_of_way": 31, "no_checks": 32, "all_checks": 31}[m.value]


def _lc_mode_int(m: LaneChangeMode) -> int:
    return {"default": 1621, "no_lc": 0, "strategic": 256}[m.value]


def _find_binary(names: list[str]) -> str | None:
    """Return the first executable found in PATH from the candidate list."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _find_sumo_script(filename: str, sumo_home: str = "") -> str | None:
    """Locate a SUMO Python tool (randomTrips.py, traceExporter.py, …).

    Search order: well-known system dirs, then the provided sumo_home,
    then the SUMO_HOME env var.
    """
    env_home = os.environ.get("SUMO_HOME", "")
    candidates = [
        *[f"{d}/{filename}" for d in _SUMO_TOOL_DIRS],
        f"{sumo_home}/tools/{filename}" if sumo_home else None,
        f"{env_home}/tools/{filename}" if env_home and env_home != sumo_home else None,
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


def check_tools(sumo_home: str = "") -> dict[str, bool]:
    """Availability map for every SUMO tool the pipeline needs.

    Reuses the exact lookup logic the pipeline uses, so a `ready` result
    genuinely means the pipeline can run.
    """
    return {
        "netconvert": _find_binary(["netconvert", "netconvert.exe"]) is not None,
        "duarouter": _find_binary(["duarouter", "duarouter.exe"]) is not None,
        "sumo": _find_binary(["sumo", "sumo.exe"]) is not None,
        "traceExporter.py": _find_sumo_script("traceExporter.py", sumo_home)
        is not None,
        "randomTrips.py": _find_sumo_script("randomTrips.py", sumo_home) is not None,
    }


# ── Command builders (pure sync, no I/O) ──────────────────────


def _netconvert_cmd(osm: Path, net_out: Path, p: NetconvertParams) -> list[str]:
    tool = _find_binary(["netconvert", "netconvert.exe"])
    if not tool:
        raise RuntimeError(
            "netconvert not found — install SUMO: "
            "https://sumo.dlr.de/docs/Installing/index.html"
        )
    cmd = [
        tool,
        "--osm-files",
        str(osm),
        "--output-file",
        str(net_out),
        "--remove-edges.isolated",
        str(p.osm_remove_isolated_edges).lower(),
        "--keep-edges.by-vclass",
        p.keep_edges_by_vclass.value if p.keep_edges_by_vclass else "all",
        "--no-internal-links",
        str(p.geometry_no_internal_links).lower(),
        "--junctions.internal-link-detail",
        str(p.junctions_internal_link_detail),
        "--junctions.corner-detail",
        str(p.junctions_corner_detail),
        "--default.junctions.type",
        p.default_junction_type.value,
        "--junctions.minimum-size",
        str(p.junctions_min_size),
        "--junctions.limit-turn-speed",
        str(p.junctions_limit_turn_speed),
        "--default.lanewidth",
        str(p.default_lane_width),
        "--default.speed",
        str(p.default_speed_limit),
        "--default.lanenumber",
        str(p.default_num_lanes),
        "--tls.guess",
        str(p.tl_guess).lower(),
        "--tls.default-type",
        p.tl_type.value,
        "--tls.join",
        str(p.tl_join).lower(),
        "--tls.min-dur",
        str(p.tl_min_dur),
        "--tls.max-dur",
        str(p.tl_max_dur),
        "--proj.utm",
        str(p.proj_utm).lower(),
        "--osm.highway.type-tag",
        ",".join(p.osm_highway_types),
    ]
    if p.osm_no_large_roundabouts:
        cmd += ["--roundabouts.guess", "false"]
    if p.osm_oneway_spread:
        cmd += ["--osm.oneway-spread-right", "true"]
    if p.no_turnarounds:
        cmd += ["--no-turnarounds", "true"]
    if p.no_left_connections:
        cmd += ["--no-left-connections", "true"]
    if p.remove_edges_by_type:
        cmd += ["--remove-edges.by-type", p.remove_edges_by_type]
    if p.keep_fringe.value == "noFringe":
        cmd += ["--keep-edges.fringe-edges", "false"]
    if p.proj_plain_geo and not p.proj_utm:
        cmd += ["--proj.plain-geo", "true"]
    return cmd


def _random_trips_cmd(
    net: Path, trips_out: Path, p: RandomTripsParams, sumo_home: str = ""
) -> list[str]:
    script = _find_sumo_script("randomTrips.py", sumo_home)
    if not script:
        raise RuntimeError(
            "randomTrips.py not found — set SUMO_HOME or install sumo-tools."
        )
    cmd = [
        "python3",
        script,
        "--net-file",
        str(net),
        "--output-trip-file",
        str(trips_out),
        "--begin",
        str(p.begin),
        "--end",
        str(p.end),
        "--period",
        str(p.period),
        "--min-distance",
        str(p.min_distance),
        "--fringe-factor",
        str(p.fringe_factor),
        "--fringe-threshold",
        str(p.fringe_threshold),
        "--seed",
        str(p.seed),
        "--vclass",
        p.vehicle_class.value,
    ]
    if p.max_distance is not None:
        cmd += ["--max-distance", str(p.max_distance)]
    if p.insertion_density is not None:
        cmd += ["--insertion-density", str(p.insertion_density)]
    if p.validate_routes:
        cmd += ["--validate"]
    if p.allow_loops:
        cmd += ["--allow-fringe.min-length", "0"]
    if p.random_depart_pos:
        cmd += ["--random-depart-pos"]
    if p.random_arrival_pos:
        cmd += ["--random-arrival-pos"]
    return cmd


def _duarouter_cmd(
    net: Path, trips: Path, routes_out: Path, p: RandomTripsParams
) -> list[str]:
    tool = _find_binary(["duarouter", "duarouter.exe"])
    if not tool:
        raise RuntimeError("duarouter not found — install SUMO.")
    return [
        tool,
        "--net-file",
        str(net),
        "--trip-files",
        str(trips),
        "--output-file",
        str(routes_out),
        "--seed",
        str(p.seed),
        "--begin",
        str(p.begin),
        "--end",
        str(p.end),
        "--ignore-errors",
        "true",
        "--no-step-log",
    ]


def _sumo_cmd(cfg: Path, vtype: Path) -> list[str]:
    tool = _find_binary(["sumo", "sumo.exe"])
    if not tool:
        raise RuntimeError("sumo not found — install SUMO.")
    return [
        tool,
        "--configuration-file",
        str(cfg),
        "--additional-files",
        str(vtype),
    ]


def _trace_export_cmds(
    fcd: Path, workdir: Path, p: TraceExporterParams, sumo_home: str = ""
) -> list[tuple[str, list[str], Path]]:
    """Return list of (label, cmd, output_path) for traceExporter runs."""
    script = _find_sumo_script("traceExporter.py", sumo_home)
    if not script:
        raise RuntimeError(
            "traceExporter.py not found — set SUMO_HOME or install sumo-tools."
        )
    base = [
        "python3",
        script,
        "--fcd-input",
        str(fcd),
        "--begin",
        str(p.begin),
        "--penetration",
        str(p.penetration_rate),
        "--seed",
        str(p.seed),
        "--orig-x",
        str(p.x_offset),
        "--orig-y",
        str(p.y_offset),
    ]
    if p.end is not None:
        base += ["--end", str(p.end)]
    if p.boundary:
        base += ["--boundary", p.boundary]

    results: list[tuple[str, list[str], Path]] = []

    if p.output_format in (OutputFormat.ns_movements, OutputFormat.both):
        out = workdir / "ns_movements"
        c = base + ["--ns2-output", str(out)]
        if p.ns2_include_speed:
            c += ["--ns2-include-speed"]
        results.append(("ns_movements", c, out))

    if p.output_format in (OutputFormat.tcl, OutputFormat.both):
        out = workdir / "mobility.tcl"
        results.append(("tcl", base + ["--ns2-output", str(out)], out))

    return results


# ── Async file writers ────────────────────────────────────────


async def _write_text(path: Path, content: str) -> None:
    async with aiofiles.open(path, "w", encoding="utf-8") as fh:
        await fh.write(content)


async def _copy_file(src: Path, dst: Path) -> None:
    """Non-blocking file copy via aiofiles."""
    async with aiofiles.open(src, "rb") as r:
        data = await r.read()
    async with aiofiles.open(dst, "wb") as w:
        await w.write(data)


async def _write_sumo_cfg(
    workdir: Path,
    net: Path,
    routes: Path,
    fcd_out: Path,
    tripinfo_out: Path,
    summary_out: Path,
    p: SumoParams,
) -> Path:
    output_block = f"""
        <fcd-output value="{fcd_out}"/>
        <fcd-output.period value="{p.fcd_output_period}"/>
        <fcd-output.geo value="{str(p.fcd_output_geo).lower()}"/>"""
    if p.tripinfo_output:
        output_block += f'\n        <tripinfo-output value="{tripinfo_out}"/>'
    if p.summary_output:
        output_block += f'\n        <summary-output value="{summary_out}"/>'

    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<configuration xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
               xsi:noNamespaceSchemaLocation="http://sumo.dlr.de/xsd/sumoConfiguration.xsd">
    <input>
        <net-file value="{net}"/>
        <route-files value="{routes}"/>
    </input>
    <time>
        <begin value="{p.begin}"/>
        <end value="{p.end}"/>
        <step-length value="{p.step_length}"/>
    </time>
    <processing>
        <ignore-route-errors value="{str(p.ignore_route_errors).lower()}"/>
        <no-internal-links value="{str(p.no_internal_links).lower()}"/>
        <collision.action value="{p.collision_action}"/>
        <lateral-resolution value="{p.lateral_resolution}"/>
    </processing>
    <output>{output_block}
    </output>
    <random_number>
        <seed value="{p.seed}"/>
    </random_number>
    <report>
        <no-step-log value="true"/>
        <verbose value="false"/>
    </report>
</configuration>
"""
    cfg_path = workdir / "sim.sumocfg"
    await _write_text(cfg_path, xml)
    return cfg_path


async def _write_vtype_xml(workdir: Path, p: SumoParams, vc: VehicleClass) -> Path:
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<additional>
    <vType id="vType_{vc.value}"
           vClass="{vc.value}"
           length="{p.default_vehicle_length}"
           minGap="{p.default_min_gap}"
           maxSpeed="{p.default_max_speed}"
           accel="{p.default_accel}"
           decel="{p.default_decel}"
           emergencyDecel="{p.default_emergency_decel}"
           sigma="{p.default_sigma}"
           tau="{p.default_tau}"
           speedMode="{_speed_mode_int(p.speed_mode)}"
           lcMode="{_lc_mode_int(p.lanechange_mode)}"/>
</additional>
"""
    vtype_path = workdir / "vtypes.add.xml"
    await _write_text(vtype_path, xml)
    return vtype_path


# ── Pipeline runner ───────────────────────────────────────────


class PipelineRunner:
    """Owns per-job execution state: task registry, current subprocess set,
    concurrency semaphore. Created once at app startup with injected
    Settings + JobStore."""

    def __init__(self, settings: Settings, store: JobStore):
        self.settings = settings
        self.store = store
        self._tasks: dict[str, asyncio.Task] = {}
        self._procs: dict[str, set[asyncio.subprocess.Process]] = {}
        self._semaphore = asyncio.Semaphore(settings.max_concurrent_jobs)

    # ── Job lifecycle ─────────────────────────────────────────

    def _new_job(self, job_id: str | None = None) -> JobStatus:
        return JobStatus(
            job_id=job_id or str(uuid.uuid4()),
            status=StageStatus.pending,
            stages={name: StageStatus.pending for name in STAGE_NAMES},
            stage_logs={},
            created_at=_now(),
        )

    async def create_and_launch(
        self, osm_path: Path, config: ConversionRequest, job_id: str | None = None
    ) -> JobStatus:
        """Persist a new job row, then start its pipeline task. When job_id
        is provided it must match the pre-saved upload filename."""
        job = self._new_job(job_id)
        await self.store.create(job, config.model_dump_json())
        logger.info("job %s created (%s)", job.job_id, osm_path.name)
        self._tasks[job.job_id] = asyncio.create_task(
            self._guarded_run(job.job_id, osm_path, config)
        )
        return job

    async def cancel(self, job_id: str) -> str:
        """Cancel a pending/running job: kill its subprocess tree, then its
        task. Returns the resulting status string; raises LookupError for an
        unknown job and RuntimeError when the job is not in a cancellable
        state."""
        job = await self.store.get(job_id)
        if not job:
            raise LookupError(job_id)
        if job.status not in (StageStatus.pending, StageStatus.running):
            return job.status.value  # not cancellable

        # Durable intent first: the DB records the cancel even if the
        # process dies mid-kill.
        job.status = StageStatus.cancelled
        if job.error is None:
            job.error = _CANCEL_SENTINEL
        job.completed_at = _now()
        for stage, st in job.stages.items():
            if st == StageStatus.running:
                job.stages[stage] = StageStatus.cancelled
        await self.store.upsert(job)
        logger.info("job %s cancelled by user", job_id)

        # Kill the subprocess group BEFORE cancelling the task:
        # asyncio.wait_for(proc.communicate()) does not kill the child when
        # the awaiting task is cancelled.
        for proc in list(self._procs.get(job_id, ())):
            self._kill_proc_tree(proc)

        task = self._tasks.get(job_id)
        if task is not None:
            task.cancel()
        return StageStatus.cancelled.value

    async def delete(self, job_id: str) -> None:
        await self.store.delete(job_id)
        self.cleanup_job_files(job_id)

    def cleanup_job_files(self, job_id: str) -> None:
        """Remove workdir, outputs, uploads and the upload file for a job."""
        for d in (self.settings.jobs_dir / job_id, self.settings.out_dir / job_id):
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
        for f in self.settings.upload_dir.glob(f"{job_id}*"):
            f.unlink(missing_ok=True)

    async def prune_finished(self) -> None:
        for job_id in await self.store.prune():
            self.cleanup_job_files(job_id)

    @staticmethod
    def _kill_proc_tree(proc: asyncio.subprocess.Process) -> None:
        """SIGKILL the whole process group (children included); fall back to
        killing just the process where process groups are unavailable."""
        if proc.returncode is not None:
            return
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, AttributeError, OSError):
            try:
                proc.kill()
            except ProcessLookupError:
                pass

    # ── Task wrapper ──────────────────────────────────────────

    async def _guarded_run(
        self, job_id: str, osm_path: Path, config: ConversionRequest
    ) -> None:
        """Concurrency gate + registry cleanup around the pipeline. This is
        the top of our own task tree, so CancelledError is deliberately
        swallowed here AFTER cleanup — cancelling this task is the
        cancellation mechanism, not an error."""
        try:
            async with self._semaphore:
                await self._run_pipeline(job_id, osm_path, config)
        except asyncio.CancelledError:
            logger.info("job %s pipeline task cancelled", job_id)
        except Exception:
            logger.exception("job %s pipeline task crashed unexpectedly", job_id)
        finally:
            self._tasks.pop(job_id, None)
            self._procs.pop(job_id, None)
            await self.prune_finished()

    # ── Async subprocess primitive ────────────────────────────

    async def _run_async(
        self,
        job_id: str,
        cmd: list[str],
        workdir: Path,
        timeout: float,
    ) -> tuple[int, str, str]:
        """Run a command asynchronously.
        Returns (returncode, stdout, stderr).
        Raises RuntimeError on timeout or missing executable, and
        CancelledError when the job is cancelled (after killing the tree)."""
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(workdir),
                start_new_session=True,
            )
        except FileNotFoundError:
            raise RuntimeError(f"Executable not found: {cmd[0]!r}")

        self._procs.setdefault(job_id, set()).add(proc)
        try:
            raw_out, raw_err = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            self._kill_proc_tree(proc)
            await proc.communicate()
            raise RuntimeError(
                f"Command timed out after {timeout:.0f} s: {' '.join(cmd[:3])!r}…"
            )
        except asyncio.CancelledError:
            self._kill_proc_tree(proc)
            raise
        finally:
            self._procs.get(job_id, set()).discard(proc)

        rc = proc.returncode
        if rc is not None and rc != 0:
            logger.warning(
                "job %s command %r exited %d",
                job_id,
                cmd[0],
                rc,
            )
        return rc, raw_out.decode(errors="replace"), raw_err.decode(errors="replace")

    # ── Job state update + persistence ────────────────────────

    async def _persist(self, job: JobStatus) -> None:
        await self.store.upsert(job)

    async def _set_stage(
        self,
        job: JobStatus,
        stage: str,
        status: StageStatus,
        log: StageLog | None = None,
    ) -> None:
        job.stages[stage] = status
        job.current_stage = stage
        if log:
            job.stage_logs[stage] = log.model_dump()
        await self._persist(job)

    # ── Per-stage runner with timing + log persistence ────────

    async def _run_stage(
        self,
        job: JobStatus,
        stage: str,
        cmd: list[str],
        workdir: Path,
        timeout: float,
    ) -> tuple[str, str]:
        """
        Mark stage running, execute the command, persist stdout/stderr to disk,
        update the job's StageLog, and return (stdout, stderr).
        Raises RuntimeError on non-zero exit or timeout.
        """
        await self._set_stage(job, stage, StageStatus.running)
        t0 = time.monotonic()

        rc, stdout, stderr = await self._run_async(job.job_id, cmd, workdir, timeout)

        elapsed = time.monotonic() - t0

        # Persist log to disk (non-blocking)
        log_path = workdir / f"{stage}.log"
        await _write_text(
            log_path, f"=== stdout ===\n{stdout}\n=== stderr ===\n{stderr}\n"
        )

        # Capture SUMO warnings into the job
        for line in (stdout + stderr).splitlines():
            if "Warning" in line or "warning" in line:
                job.warnings.append(f"[{stage}] {line.strip()}")

        log = StageLog(
            status=StageStatus.done if rc == 0 else StageStatus.failed,
            stdout=stdout[:4000] if stdout else None,  # truncate for the store
            stderr=stderr[:4000] if stderr else None,
            duration=round(elapsed, 3),
        )

        if rc != 0:
            await self._set_stage(job, stage, StageStatus.failed, log)
            raise RuntimeError(
                f"Stage '{stage}' exited with code {rc}.\nstderr: {stderr[:800]}"
            )

        await self._set_stage(job, stage, StageStatus.done, log)
        logger.info("job %s stage %s done in %.1fs", job.job_id, stage, elapsed)
        return stdout, stderr

    # ── Master pipeline ───────────────────────────────────────

    async def _run_pipeline(
        self,
        job_id: str,
        osm_path: Path,
        config: ConversionRequest,
    ) -> None:
        """
        Execute all five pipeline stages sequentially.

        Stages:
          1. netconvert   — OSM → .net.xml
          2. random_trips — .net.xml → trips.xml
          3. duarouter    — trips.xml → routes.rou.xml
          4. sumo         — routes + net → fcd-output.xml
          5. trace_export — fcd-output.xml → ns_movements / mobility.tcl
        """
        workdir = self.settings.jobs_dir / job_id
        await aiofiles.os.makedirs(workdir, exist_ok=True)

        job = await self.store.get(job_id)
        if job is None:
            logger.error("job %s vanished before pipeline start", job_id)
            return
        if job.status == StageStatus.cancelled:
            return  # cancelled while queued on the semaphore

        job.status = StageStatus.running
        await self._persist(job)
        sumo_home = self.settings.resolve_sumo_home()

        try:
            # ── 1. netconvert ────────────────────────────────
            net_path = workdir / "network.net.xml"
            await self._run_stage(
                job,
                "netconvert",
                _netconvert_cmd(osm_path, net_path, config.netconvert),
                workdir,
                timeout=self.settings.timeout_default_s,
            )

            # ── 2. randomTrips ───────────────────────────────
            trips_path = workdir / "trips.xml"
            await self._run_stage(
                job,
                "random_trips",
                _random_trips_cmd(net_path, trips_path, config.random_trips, sumo_home),
                workdir,
                timeout=self.settings.timeout_default_s,
            )

            # ── 3. duarouter ─────────────────────────────────
            routes_path = workdir / "routes.rou.xml"
            await self._run_stage(
                job,
                "duarouter",
                _duarouter_cmd(net_path, trips_path, routes_path, config.random_trips),
                workdir,
                timeout=self.settings.timeout_default_s,
            )

            # ── 4. sumo ──────────────────────────────────────
            fcd_path = workdir / "fcd-output.xml"
            tripinfo_path = workdir / "tripinfo.xml"
            summary_path = workdir / "summary.xml"

            # Write config files asynchronously before launching SUMO
            cfg_path, vtype_path = await asyncio.gather(
                _write_sumo_cfg(
                    workdir,
                    net_path,
                    routes_path,
                    fcd_path,
                    tripinfo_path,
                    summary_path,
                    config.sumo,
                ),
                _write_vtype_xml(
                    workdir, config.sumo, config.random_trips.vehicle_class
                ),
            )

            await self._run_stage(
                job,
                "sumo",
                _sumo_cmd(cfg_path, vtype_path),
                workdir,
                timeout=self.settings.timeout_sumo_s,
            )

            # ── 5. traceExporter ─────────────────────────────
            await self._set_stage(job, "trace_export", StageStatus.running)
            t0 = time.monotonic()

            export_specs = _trace_export_cmds(
                fcd_path, workdir, config.trace_exporter, sumo_home
            )

            # Run all traceExporter variants concurrently
            tasks = [
                self._run_async(
                    job_id, cmd, workdir, self.settings.timeout_trace_export_s
                )
                for _, cmd, _ in export_specs
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            dest_dir = self.settings.out_dir / job_id
            await aiofiles.os.makedirs(dest_dir, exist_ok=True)

            output_files: list[str] = []
            for (label, _, out_path), result in zip(export_specs, results):
                if isinstance(result, Exception):
                    job.warnings.append(f"[trace_export:{label}] {result}")
                    logger.warning(
                        "job %s trace_export:%s failed: %s", job_id, label, result
                    )
                    continue
                rc, stdout, stderr = result
                if rc != 0:
                    job.warnings.append(
                        f"[trace_export:{label}] exit {rc}: {stderr[:300]}"
                    )
                elif out_path.exists():
                    dst = dest_dir / out_path.name
                    await _copy_file(out_path, dst)
                    output_files.append(str(dst))

            # Copy SUMO stats outputs
            for extra in (tripinfo_path, summary_path):
                if extra.exists():
                    dst = dest_dir / extra.name
                    await _copy_file(extra, dst)
                    output_files.append(str(dst))

            elapsed = time.monotonic() - t0
            log = StageLog(status=StageStatus.done, duration=round(elapsed, 3))
            await self._set_stage(job, "trace_export", StageStatus.done, log)

            # A cancel may have completed all subprocess work before the
            # CancelledError was delivered — never clobber it with "done".
            latest = await self.store.get(job_id)
            if latest is not None and latest.status == StageStatus.cancelled:
                raise asyncio.CancelledError()

            job.outputs = output_files
            job.status = StageStatus.done
            job.completed_at = _now()
            await self._persist(job)
            logger.info("job %s done (%d output file(s))", job_id, len(output_files))

        except asyncio.CancelledError:
            # DB state was already persisted by cancel(); ensure completion
            # markers for races where cancel() ran before the job started.
            if job.status != StageStatus.cancelled:
                job.status = StageStatus.cancelled
                job.error = job.error or _CANCEL_SENTINEL
                job.completed_at = job.completed_at or _now()
                for stage, st in job.stages.items():
                    if st == StageStatus.running:
                        job.stages[stage] = StageStatus.cancelled
                await self._persist(job)
            raise  # handed to _guarded_run

        except RuntimeError as exc:
            if await self._was_cancelled(job_id, job):
                raise asyncio.CancelledError()
            job.status = StageStatus.failed
            job.error = str(exc)
            job.completed_at = _now()
            await self._persist(job)
            logger.warning("job %s failed: %s", job_id, exc)

        except Exception as exc:
            if await self._was_cancelled(job_id, job):
                raise asyncio.CancelledError()
            job.status = StageStatus.failed
            job.error = f"Unexpected error in pipeline: {exc!r}"
            job.completed_at = _now()
            await self._persist(job)
            logger.exception("job %s failed unexpectedly", job_id)

    async def _was_cancelled(self, job_id: str, job: JobStatus) -> bool:
        """True when a cancel landed while a stage was failing — cancellation
        wins over the failure report."""
        latest = await self.store.get(job_id)
        return latest is not None and latest.status == StageStatus.cancelled
