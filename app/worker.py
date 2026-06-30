"""
Async pipeline executor for OSM → NS-3 conversion.

All subprocess calls use asyncio.create_subprocess_exec — no blocking calls
on the event loop. File I/O uses aiofiles. Per-stage logs are persisted to
disk and returned via the /jobs/{id}/logs endpoint.
"""

from __future__ import annotations

import asyncio
import shutil
import time
import uuid
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Dict, List, Optional, Tuple

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

# ── Directory layout ──────────────────────────────────────────
BASE_DIR   = Path(__file__).parent.parent
JOBS_DIR   = BASE_DIR / "jobs"
UPLOAD_DIR = BASE_DIR / "uploads"
OUT_DIR    = BASE_DIR / "outputs"

for _d in (JOBS_DIR, UPLOAD_DIR, OUT_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# In-memory job store (swap for Redis/SQLite in production)
_jobs:      Dict[str, JobStatus]    = {}
_job_locks: Dict[str, asyncio.Lock] = {}

# SUMO tool search paths (extend / override via SUMO_HOME env var)
_SUMO_TOOL_DIRS = [
    "/usr/share/sumo/tools",
    "/usr/local/share/sumo/tools",
]


# ── Pure helpers (sync, no I/O) ───────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _speed_mode_int(m: SpeedMode) -> int:
    return {"right_of_way": 31, "no_checks": 32, "all_checks": 31}[m.value]


def _lc_mode_int(m: LaneChangeMode) -> int:
    return {"default": 1621, "no_lc": 0, "strategic": 256}[m.value]


def _find_binary(names: List[str]) -> Optional[str]:
    """Return the first executable found in PATH from the candidate list."""
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def _find_sumo_script(filename: str) -> Optional[str]:
    """Locate a SUMO Python tool (randomTrips.py, traceExporter.py, …)."""
    import os
    sumo_home = os.environ.get("SUMO_HOME", "")
    candidates = [
        *[f"{d}/{filename}" for d in _SUMO_TOOL_DIRS],
        f"{sumo_home}/tools/{filename}" if sumo_home else None,
    ]
    return next((c for c in candidates if c and Path(c).exists()), None)


# ── Job registry ──────────────────────────────────────────────

def create_job() -> str:
    job_id = str(uuid.uuid4())
    _jobs[job_id] = JobStatus(
        job_id=job_id,
        status=StageStatus.pending,
        stages={
            "netconvert":   StageStatus.pending,
            "random_trips": StageStatus.pending,
            "duarouter":    StageStatus.pending,
            "sumo":         StageStatus.pending,
            "trace_export": StageStatus.pending,
        },
        stage_logs={},
        created_at=_now(),
    )
    _job_locks[job_id] = asyncio.Lock()
    return job_id


def get_job(job_id: str) -> Optional[JobStatus]:
    return _jobs.get(job_id)


def list_jobs() -> List[JobStatus]:
    return list(_jobs.values())


def get_full_schema() -> dict:
    return ConversionRequest.model_json_schema()


def get_defaults() -> dict:
    return ConversionRequest().model_dump()


# ── Async subprocess primitive ────────────────────────────────

async def _run_async(
    cmd: List[str],
    workdir: Path,
    timeout: float = 600.0,
) -> Tuple[int, str, str]:
    """
    Run a command asynchronously.
    Returns (returncode, stdout, stderr).
    Raises RuntimeError on timeout or missing executable.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(workdir),
        )
    except FileNotFoundError:
        raise RuntimeError(f"Executable not found: {cmd[0]!r}")

    try:
        raw_out, raw_err = await asyncio.wait_for(
            proc.communicate(), timeout=timeout
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        raise RuntimeError(
            f"Command timed out after {timeout:.0f} s: {' '.join(cmd[:3])!r}…"
        )

    return proc.returncode, raw_out.decode(errors="replace"), raw_err.decode(errors="replace")


# ── Async file I/O helpers ────────────────────────────────────

async def _write_text(path: Path, content: str) -> None:
    async with aiofiles.open(path, "w", encoding="utf-8") as fh:
        await fh.write(content)


async def _copy_file(src: Path, dst: Path) -> None:
    """Non-blocking file copy via aiofiles."""
    async with aiofiles.open(src, "rb") as r:
        data = await r.read()
    async with aiofiles.open(dst, "wb") as w:
        await w.write(data)


# ── Job state update ──────────────────────────────────────────

def _set_stage(
    job: JobStatus,
    stage: str,
    status: StageStatus,
    log: Optional[StageLog] = None,
) -> None:
    job.stages[stage]    = status
    job.current_stage    = stage
    if log:
        job.stage_logs[stage] = log.model_dump()


# ── Command builders (pure sync, no I/O) ─────────────────────

def _netconvert_cmd(osm: Path, net_out: Path, p: NetconvertParams) -> List[str]:
    tool = _find_binary(["netconvert", "netconvert.exe"])
    if not tool:
        raise RuntimeError(
            "netconvert not found — install SUMO: "
            "https://sumo.dlr.de/docs/Installing/index.html"
        )
    cmd = [
        tool,
        "--osm-files",   str(osm),
        "--output-file", str(net_out),

        "--remove-edges.isolated",          str(p.osm_remove_isolated_edges).lower(),
        "--keep-edges.by-vclass",           p.keep_edges_by_vclass.value
                                            if p.keep_edges_by_vclass else "all",

        "--no-internal-links",              str(p.geometry_no_internal_links).lower(),
        "--junctions.internal-link-detail", str(p.junctions_internal_link_detail),
        "--junctions.corner-detail",        str(p.junctions_corner_detail),
        "--default.junctions.type",         p.default_junction_type.value,
        "--junctions.minimum-size",         str(p.junctions_min_size),
        "--junctions.limit-turn-speed",     str(p.junctions_limit_turn_speed),

        "--default.lanewidth",              str(p.default_lane_width),
        "--default.speed",                  str(p.default_speed_limit),
        "--default.lanenumber",             str(p.default_num_lanes),

        "--tls.guess",                      str(p.tl_guess).lower(),
        "--tls.default-type",               p.tl_type.value,
        "--tls.join",                       str(p.tl_join).lower(),
        "--tls.min-dur",                    str(p.tl_min_dur),
        "--tls.max-dur",                    str(p.tl_max_dur),

        "--proj.utm",                       str(p.proj_utm).lower(),
        "--osm.highway.type-tag",           ",".join(p.osm_highway_types),
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


def _random_trips_cmd(net: Path, trips_out: Path, p: RandomTripsParams) -> List[str]:
    script = _find_sumo_script("randomTrips.py")
    if not script:
        raise RuntimeError(
            "randomTrips.py not found — set SUMO_HOME or install sumo-tools."
        )
    cmd = [
        "python3", script,
        "--net-file",          str(net),
        "--output-trip-file",  str(trips_out),
        "--begin",             str(p.begin),
        "--end",               str(p.end),
        "--period",            str(p.period),
        "--min-distance",      str(p.min_distance),
        "--fringe-factor",     str(p.fringe_factor),
        "--fringe-threshold",  str(p.fringe_threshold),
        "--seed",              str(p.seed),
        "--vclass",            p.vehicle_class.value,
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
) -> List[str]:
    tool = _find_binary(["duarouter", "duarouter.exe"])
    if not tool:
        raise RuntimeError("duarouter not found — install SUMO.")
    return [
        tool,
        "--net-file",    str(net),
        "--trip-files",  str(trips),
        "--output-file", str(routes_out),
        "--seed",        str(p.seed),
        "--begin",       str(p.begin),
        "--end",         str(p.end),
        "--ignore-errors", "true",
        "--no-step-log",
    ]


def _sumo_cmd(cfg: Path, vtype: Path) -> List[str]:
    tool = _find_binary(["sumo", "sumo.exe"])
    if not tool:
        raise RuntimeError("sumo not found — install SUMO.")
    return [
        tool,
        "--configuration-file", str(cfg),
        "--additional-files",   str(vtype),
    ]


def _trace_export_cmds(
    fcd: Path, workdir: Path, p: TraceExporterParams
) -> List[Tuple[str, List[str], Path]]:
    """Return list of (label, cmd, output_path) for traceExporter runs."""
    script = _find_sumo_script("traceExporter.py")
    if not script:
        raise RuntimeError(
            "traceExporter.py not found — set SUMO_HOME or install sumo-tools."
        )
    base = [
        "python3", script,
        "--fcd-input",    str(fcd),
        "--begin",        str(p.begin),
        "--penetration",  str(p.penetration_rate),
        "--seed",         str(p.seed),
        "--orig-x",       str(p.x_offset),
        "--orig-y",       str(p.y_offset),
    ]
    if p.end is not None:
        base += ["--end", str(p.end)]
    if p.boundary:
        base += ["--boundary", p.boundary]

    results: List[Tuple[str, List[str], Path]] = []

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


async def _write_vtype_xml(
    workdir: Path, p: SumoParams, vc: VehicleClass
) -> Path:
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


# ── Per-stage runner with timing + log persistence ────────────

async def _run_stage(
    job: JobStatus,
    stage: str,
    cmd: List[str],
    workdir: Path,
    timeout: float = 600.0,
) -> Tuple[str, str]:
    """
    Mark stage running, execute the command, persist stdout/stderr to disk,
    update the job's StageLog, and return (stdout, stderr).
    Raises RuntimeError on non-zero exit or timeout.
    """
    _set_stage(job, stage, StageStatus.running)
    t0 = time.monotonic()

    rc, stdout, stderr = await _run_async(cmd, workdir, timeout=timeout)

    elapsed = time.monotonic() - t0

    # Persist log to disk (non-blocking)
    log_path = workdir / f"{stage}.log"
    await _write_text(log_path, f"=== stdout ===\n{stdout}\n=== stderr ===\n{stderr}\n")

    # Capture SUMO warnings into the job
    for line in (stdout + stderr).splitlines():
        if "Warning" in line or "warning" in line:
            job.warnings.append(f"[{stage}] {line.strip()}")

    log = StageLog(
        status=StageStatus.done if rc == 0 else StageStatus.failed,
        stdout=stdout[:4000] if stdout else None,   # truncate for in-memory store
        stderr=stderr[:4000] if stderr else None,
        duration=round(elapsed, 3),
    )

    if rc != 0:
        _set_stage(job, stage, StageStatus.failed, log)
        raise RuntimeError(
            f"Stage '{stage}' exited with code {rc}.\n"
            f"stderr: {stderr[:800]}"
        )

    _set_stage(job, stage, StageStatus.done, log)
    return stdout, stderr


# ── Master pipeline ───────────────────────────────────────────

async def run_pipeline(
    job_id: str,
    osm_path: Path,
    config: ConversionRequest,
) -> None:
    """
    Execute all five pipeline stages sequentially in the background.

    Stages:
      1. netconvert   — OSM → .net.xml
      2. random_trips — .net.xml → trips.xml
      3. duarouter    — trips.xml → routes.rou.xml
      4. sumo         — routes + net → fcd-output.xml
      5. trace_export — fcd-output.xml → ns_movements / mobility.tcl
    """
    workdir = JOBS_DIR / job_id
    await aiofiles.os.makedirs(workdir, exist_ok=True)

    job = _jobs[job_id]
    job.status = StageStatus.running

    try:
        # ── 1. netconvert ────────────────────────────────────
        net_path = workdir / "network.net.xml"
        await _run_stage(
            job, "netconvert",
            _netconvert_cmd(osm_path, net_path, config.netconvert),
            workdir,
        )

        # ── 2. randomTrips ───────────────────────────────────
        trips_path = workdir / "trips.xml"
        await _run_stage(
            job, "random_trips",
            _random_trips_cmd(net_path, trips_path, config.random_trips),
            workdir,
        )

        # ── 3. duarouter ─────────────────────────────────────
        routes_path = workdir / "routes.rou.xml"
        await _run_stage(
            job, "duarouter",
            _duarouter_cmd(net_path, trips_path, routes_path, config.random_trips),
            workdir,
        )

        # ── 4. sumo ──────────────────────────────────────────
        fcd_path      = workdir / "fcd-output.xml"
        tripinfo_path = workdir / "tripinfo.xml"
        summary_path  = workdir / "summary.xml"

        # Write config files asynchronously before launching SUMO
        cfg_path, vtype_path = await asyncio.gather(
            _write_sumo_cfg(
                workdir, net_path, routes_path,
                fcd_path, tripinfo_path, summary_path,
                config.sumo,
            ),
            _write_vtype_xml(workdir, config.sumo, config.random_trips.vehicle_class),
        )

        await _run_stage(
            job, "sumo",
            _sumo_cmd(cfg_path, vtype_path),
            workdir,
            timeout=1200.0,   # SUMO can be slow on large networks
        )

        # ── 5. traceExporter ─────────────────────────────────
        _set_stage(job, "trace_export", StageStatus.running)
        t0 = time.monotonic()

        export_specs = _trace_export_cmds(fcd_path, workdir, config.trace_exporter)

        # Run all traceExporter variants concurrently
        tasks = [
            _run_async(cmd, workdir, timeout=300.0)
            for _, cmd, _ in export_specs
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        dest_dir = OUT_DIR / job_id
        await aiofiles.os.makedirs(dest_dir, exist_ok=True)

        output_files: List[str] = []
        for (label, _, out_path), result in zip(export_specs, results):
            if isinstance(result, Exception):
                job.warnings.append(f"[trace_export:{label}] {result}")
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
        _set_stage(job, "trace_export", StageStatus.done, log)

        job.outputs      = output_files
        job.status       = StageStatus.done
        job.completed_at = _now()

    except RuntimeError as exc:
        job.status       = StageStatus.failed
        job.error        = str(exc)
        job.completed_at = _now()

    except Exception as exc:
        job.status       = StageStatus.failed
        job.error        = f"Unexpected error in pipeline: {exc!r}"
        job.completed_at = _now()



