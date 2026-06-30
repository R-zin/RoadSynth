"""
OSM → NS-3 Mobility Trace Conversion API

Endpoints:
  POST /jobs            — Upload OSM + JSON config → start conversion job
  GET  /jobs            — List all jobs
  GET  /jobs/{id}       — Poll job status + stage progress
  GET  /jobs/{id}/download/{filename} — Download output file
  GET  /jobs/{id}/logs  — Retrieve stage logs
  DELETE /jobs/{id}     — Remove job and its files
  GET  /schema          — Full JSON Schema for all parameters
  GET  /defaults        — Default configuration values
  GET  /health          — Health check + SUMO tool availability
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
from pathlib import Path
from typing import List, Optional

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .models import (
    ConversionRequest,
    JobStatus,
    StageStatus,
)
from .pipeline import (
    OUT_DIR,
    JOBS_DIR,
    UPLOAD_DIR,
    create_job,
    get_defaults,
    get_full_schema,
    get_job,
    list_jobs,
    run_pipeline,
)

# ── App setup ────────────────────────────────────────────────

app = FastAPI(
    title="OSM → NS-3 Mobility Trace Converter",
    description=(
        "Convert OpenStreetMap files to NS-3 mobility traces "
        "(ns_movements / TCL) via the full SUMO pipeline. "
        "Every parameter is exposed."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Dependency: parse config from multipart form ──────────────

async def parse_config(config: str = Form(default="{}")) -> ConversionRequest:
    """
    Parse the JSON configuration from the multipart form field.
    Unspecified fields use their defaults (all parameters have sensible defaults).
    """
    try:
        data = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"config JSON parse error: {exc}",
        )
    try:
        return ConversionRequest(**data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"config validation error: {exc}",
        )


# ── Routes ────────────────────────────────────────────────────

@app.get("/health", tags=["system"])
async def health():
    """Check API health and SUMO tool availability on the server."""
    tools = ["netconvert", "duarouter", "sumo"]
    availability = {t: shutil.which(t) is not None for t in tools}

    # Check traceExporter.py
    te_paths = [
        "/usr/share/sumo/tools/traceExporter.py",
        "/usr/local/share/sumo/tools/traceExporter.py",
    ]
    te_available = any(Path(p).exists() for p in te_paths)
    availability["traceExporter.py"] = te_available

    rt_paths = [
        "/usr/share/sumo/tools/randomTrips.py",
        "/usr/local/share/sumo/tools/randomTrips.py",
    ]
    rt_available = any(Path(p).exists() for p in rt_paths)
    availability["randomTrips.py"] = rt_available

    all_ok = all(availability.values())
    return {
        "status": "ready" if all_ok else "degraded",
        "tools": availability,
        "pipeline_ready": all_ok,
    }


@app.get("/schema", tags=["config"])
async def get_schema():
    """
    Return the full JSON Schema for ConversionRequest.
    Use this to auto-generate forms or validate configs client-side.
    """
    return get_full_schema()


@app.get("/defaults", tags=["config"])
async def get_default_config():
    """Return the default configuration for all pipeline stages."""
    return get_defaults()


@app.post("/jobs", status_code=status.HTTP_202_ACCEPTED, tags=["jobs"])
async def create_conversion_job(
    background_tasks: BackgroundTasks,
    osm_file: UploadFile = File(..., description="OpenStreetMap .osm or .osm.pbf file"),
    config: ConversionRequest = Depends(parse_config),
):
    """
    Start an OSM → NS-3 conversion job.

    **Multipart form fields:**
    - `osm_file` — the `.osm` file to convert
    - `config`   — JSON string with pipeline parameters (partial or full).
                   Omitted fields use defaults. See `/defaults` and `/schema`.

    **Returns:** job_id for polling via `GET /jobs/{id}`

    **Example config (partial — just change what you need):**
    ```json
    {
      "random_trips": {
        "end": 1800,
        "period": 1.5,
        "vehicle_class": "passenger"
      },
      "sumo": {
        "step_length": 0.1,
        "fcd_output_period": 1.0
      },
      "trace_exporter": {
        "output_format": "both",
        "sampling_period": 1.0,
        "penetration_rate": 0.8
      }
    }
    ```
    """
    if not osm_file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    suffix = Path(osm_file.filename).suffix.lower()
    if suffix not in (".osm", ".xml", ".pbf"):
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Upload a .osm file.",
        )

    # Save upload
    job_id  = create_job()
    upload_path = UPLOAD_DIR / f"{job_id}{suffix}"
    content = await osm_file.read()
    upload_path.write_bytes(content)

    # Save config snapshot
    cfg_snap = JOBS_DIR / job_id
    cfg_snap.mkdir(parents=True, exist_ok=True)
    (cfg_snap / "config.json").write_text(config.model_dump_json(indent=2))

    # Launch pipeline in background
    background_tasks.add_task(run_pipeline, job_id, upload_path, config)

    return {
        "job_id": job_id,
        "message": "Job accepted. Poll GET /jobs/{job_id} for status.",
        "config_snapshot": config.model_dump(),
    }


@app.get("/jobs", response_model=List[JobStatus], tags=["jobs"])
async def list_all_jobs():
    """List all jobs (most recent first)."""
    jobs = list_jobs()
    jobs.sort(key=lambda j: j.created_at, reverse=True)
    return jobs


@app.get("/jobs/{job_id}", response_model=JobStatus, tags=["jobs"])
async def get_job_status(job_id: str):
    """
    Poll the status of a conversion job.

    **Stage order:**
    1. `netconvert`   — OSM → SUMO network
    2. `random_trips` — Generate vehicle trips
    3. `duarouter`    — Compute routes
    4. `sumo`         — Run traffic simulation
    5. `trace_export` — Export NS-3 mobility traces

    **Status values:** `pending` → `running` → `done` | `failed`
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    return job


@app.get("/jobs/{job_id}/config", tags=["jobs"])
async def get_job_config(job_id: str):
    """Retrieve the exact configuration used for a job."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
    cfg_path = JOBS_DIR / job_id / "config.json"
    if not cfg_path.exists():
        raise HTTPException(status_code=404, detail="Config not found for this job.")
    return json.loads(cfg_path.read_text())


@app.get("/jobs/{job_id}/files", tags=["jobs"])
async def list_job_files(job_id: str):
    """List all output files available for download."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    out_dir = OUT_DIR / job_id
    if not out_dir.exists():
        return {"job_id": job_id, "files": []}

    files = []
    for f in sorted(out_dir.iterdir()):
        files.append({
            "filename": f.name,
            "size_bytes": f.stat().st_size,
            "download_url": f"/jobs/{job_id}/download/{f.name}",
        })
    return {"job_id": job_id, "files": files}


@app.get("/jobs/{job_id}/download/{filename}", tags=["jobs"])
async def download_output(job_id: str, filename: str):
    """
    Download an output file.

    Common files produced:
    - `ns_movements`   — NS-3 Ns2MobilityHelper trace
    - `mobility.tcl`   — NS-2/NS-3 TCL Setdest trace
    - `tripinfo.xml`   — Per-vehicle trip statistics
    - `summary.xml`    — Per-step network statistics
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    file_path = OUT_DIR / job_id / filename
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

    # Sanitise path traversal
    try:
        file_path.resolve().relative_to((OUT_DIR / job_id).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid filename.")

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )


@app.get("/jobs/{job_id}/logs", tags=["jobs"])
async def get_job_logs(job_id: str):
    """
    Retrieve SUMO tool output logs captured during the job.
    Useful for debugging parameter choices.
    """
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    logs_dir = JOBS_DIR / job_id
    logs = {}
    for stage in ["netconvert", "duarouter", "sumo", "traceExporter"]:
        log_file = logs_dir / f"{stage}.log"
        if log_file.exists():
            logs[stage] = log_file.read_text()
        else:
            logs[stage] = None

    return {
        "job_id": job_id,
        "warnings": job.warnings,
        "stage_logs": logs,
    }


@app.delete("/jobs/{job_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["jobs"])
async def delete_job(job_id: str):
    """Delete a job and all its associated files."""
    from .pipeline import _jobs, _job_locks
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

    if job.status == StageStatus.running:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a running job. Wait for it to complete.",
        )

    # Clean up files
    for d in [JOBS_DIR / job_id, OUT_DIR / job_id]:
        if d.exists():
            shutil.rmtree(d)

    upload_dir = UPLOAD_DIR
    for f in upload_dir.glob(f"{job_id}*"):
        f.unlink()

    _jobs.pop(job_id, None)
    _job_locks.pop(job_id, None)