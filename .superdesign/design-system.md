# Design System — OSM → NS-3 Mobility Trace Converter (Frontend)

## Product Context
Web frontend for an **OSM → NS-3 Mobility Trace Conversion** service (FastAPI + SUMO pipeline). The backend converts OpenStreetMap files into NS-3 mobility traces (`ns_movements`, `mobility.tcl`) via a 5-stage pipeline, and exposes a CORS-enabled REST API.

**Audience:** network-simulation researchers, VANET engineers, and developers. Technically literate; they think in terms of pipeline stages, parameters, logs, and traces. The UI must feel precise, structured, and trustworthy — like good engineering tooling.

**Core job (JTBD):** Upload an OSM file → configure the pipeline → watch it run → download NS-3 traces.

## Visual Direction: "Reality-First" (Poster-Modernist Technical)
Rejects SaaS fluff in favor of a structured, modernist, technical aesthetic. Strict grid, monochromatic base with a single vibrant accent, heavy typographic contrast, flat surfaces. Establishes authority and clarity.

### Palette
| Token | Hex | Usage |
|-------|-----|-------|
| `--bg` | `#E3E2DE` | Primary background (warm cream) |
| `--surface` | `#EDECEA` | Elevated surface / card fill (slightly lighter than bg) |
| `--ink` | `#141414` | Primary text (jet black) |
| `--ink-2` | `#444343` | Secondary text (deep gray) |
| `--muted` | `#7A7A7A` | Labels, metadata, muted text |
| `--line` | `#C7C7C7` | Borders, dividers, grid lines (1px solid) |
| `--accent` | `#1351AA` | Primary accent (cobalt blue) — links, primary actions, active states |
| `--accent-ink` | `#E3E2DE` | Text on accent fills |

**Functional status tokens (restrained, functional only):**
- `--status-pending`: `#7A7A7A` (muted gray)
- `--status-running`: `#1351AA` (cobalt — matches accent; pulse animation)
- `--status-done`: `#1E7A46` (muted green — success)
- `--status-failed`: `#B4231F` (muted red — failure)
- `--status-skipped`: `#9A9A9A`

### Typography
- **Headings / Display:** `'Inter'` (sans-serif), weight 700–900, tight tracking (`letter-spacing: -0.03em`), line-height 0.9. May use uppercase for section headers.
- **Body:** `'Inter'`, weight 400–500, 14–16px, line-height 1.5, color `--ink-2`.
- **Technical / Metadata:** `'JetBrains Mono'` (monospace) — endpoints, job IDs, durations, stage names, file names, status tags. Uppercase, tracked out (`letter-spacing: 0.15em`), 11–13px, color `--muted`.
- For React+Tailwind: load `Inter` + `JetBrains Mono` via Google Fonts in `index.html`.

### Structural Elements
- **Grid:** Strict 12-column layout. Reserve left 3 columns for section labels/metadata; main content in columns 4–12 (the "Label Sidebar" pattern).
- **Borders:** 1px solid `--line` to separate every section, card, row, and cell. This is the primary depth mechanism.
- **Corners:** **0px border-radius throughout** (sharp, technical, poster-modernist). No exceptions for cards/buttons/panels. (Inputs may use 0px as well — keep it consistent.)
- **Shadows:** **None.** Use flat color blocks and 1px borders for separation, never drop shadows. (The only allowed "depth" is a subtle background-tint hover.)
- **Motion:** Fast, linear transitions (0.2–0.3s) for color changes only. No bouncy/organic easing. Status dots may pulse.

### Navigation / Shell
- Sticky top bar, ~64–80px, cream bg at 95% opacity with subtle backdrop-blur, 1px bottom border `--line`.
- 12-col grid: columns 1–3 = logo (uppercase, bold, tracking-tight, e.g. `OSM→NS3` with a small black square mark). Columns 4–9 = empty or a system-status indicator. Columns 10–12 = right-aligned nav links (text-sm, font-semibold, uppercase tracked).
- Pages: **Dashboard**, **New Job**, **Jobs/Detail**, **System**.

### Key Components (Petite-Vue / HTML for drafts)
- **Poster Button:** rectangular, 0px radius, padding 14px 28px, 13px bold uppercase tracked label. Primary = `--accent` fill / `--accent-ink` text; hover → `--ink` fill. Secondary = `--ink` fill / cream text, or transparent with 1px `--line` border + `--ink` text, hover → `--surface` bg. Ghost = text-only underline on hover.
- **Mono Status Tag:** flex row, mono uppercase 10–11px tracked, with a 6px dot. Color = status token. e.g. `● RUNNING` (cobalt, pulsing).
- **Job Row / Table:** full-width rows separated by 1px top border. Columns: Job ID (mono, truncated), Status (tag), Created (mono), Stages mini-progress (5 ticks), Actions (View / Delete). Hover → `--surface` bg. Alternating subtle tone optional (white/#EDECEA vs cream).
- **Pipeline Stepper:** horizontal 5-step track — `netconvert → random_trips → duarouter → sumo → trace_export`. Each step shows index, mono stage name, and a status dot/bar. Current step = cobalt + pulse; done = green check; failed = red; pending = gray. Connect with 1px lines.
- **Config Section (guided):** grouped card per stage (`netconvert`, `random_trips`, `sumo`, `trace_exporter`). Each shows 3–5 key params as labeled inputs (top-aligned labels, mono field names, 1px border inputs, focus → border `--ink`). A collapsible "Advanced" region reveals remaining params. Prefill from `/defaults`.
- **Log Block:** monospace, 12–13px, 0px radius, 1px `--line` border, `--ink` on `--surface` or near-black ` #141414` block with `#EDECEA` text for stderr emphasis. Show `=== stdout ===` / `=== stderr ===` separators.
- **Health Tile:** grid of tool-availability tiles (`netconvert`, `duarouter`, `sumo`, `traceExporter.py`, `randomTrips.py`), each a status tag + availability.
- **File / Download Row:** filename (mono), size (mono, muted), download link/button.

## UX Flows & Pages (design these 4)
1. **Dashboard** — Jobs overview: header with `New Job` CTA + system-status pill; a jobs table (most recent first) with status, created-at, stage mini-progress, actions; empty/loading/error states; a compact health strip (`/health`).
2. **New Job** — Upload card (drag/drop `.osm`/`.osm.pbf` + filename display), then a guided config editor grouped by the 4 stages with collapsible advanced sections prefilled from `/defaults`; submit → `POST /jobs` (multipart) → redirect to Job Detail. Show `GET /schema`/`/defaults` usage hint.
3. **Job Detail** — Job header (ID mono, status tag, created/completed). Live **pipeline stepper** (poll `GET /jobs/{id}`). Tabs/sections: **Progress** (stepper + current stage + warnings), **Outputs** (`GET /jobs/{id}/files` → download rows), **Logs** (`GET /jobs/{id}/logs` → per-stage stdout/stderr), **Config** (`GET /jobs/{id}/config` → JSON), **Delete** action (`DELETE /jobs/{id}`, disabled while running).
4. **System** — `GET /health` view: overall `status` (`ready`/`degraded`), `pipeline_ready` flag, and a grid of SUMO tool-availability tiles. Monospace, technical, status-colored.

## API-Aware Content (use real names — do not invent)
- **Stages (order):** `netconvert`, `random_trips`, `duarouter`, `sumo`, `trace_export`.
- **Status values:** `pending` → `running` → `done` | `failed` (also `skipped`).
- **Config groups:** `netconvert`, `random_trips`, `sumo`, `trace_exporter`. Example key params: netconvert → `osm_highway_types`, `default_speed_limit`, `tl_type`, `proj_utm`; random_trips → `end`, `period`, `vehicle_class`, `seed`; sumo → `end`, `step_length`, `fcd_output_period`, `default_max_speed`; trace_exporter → `output_format` (ns_movements|tcl|both), `sampling_period`, `penetration_rate`.
- **Output files:** `ns_movements`, `mobility.tcl`, `tripinfo.xml`, `summary.xml`, `fcd-output.xml`.
- **Endpoints:** `POST /jobs`, `GET /jobs`, `GET /jobs/{id}`, `GET /jobs/{id}/files`, `GET /jobs/{id}/download/{filename}`, `GET /jobs/{id}/logs`, `GET /jobs/{id}/config`, `DELETE /jobs/{id}`, `GET /health`, `GET /schema`, `GET /defaults`.

## Implementation Notes (React + Tailwind + Vite)
- Tailwind theme extend tokens: `bg`, `surface`, `ink`, `ink-2`, `muted`, `line`, `accent`, `accent-ink`, plus status colors. Set `borderRadius` default to 0.
- Fonts: `Inter` (sans) + `JetBrains Mono` (mono) via Google Fonts in `index.html`.
- Use 1px `--line` borders + background tints for all separation; **never** drop shadows.
- Mono utility class for technical text (`font-mono uppercase tracking-[0.15em] text-[11px] text-muted`).
