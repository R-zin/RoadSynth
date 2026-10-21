# ── Stage 1: build the frontend ──────────────────────────────────────────────
FROM node:20-slim AS frontend
WORKDIR /fe
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ── Stage 2: runtime (Ubuntu + SUMO + backend + built frontend) ─────────────
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      python3 python3-pip python3-venv \
      sumo sumo-tools \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python deps in a venv.
RUN python3 -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
COPY requirements.txt ./
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# Backend + built SPA served by FastAPI's StaticFiles mount.
COPY main.py ./
COPY app/ ./app/
COPY --from=frontend /fe/dist ./static

# Non-root user; data (jobs.db + uploads/outputs) lives on a volume.
RUN useradd --create-home --uid 10001 appuser \
 && mkdir -p /data \
 && chown -R appuser:appuser /data /app
USER appuser

VOLUME /data
ENV OSM2NS3_DATA_DIR=/data \
    OSM2NS3_STATIC_DIR=/app/static \
    SUMO_HOME=/usr/share/sumo

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
