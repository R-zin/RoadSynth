# osm2ns3

A FastAPI service that converts **OpenStreetMap files into NS-3 mobility traces** via the full SUMO toolchain. Every parameter of every pipeline stage is exposed over a REST API with strict Pydantic validation and fully async execution.

```
OSM file  →  netconvert  →  randomTrips  →  duarouter  →  SUMO  →  traceExporter  →  ns_movements / .tcl
```

---

## Features

- **74 tunable parameters** across all four pipeline stages (26 netconvert, 14 randomTrips, 23 SUMO, 11 traceExporter)
- **14 cross-field validators** — catches impossible configurations before SUMO ever runs (e.g. `fcd_output_period` must be a whole multiple of `step_length`, `sumo.end` cannot exceed `random_trips.end`, `default_decel` cannot exceed `default_emergency_decel`)
- **Fully async pipeline** — all subprocess calls use `asyncio.create_subprocess_exec`, all file I/O uses `aiofiles`; the event loop is never blocked
- **Background jobs with live polling** — submit a job, poll `/jobs/{id}` for per-stage progress
- **Per-stage logs persisted to disk** — fetch stdout/stderr for any stage via `/jobs/{id}/logs`
- **Two output formats** — `ns_movements` (NS-3 `Ns2MobilityHelper`) and/or `mobility.tcl` (NS-2 TCL Setdest)
- **JSON Schema export** — `GET /schema` returns the complete parameter schema; use it to auto-generate forms or validate configs client-side
- Interactive API docs at `/docs` (Swagger UI) and `/redoc`

---

## Requirements

**Python:** 3.10+

**Python packages:**
```
fastapi
uvicorn[standard]
python-multipart
aiofiles
pydantic>=2.0
```

**SUMO tools** (must be on `PATH` or set `SUMO_HOME`):
| Tool | Purpose |
|------|---------|
| `netconvert` | OSM → SUMO network |
| `duarouter` | Shortest-path route computation |
| `sumo` | Microscopic traffic simulation |
| `randomTrips.py` | Trip generation (ships with SUMO) |
| `traceExporter.py` | Mobility trace export (ships with SUMO) |

Install SUMO: https://sumo.dlr.de/docs/Installing/index.html

On Ubuntu/Debian:
```bash
sudo add-apt-repository ppa:sumo/stable
sudo apt update && sudo apt install sumo sumo-tools
```

---

## Installation

```bash
git clone https://github.com/your-username/osm2ns3.git
cd osm2ns3
pip install -r requirements.txt
```

**`requirements.txt`**
```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9
aiofiles>=23.0.0
pydantic>=2.0.0
```

---

## Running

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000/docs** for the interactive Swagger UI.

If SUMO is installed at a non-standard path:
```bash
export SUMO_HOME=/opt/sumo
uvicorn app.main:app --reload
```

---

## Quick Start

### 1. Check the server is ready

```bash
curl http://localhost:8000/health
```

```json
{
  "status": "ready",
  "tools": {
    "netconvert": true,
    "duarouter": true,
    "sumo": true,
    "traceExporter.py": true,
    "randomTrips.py": true
  },
  "pipeline_ready": true
}
```

### 2. Submit a conversion job

```bash
curl -X POST http://localhost:8000/jobs \
  -F "osm_file=@kochi.osm" \
  -F 'config={
    "random_trips": {
      "end": 1800,
      "period": 1.5,
      "vehicle_class": "passenger",
      "min_distance": 200
    },
    "sumo": {
      "step_length": 0.1,
      "fcd_output_period": 1.0,
      "seed": 12345
    },
    "trace_exporter": {
      "output_format": "both",
      "sampling_period": 1.0,
      "penetration_rate": 0.8
    }
  }'
```

```json
{
  "job_id": "3f2a1c7e-...",
  "message": "Job accepted. Poll GET /jobs/3f2a1c7e-... for status."
}
```

### 3. Poll for progress

```bash
curl http://localhost:8000/jobs/3f2a1c7e-...
```

```json
{
  "job_id": "3f2a1c7e-...",
  "status": "running",
  "current_stage": "sumo",
  "stages": {
    "netconvert":   "done",
    "random_trips": "done",
    "duarouter":    "done",
    "sumo":         "running",
    "trace_export": "pending"
  }
}
```

### 4. Download outputs

```bash
# List available files
curl http://localhost:8000/jobs/3f2a1c7e-.../files

# Download NS-3 mobility trace
curl -O http://localhost:8000/jobs/3f2a1c7e-.../download/ns_movements

# Download TCL trace
curl -O http://localhost:8000/jobs/3f2a1c7e-.../download/mobility.tcl
```

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | SUMO tool availability check |
| `GET` | `/schema` | Full JSON Schema for all 74 parameters |
| `GET` | `/defaults` | Default values for every parameter |
| `POST` | `/jobs` | Submit OSM file + config, returns `job_id` |
| `GET` | `/jobs` | List all jobs, newest first |
| `GET` | `/jobs/{id}` | Job status + per-stage progress |
| `GET` | `/jobs/{id}/config` | Exact config used for a job |
| `GET` | `/jobs/{id}/files` | List downloadable output files |
| `GET` | `/jobs/{id}/download/{file}` | Download an output file |
| `GET` | `/jobs/{id}/logs` | Per-stage stdout/stderr logs |
| `DELETE` | `/jobs/{id}` | Delete job and all its files |

---

## Parameters

All parameters are optional — omitted fields use validated defaults. Submit any subset as JSON in the `config` form field.

### Stage 1 — `netconvert` (26 parameters)

Controls how the OSM file is converted to a SUMO road network.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `osm_highway_types` | `["motorway","trunk","primary","secondary","tertiary","residential","living_street","unclassified"]` | OSM highway tag values to import. Must be non-empty; each must be a known SUMO highway type. |
| `osm_remove_isolated_edges` | `true` | Remove edges not reachable from the main network. |
| `osm_no_large_roundabouts` | `false` | Skip large-roundabout guessing (faster, less accurate). |
| `osm_oneway_spread` | `false` | Give one-way roads a physical gap (doubles edge count). |
| `geometry_remove_isolated_nodes` | `true` | Remove degree-0 nodes. |
| `geometry_no_internal_links` | `false` | Omit internal junction links (vehicles teleport through intersections). |
| `junctions_internal_link_detail` | `5` | Geometry points inside junctions. Range: 1–20. |
| `junctions_corner_detail` | `5` | Geometry points for corner curves. Range: 1–20. |
| `default_junction_type` | `"priority"` | Right-of-way rule. One of: `priority`, `traffic_light`, `right_before_left`, `unregulated`, `allway_stop`, `zipper`. |
| `junctions_min_size` | `1.5` | Minimum junction radius in metres. Range: 0–20. |
| `junctions_limit_turn_speed` | `5.5` | Speed cap on sharp turns (m/s). 0 = disabled. Range: 0–30. |
| `default_lane_width` | `3.2` | Lane width in metres. Range: 1–10. |
| `default_speed_limit` | `13.9` | Speed limit in m/s (13.9 ≈ 50 km/h). Range: 1–83.3. |
| `default_num_lanes` | `1` | Lane count when OSM data is absent. Range: 1–8. |
| `no_turnarounds` | `false` | Disallow U-turns at dead ends. |
| `no_left_connections` | `false` | Disallow left-turn connections. |
| `tl_guess` | `true` | Auto-assign traffic lights to large junctions. |
| `tl_type` | `"static"` | TL algorithm. One of: `static`, `actuated`, `delay_based`, `SOTL_PHASE`, `SOTL_PLATOON`. |
| `tl_join` | `false` | Merge nearby TL junctions into one programme. |
| `tl_min_dur` | `5` | Minimum green phase in seconds. Range: 1–120. **Must be < `tl_max_dur`.** |
| `tl_max_dur` | `50` | Maximum green phase in seconds. Range: 5–300. |
| `keep_edges_by_vclass` | `null` | Retain only edges for this vehicle class. One of: `passenger`, `bus`, `truck`, `motorcycle`, `bicycle`, `pedestrian`, … |
| `remove_edges_by_type` | `null` | Comma-separated OSM types to discard (e.g. `"footway,cycleway"`). |
| `keep_fringe` | `"all"` | `"all"` keeps fringe edges; `"noFringe"` removes them. |
| `proj_utm` | `true` | Use UTM projection. **Mutually exclusive with `proj_plain_geo`.** |
| `proj_plain_geo` | `false` | Keep raw WGS84 coordinates (degrees, not metres — not suitable for NS-3). |

### Stage 2 — `random_trips` (14 parameters)

Controls vehicle count, timing, and spatial distribution.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `begin` | `0.0` | Trip generation start in seconds. **Must be < `end`.** |
| `end` | `3600.0` | Trip generation end in seconds. |
| `period` | `2.0` | Mean inter-departure gap in seconds (1/period ≈ insertion rate). Range: 0.1–3600. |
| `insertion_density` | `null` | Vehicles/hour/km of road. Overrides `period` when set. |
| `vehicle_class` | `"passenger"` | SUMO vehicle class for all trips. |
| `min_distance` | `300.0` | Minimum trip Euclidean distance in metres. |
| `max_distance` | `null` | Maximum trip distance in metres. **Must be > `min_distance` when set.** |
| `fringe_factor` | `1.0` | Bias toward network boundary edges as trip endpoints. Range: 0–100. |
| `fringe_threshold` | `0.0` | Minimum edge-speed fraction to qualify as a fringe edge. Range: 0–1. |
| `validate_routes` | `true` | Discard trips with no valid route. |
| `allow_loops` | `false` | Allow trips that start and end on the same edge. |
| `random_depart_pos` | `false` | Randomise departure position along origin edge. |
| `random_arrival_pos` | `false` | Randomise arrival position along destination edge. |
| `seed` | `42` | Random seed for reproducible generation. |

### Stage 3 — `sumo` (23 parameters)

Controls the microscopic traffic simulation and FCD output resolution.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `begin` | `0.0` | Simulation start in seconds. **Must be < `end`.** |
| `end` | `3600.0` | Simulation end in seconds. **Must be ≤ `random_trips.end`.** |
| `step_length` | `0.1` | Time step in seconds. 0.1 s recommended for VANET. Range: 0.01–10. |
| `default_max_speed` | `50.0` | Global vehicle speed cap in m/s. Range: 1–200. |
| `default_accel` | `2.6` | Default acceleration in m/s². Range: 0.1–20. |
| `default_decel` | `4.5` | Default deceleration in m/s². **Must be ≤ `default_emergency_decel`.** Range: 0.1–20. |
| `default_emergency_decel` | `9.0` | Maximum physical deceleration in m/s². Range: 0.1–30. |
| `default_sigma` | `0.5` | Krauss driver imperfection. 0 = perfect, 1 = maximum noise. Range: 0–1. |
| `default_tau` | `1.0` | Minimum time headway / reaction time in seconds. Range: 0.1–10. |
| `default_vehicle_length` | `5.0` | Vehicle body length in metres. Range: 1–30. |
| `default_min_gap` | `2.5` | Minimum bumper-to-bumper gap in metres. Range: 0–20. |
| `speed_mode` | `"right_of_way"` | Speed safety checks. One of: `right_of_way`, `no_checks`, `all_checks`. |
| `lanechange_mode` | `"default"` | Lane-change model. One of: `default`, `no_lc`, `strategic`. |
| `no_internal_links` | `false` | Skip junction internal links in simulation. |
| `ignore_route_errors` | `false` | Continue when a vehicle cannot follow its route. |
| `collision_action` | `"warn"` | Response to collisions. One of: `warn`, `teleport`, `remove`, `none`. |
| `lateral_resolution` | `0.0` | Sub-lane resolution in metres. 0 = standard lane model. Range: 0–5. |
| `fcd_output_period` | `0.1` | FCD write interval in seconds. **Must be a whole multiple of `step_length`.** Range: 0.01–60. |
| `fcd_output_geo` | `false` | Write FCD in WGS84 lon/lat. Keep `false` for NS-3. |
| `fcd_filter_shapes` | `false` | Restrict FCD to vehicles inside a polygon. |
| `tripinfo_output` | `true` | Emit per-vehicle trip statistics. |
| `summary_output` | `true` | Emit per-step network summary statistics. |
| `seed` | `42` | Random seed for reproducible simulation. |

### Stage 4 — `trace_exporter` (11 parameters)

Controls conversion of SUMO FCD output to NS-3 mobility traces.

| Parameter | Default | Description |
|-----------|---------|-------------|
| `output_format` | `"both"` | Output to produce. One of: `ns_movements`, `tcl`, `both`. |
| `x_offset` | `0.0` | X translation applied to all coordinates (metres). |
| `y_offset` | `0.0` | Y translation applied to all coordinates (metres). |
| `boundary` | `null` | Spatial filter as `"xMin,yMin,xMax,yMax"`. Validated: xMin < xMax, yMin < yMax. |
| `begin` | `0.0` | Export start time in seconds. |
| `end` | `null` | Export end time in seconds. **Must be > `begin`; must be ≤ `sumo.end`.** |
| `sampling_period` | `1.0` | Position update interval in seconds. **Must be ≥ `sumo.fcd_output_period` and a whole multiple of it.** Range: 0.1–60. |
| `ns2_include_speed` | `true` | Embed instantaneous speed in each output line. |
| `penetration_rate` | `1.0` | Fraction of vehicles to export. 1.0 = all; < 1.0 models partial OBU deployment. Range: 0.01–1. |
| `seed` | `42` | Random seed for vehicle sub-sampling when `penetration_rate < 1`. |
| `write_fcd_filtered` | `false` | Also write a filtered FCD XML with only exported vehicles. |

---

## Validation Rules

The API rejects invalid configurations immediately at upload time, before any SUMO tool runs.

**Within `netconvert`:**
- `osm_highway_types` must be non-empty; each entry must be a known SUMO highway type
- `remove_edges_by_type` tokens must all be known highway types
- `proj_utm` and `proj_plain_geo` are mutually exclusive
- `tl_min_dur` must be strictly less than `tl_max_dur`

**Within `random_trips`:**
- `begin` < `end`
- `max_distance` > `min_distance` (when set)

**Within `sumo`:**
- `begin` < `end`
- `fcd_output_period` must be a whole multiple of `step_length`
- `default_decel` ≤ `default_emergency_decel`
- `collision_action` must be one of `warn`, `teleport`, `remove`, `none`

**Within `trace_exporter`:**
- `boundary` must match the pattern `xMin,yMin,xMax,yMax` with xMin < xMax and yMin < yMax
- `end` > `begin` (when set)

**Cross-stage:**
- `sumo.end` ≤ `random_trips.end`
- `trace_exporter.end` ≤ `sumo.end` (when set)
- `trace_exporter.sampling_period` ≥ `sumo.fcd_output_period`
- `trace_exporter.sampling_period` must be a whole multiple of `sumo.fcd_output_period`

---

## Output Files

| File | Description |
|------|-------------|
| `ns_movements` | NS-3 `Ns2MobilityHelper` trace — load with `Ns2MobilityHelper mobility("ns_movements")` |
| `mobility.tcl` | NS-2 TCL Setdest trace — also compatible with NS-3 |
| `tripinfo.xml` | Per-vehicle statistics: departure time, arrival time, route length, waiting time |
| `summary.xml` | Per-step network statistics: running vehicles, mean speed, halting count |

### Using `ns_movements` in NS-3

```cpp
MobilityHelper mobility;
Ns2MobilityHelper ns2mobility("ns_movements");
ns2mobility.Install();
```

### Using `mobility.tcl` in NS-3

```cpp
MobilityHelper mobility;
mobility.SetMobilityModel("ns3::Ns2MobilityModel",
    "TraceFile", StringValue("mobility.tcl"));
mobility.Install(nodes);
```

---

## Project Structure

```
osm2ns3/
├── app/
│   ├── main.py       # FastAPI app, all route handlers
│   ├── models.py     # Pydantic models: 74 parameters, 14 validators
│   └── pipeline.py   # Async pipeline: subprocess + aiofiles throughout
├── jobs/             # Per-job workdirs with intermediate files and .log files
├── uploads/          # Uploaded OSM files (named by job UUID)
├── outputs/          # Final output files served for download
└── requirements.txt
```

---

## Use Case: VANET Research

This tool was built for VANET (Vehicular Ad-hoc Network) simulation research where NS-3 is used to evaluate routing protocols (AODV, GPSR, etc.) over realistic urban mobility. A typical research workflow:

1. Export a city area from [OpenStreetMap](https://www.openstreetmap.org/) as `.osm`
2. Submit to this API with VANET-tuned parameters:
   - `step_length: 0.1` — matches the IEEE 802.11p 10 Hz beacon rate
   - `fcd_output_period: 1.0` — 1 s position updates in the trace
   - `sampling_period: 1.0` — consistent with FCD period
   - `vehicle_class: "passenger"` — standard private vehicles
3. Use the `ns_movements` file in NS-3 with `Ns2MobilityHelper`
4. Run protocol comparison experiments

---

## License

MIT