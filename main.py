"""
OSM → NS-3 Mobility Trace Conversion API

Endpoints:
  POST   /jobs                    — Upload OSM + JSON config → start conversion job
  GET    /jobs                    — List all jobs
  GET    /jobs/{id}               — Poll job status + stage progress
  POST   /jobs/{id}/cancel        — Cancel a pending/running job
  GET    /jobs/{id}/download/{fn} — Download output file
  GET    /jobs/{id}/logs          — Retrieve stage logs
  DELETE /jobs/{id}               — Remove job and its files
  GET    /schema                  — Full JSON Schema for all parameters
  GET    /defaults                — Default configuration values
  GET    /live                    — Liveness probe
  GET    /ready                   — Readiness probe (SUMO tool availability)
  GET    /health                  — Health check (backwards-compatible shape)

Auth: when OSM2NS3_API_KEY is set, every /jobs route requires an
``X-API-Key`` header; system/config endpoints and the SPA stay public.
"""

from __future__ import annotations

import json
import logging
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.models import ConversionRequest, JobStatus, StageStatus
from app.settings import Settings, get_settings
from app.store import JobStore
from app.worker import PipelineRunner, check_tools

logger = logging.getLogger("osm2ns3.api")

_UPLOAD_CHUNK = 1 << 20  # 1 MiB


# ── Dependencies ──────────────────────────────────────────────


def get_runner(request: Request) -> PipelineRunner:
    return request.app.state.runner


def get_store(request: Request) -> JobStore:
    return request.app.state.store


async def verify_api_key(
    request: Request,
    x_api_key: str | None = Header(default=None),
) -> None:
    """No-op unless an API key is configured. Reads the settings of THE app
    handling the request (app.state), not the process-level cache, so the
    same process can host apps with different keys."""
    settings = getattr(request.app.state, "settings", None) or get_settings()
    if settings.api_key is None:
        return
    if x_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key. Send it via the X-API-Key header.",
        )


async def parse_config(config: str = Form(default="{}")) -> ConversionRequest:
    """
    Parse the JSON configuration from the multipart form field.
    Unspecified fields use their defaults (all parameters have sensible defaults).
    """
    try:
        data = json.loads(config)
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"config JSON parse error: {exc}",
        )
    try:
        return ConversionRequest(**data)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"config validation error: {exc}",
        )


# ── App factory ───────────────────────────────────────────────


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        logging.basicConfig(
            level=settings.log_level.upper(),
            format="%(asctime)s %(levelname)s %(name)s %(message)s",
        )
        settings.ensure_dirs()
        store = JobStore(
            settings.db_path,
            retention_max=settings.job_retention_max,
            retention_days=settings.job_retention_days,
        )
        await store.init()  # also recovers jobs interrupted by a restart
        app.state.settings = settings
        app.state.store = store
        app.state.runner = PipelineRunner(settings, store)
        logger.info(
            "osm2ns3 ready (data_dir=%s, auth=%s)",
            settings.data_dir,
            "on" if settings.api_key else "off",
        )
        yield

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
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # All /jobs routes are behind the (env-enabled) API-key check.
    jobs_router = APIRouter(
        prefix="/jobs",
        tags=["jobs"],
        dependencies=[Depends(verify_api_key)],
    )

    # ── System routes (public) ────────────────────────────────

    @app.get("/live", tags=["system"])
    async def live():
        """Liveness probe — always ok while the process serves requests."""
        return {"status": "ok"}

    @app.get("/ready", tags=["system"])
    async def ready():
        """Readiness probe — 200 when every SUMO tool the pipeline needs is
        available, 503 with the availability map otherwise."""
        tools = check_tools(settings.resolve_sumo_home())
        all_ok = all(tools.values())
        payload = {
            "status": "ready" if all_ok else "not_ready",
            "tools": tools,
            "pipeline_ready": all_ok,
        }
        # Backwards-compatible alias consumed by the frontend health strip.
        payload["tools_available"] = all_ok
        return JSONResponse(payload, status_code=status.HTTP_200_OK if all_ok else 503)

    @app.get("/health", tags=["system"])
    async def health():
        """Backwards-compatible health check (same info as /ready, always 200)."""
        tools = check_tools(settings.resolve_sumo_home())
        all_ok = all(tools.values())
        return {
            "status": "ready" if all_ok else "degraded",
            "tools": tools,
            "pipeline_ready": all_ok,
        }

    @app.get("/schema", tags=["config"])
    async def get_schema():
        """
        Return the full JSON Schema for ConversionRequest.
        Use this to auto-generate forms or validate configs client-side.
        """
        return ConversionRequest.model_json_schema()

    @app.get("/defaults", tags=["config"])
    async def get_default_config():
        """Return the default configuration for all pipeline stages."""
        return ConversionRequest().model_dump()

    # ── Job routes (API-key gated) ────────────────────────────

    @jobs_router.post("", status_code=status.HTTP_202_ACCEPTED)
    async def create_conversion_job(
        osm_file: UploadFile = File(
            ..., description="OpenStreetMap .osm or .osm.pbf file"
        ),
        config: ConversionRequest = Depends(parse_config),
        runner: PipelineRunner = Depends(get_runner),
    ):
        """
        Start an OSM → NS-3 conversion job.

        **Multipart form fields:**
        - `osm_file` — the `.osm` file to convert
        - `config`   — JSON string with pipeline parameters (partial or full).
                       Omitted fields use defaults. See `/defaults` and `/schema`.

        **Returns:** job_id for polling via `GET /jobs/{id}`
        """
        if not osm_file.filename:
            raise HTTPException(status_code=400, detail="No filename provided.")

        suffix = Path(osm_file.filename).suffix.lower()
        if suffix not in (".osm", ".xml", ".pbf"):
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type '{suffix}'. Upload a .osm file.",
            )

        # Stream the upload to disk in chunks with a size cap — never load
        # the whole file into memory. The job id is generated up-front so
        # the upload filename matches; no DB row exists until the file is
        # safely on disk.
        job_id = str(uuid.uuid4())
        upload_path = settings.upload_dir / f"{job_id}{suffix}"
        limit = settings.max_upload_mb * 1024 * 1024
        size = 0
        try:
            async with aiofiles.open(upload_path, "wb") as fh:
                while chunk := await osm_file.read(_UPLOAD_CHUNK):
                    size += len(chunk)
                    if size > limit:
                        raise HTTPException(
                            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                            detail=(
                                f"Upload exceeds the {settings.max_upload_mb} MB limit "
                                f"(OSM2NS3_MAX_UPLOAD_MB)."
                            ),
                        )
                    await fh.write(chunk)
        except Exception:
            upload_path.unlink(missing_ok=True)
            raise
        finally:
            await osm_file.close()

        logger.info("uploaded %s (%d bytes) → job %s", osm_file.filename, size, job_id)

        # Persist the job row (with config snapshot) and launch the pipeline.
        await runner.create_and_launch(upload_path, config, job_id=job_id)

        return {
            "job_id": job_id,
            "message": "Job accepted. Poll GET /jobs/{job_id} for status.",
            "config_snapshot": config.model_dump(),
        }

    @jobs_router.get("", response_model=list[JobStatus])
    async def list_all_jobs(store: JobStore = Depends(get_store)):
        """List all jobs (most recent first)."""
        jobs = await store.list()
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return jobs

    @jobs_router.get("/{job_id}", response_model=JobStatus)
    async def get_job_status(job_id: str, store: JobStore = Depends(get_store)):
        """
        Poll the status of a conversion job.

        **Stage order:**
        1. `netconvert`   — OSM → SUMO network
        2. `random_trips` — Generate vehicle trips
        3. `duarouter`    — Compute routes
        4. `sumo`         — Run traffic simulation
        5. `trace_export` — Export NS-3 mobility traces

        **Status values:** `pending` → `running` → `done` | `failed` | `cancelled`
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        return job

    @jobs_router.post(
        "/{job_id}/cancel",
        response_model=JobStatus,
        status_code=status.HTTP_202_ACCEPTED,
    )
    async def cancel_job(job_id: str, runner: PipelineRunner = Depends(get_runner)):
        """Cancel a pending or running job (kills its subprocess tree)."""
        try:
            await runner.cancel(job_id)
        except LookupError:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        job = await runner.store.get(job_id)
        if job.status != StageStatus.cancelled:
            raise HTTPException(
                status_code=409,
                detail=f"Job is not running (status: {job.status.value}).",
            )
        return job

    @jobs_router.get("/{job_id}/config")
    async def get_job_config(job_id: str, store: JobStore = Depends(get_store)):
        """Retrieve the exact configuration used for a job."""
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")
        cfg = await store.get_config(job_id)
        if cfg is None:
            raise HTTPException(
                status_code=404, detail="Config not found for this job."
            )
        return cfg

    @jobs_router.get("/{job_id}/files")
    async def list_job_files(job_id: str, store: JobStore = Depends(get_store)):
        """List all output files available for download."""
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        out_dir = settings.out_dir / job_id
        if not out_dir.exists():
            return {"job_id": job_id, "files": []}

        files = []
        for f in sorted(out_dir.iterdir()):
            files.append(
                {
                    "filename": f.name,
                    "size_bytes": f.stat().st_size,
                    "download_url": f"/jobs/{job_id}/download/{f.name}",
                }
            )
        return {"job_id": job_id, "files": files}

    @jobs_router.get("/{job_id}/download/{filename}")
    async def download_output(
        job_id: str, filename: str, store: JobStore = Depends(get_store)
    ):
        """
        Download an output file.

        Common files produced:
        - `ns_movements`   — NS-3 Ns2MobilityHelper trace
        - `mobility.tcl`   — NS-2/NS-3 TCL Setdest trace
        - `tripinfo.xml`   — Per-vehicle trip statistics
        - `summary.xml`    — Per-step network statistics
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        file_path = settings.out_dir / job_id / filename
        if not file_path.exists():
            raise HTTPException(status_code=404, detail=f"File '{filename}' not found.")

        # Sanitise path traversal
        try:
            file_path.resolve().relative_to((settings.out_dir / job_id).resolve())
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid filename.")

        return FileResponse(
            path=str(file_path),
            filename=filename,
            media_type="application/octet-stream",
        )

    @jobs_router.get("/{job_id}/logs")
    async def get_job_logs(job_id: str, store: JobStore = Depends(get_store)):
        """
        Retrieve SUMO tool output logs captured during the job.
        Useful for debugging parameter choices.
        """
        job = await store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        logs_dir = settings.jobs_dir / job_id
        logs = {}
        for stage in ["netconvert", "duarouter", "sumo", "traceExporter"]:
            # New pipeline writes {stage}.log using stage names; traceExporter
            # is kept as the historical alias for trace_export coverage.
            for candidate in (
                [logs_dir / f"{stage}.log"]
                if stage != "traceExporter"
                else [logs_dir / "trace_export.log", logs_dir / "traceExporter.log"]
            ):
                if candidate.exists():
                    logs[stage] = candidate.read_text()
                    break
            else:
                logs[stage] = None

        return {
            "job_id": job_id,
            "warnings": job.warnings,
            "stage_logs": logs,
        }

    @jobs_router.delete("/{job_id}", status_code=status.HTTP_204_NO_CONTENT)
    async def delete_job(job_id: str, runner: PipelineRunner = Depends(get_runner)):
        """Delete a job and all its associated files."""
        job = await runner.store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found.")

        if job.status in (StageStatus.pending, StageStatus.running):
            raise HTTPException(
                status_code=409,
                detail="Cannot delete a running job. Cancel it first.",
            )

        await runner.delete(job_id)
        logger.info("job %s deleted", job_id)

    app.include_router(jobs_router)

    # ── Static SPA (Docker image ships frontend/dist here) ────
    # Registered LAST so API routes and /docs always win.
    if settings.static_dir.exists():

        @app.exception_handler(404)
        async def spa_fallback(request: Request, exc: HTTPException):
            """Serve index.html for client-side routes (/jobs/{id} deep links)."""
            if request.url.path.startswith(
                (
                    "/jobs",
                    "/schema",
                    "/defaults",
                    "/health",
                    "/live",
                    "/ready",
                    "/docs",
                    "/redoc",
                    "/openapi.json",
                )
            ):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            index = settings.static_dir / "index.html"
            if index.exists():
                return FileResponse(index)
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        app.mount(
            "/",
            StaticFiles(directory=str(settings.static_dir), html=True),
            name="spa",
        )

    return app


app = create_app()
