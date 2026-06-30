"""
Parameter models for the OSM → NS-3 conversion pipeline.

Pipeline stages:
  1. netconvert   — OSM → SUMO network (.net.xml)
  2. randomTrips  — Generate vehicle trips/routes
  3. duarouter    — Compute shortest-path routes
  4. sumo         — Run mobility simulation → fcd-output.xml
  5. traceExporter — fcd-output.xml → ns_movements / .tcl

Every configurable knob in each stage is exposed and cross-validated here.
"""

from __future__ import annotations

import math
import re
from enum import Enum
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ──────────────────────────────────────────────────────────────
# Shared enums
# ──────────────────────────────────────────────────────────────

class OutputFormat(str, Enum):
    ns_movements = "ns_movements"
    tcl          = "tcl"
    both         = "both"


class VehicleClass(str, Enum):
    passenger  = "passenger"
    bus        = "bus"
    truck      = "truck"
    motorcycle = "motorcycle"
    bicycle    = "bicycle"
    pedestrian = "pedestrian"
    emergency  = "emergency"
    authority  = "authority"
    army       = "army"
    vip        = "vip"
    hov        = "hov"
    custom1    = "custom1"
    custom2    = "custom2"


class TLType(str, Enum):
    static       = "static"
    actuated     = "actuated"
    delay_based  = "delay_based"
    sotl_phase   = "SOTL_PHASE"
    sotl_platoon = "SOTL_PLATOON"


class EdgeRemoval(str, Enum):
    all      = "all"
    noFringe = "noFringe"


class JunctionType(str, Enum):
    priority            = "priority"
    traffic_light       = "traffic_light"
    right_before_left   = "right_before_left"
    unregulated         = "unregulated"
    allway_stop         = "allway_stop"
    zipper              = "zipper"


class SpeedMode(str, Enum):
    right_of_way = "right_of_way"   # bitmask 31 — obey right-of-way
    no_checks    = "no_checks"      # bitmask 32 — ignore all checks
    all_checks   = "all_checks"     # bitmask 31 (same as right_of_way, alias)


class LaneChangeMode(str, Enum):
    default        = "default"    # 1621
    no_lc          = "no_lc"      # 0
    strategic_only = "strategic"  # 256


# Known OSM highway types accepted by netconvert
_VALID_HIGHWAY_TYPES = {
    "motorway", "motorway_link", "trunk", "trunk_link",
    "primary", "primary_link", "secondary", "secondary_link",
    "tertiary", "tertiary_link", "residential", "living_street",
    "unclassified", "service", "road", "track",
    "footway", "cycleway", "path", "steps", "pedestrian",
    "bus_guideway", "raceway", "construction",
}

_BOUNDARY_RE = re.compile(
    r"^-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?,-?\d+(\.\d+)?$"
)

_COLLISION_ACTIONS = {"warn", "teleport", "remove", "none"}


# ──────────────────────────────────────────────────────────────
# Stage 1 — netconvert
# ──────────────────────────────────────────────────────────────

class NetconvertParams(BaseModel):
    """
    Controls how the raw OSM file is converted into a SUMO road network.
    Reference: https://sumo.dlr.de/docs/netconvert.html
    """

    # ── OSM import ──────────────────────────────────────────
    osm_highway_types: List[str] = Field(
        default=["motorway", "trunk", "primary", "secondary",
                 "tertiary", "residential", "living_street", "unclassified"],
        min_length=1,
        description=(
            "OSM highway tag values to import. Must be non-empty. "
            "Drop types to reduce network size (e.g. remove 'residential' "
            "for arterial-only simulations)."
        ),
    )
    osm_remove_isolated_edges: bool = Field(
        True,
        description="Remove edges not reachable from the main network component.",
    )
    osm_no_large_roundabouts: bool = Field(
        False,
        description="Skip large-roundabout guessing (faster import, less accurate).",
    )
    osm_oneway_spread: bool = Field(
        False,
        description=(
            "Spread one-way roads to have a physical separation gap. "
            "Improves visualisation but doubles edge count on one-way streets."
        ),
    )

    # ── Network geometry ────────────────────────────────────
    geometry_remove_isolated_nodes: bool = Field(
        True,
        description="Remove degree-0 nodes with no connected edges.",
    )
    geometry_no_internal_links: bool = Field(
        False,
        description=(
            "Omit internal junction links. Vehicles teleport through "
            "intersections — faster simulation but no turn-delay modelling."
        ),
    )
    junctions_internal_link_detail: int = Field(
        5, ge=1, le=20,
        description="Geometry point count for links inside junctions.",
    )
    junctions_corner_detail: int = Field(
        5, ge=1, le=20,
        description="Geometry point count for junction corner curves.",
    )
    default_junction_type: JunctionType = Field(
        JunctionType.priority,
        description="Default right-of-way rule at intersections.",
    )
    junctions_min_size: float = Field(
        1.5, ge=0.0, le=20.0,
        description="Minimum junction radius in metres.",
    )
    junctions_limit_turn_speed: float = Field(
        5.5, ge=0.0, le=30.0,
        description="Cap speed on sharp turns (m/s). 0 = disabled.",
    )

    # ── Lane / road ─────────────────────────────────────────
    default_lane_width: float = Field(
        3.2, ge=1.0, le=10.0,
        description="Default lane width in metres.",
    )
    default_speed_limit: float = Field(
        13.9, ge=1.0, le=83.3,
        description="Default speed limit in m/s (13.9 ≈ 50 km/h, 83.3 ≈ 300 km/h).",
    )
    default_num_lanes: int = Field(
        1, ge=1, le=8,
        description="Default lane count when OSM data is absent.",
    )
    no_turnarounds: bool = Field(
        False,
        description="Disallow U-turns at dead-end edges.",
    )
    no_left_connections: bool = Field(
        False,
        description="Disallow left-turn lane connections (right-hand-traffic only model).",
    )

    # ── Traffic lights ──────────────────────────────────────
    tl_guess: bool = Field(
        True,
        description="Auto-assign traffic lights to large junctions.",
    )
    tl_type: TLType = Field(
        TLType.static,
        description="Traffic-light controller algorithm.",
    )
    tl_join: bool = Field(
        False,
        description="Merge nearby traffic-light junctions into one programme.",
    )
    tl_min_dur: int = Field(
        5, ge=1, le=120,
        description="Minimum green-phase duration in seconds.",
    )
    tl_max_dur: int = Field(
        50, ge=5, le=300,
        description="Maximum green-phase duration in seconds.",
    )

    # ── Network cleaning ────────────────────────────────────
    keep_edges_by_vclass: Optional[VehicleClass] = Field(
        None,
        description="Retain only edges permitted for this vehicle class. None = keep all.",
    )
    remove_edges_by_type: Optional[str] = Field(
        None,
        description=(
            "Comma-separated OSM highway types to discard, e.g. "
            "'footway,cycleway,path'. Each token must be a valid highway type."
        ),
    )
    keep_fringe: EdgeRemoval = Field(
        EdgeRemoval.all,
        description=(
            "'all' keeps fringe edges (connected on one end only). "
            "'noFringe' removes them, giving a more compact network."
        ),
    )

    # ── Projection ──────────────────────────────────────────
    proj_utm: bool = Field(
        True,
        description=(
            "Use UTM projection (metric, recommended). "
            "Mutually exclusive with proj_plain_geo."
        ),
    )
    proj_plain_geo: bool = Field(
        False,
        description=(
            "Keep WGS84 lon/lat coordinates unchanged. "
            "Mutually exclusive with proj_utm. "
            "Distances will be in degrees — not suitable for NS-3."
        ),
    )

    # ── Validators ──────────────────────────────────────────

    @field_validator("osm_highway_types")
    @classmethod
    def validate_highway_types(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("osm_highway_types must contain at least one entry.")
        invalid = [t for t in v if t not in _VALID_HIGHWAY_TYPES]
        if invalid:
            raise ValueError(
                f"Unknown highway type(s): {invalid}. "
                f"Valid types: {sorted(_VALID_HIGHWAY_TYPES)}"
            )
        return v

    @field_validator("remove_edges_by_type")
    @classmethod
    def validate_remove_types(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        tokens = [t.strip() for t in v.split(",") if t.strip()]
        if not tokens:
            raise ValueError("remove_edges_by_type is empty after splitting on ','.")
        invalid = [t for t in tokens if t not in _VALID_HIGHWAY_TYPES]
        if invalid:
            raise ValueError(
                f"remove_edges_by_type contains unknown types: {invalid}."
            )
        return ",".join(tokens)

    @model_validator(mode="after")
    def check_projection_mutual_exclusion(self) -> "NetconvertParams":
        if self.proj_utm and self.proj_plain_geo:
            raise ValueError(
                "proj_utm and proj_plain_geo are mutually exclusive — "
                "enable exactly one."
            )
        return self

    @model_validator(mode="after")
    def check_tl_durations(self) -> "NetconvertParams":
        if self.tl_min_dur >= self.tl_max_dur:
            raise ValueError(
                f"tl_min_dur ({self.tl_min_dur}) must be strictly less than "
                f"tl_max_dur ({self.tl_max_dur})."
            )
        return self


# ──────────────────────────────────────────────────────────────
# Stage 2 — randomTrips / route generation
# ──────────────────────────────────────────────────────────────

class RandomTripsParams(BaseModel):
    """
    Controls vehicle trip and route generation via SUMO's randomTrips.py.
    Reference: https://sumo.dlr.de/docs/Tools/Trip.html
    """

    begin: float = Field(
        0.0, ge=0.0,
        description="Trip generation start time in seconds.",
    )
    end: float = Field(
        3600.0, ge=1.0,
        description="Trip generation end time in seconds. Must be > begin.",
    )
    period: float = Field(
        2.0, ge=0.1, le=3600.0,
        description=(
            "Mean inter-departure gap in seconds. "
            "1/period ≈ vehicle insertion rate. "
            "Ignored when insertion_density is set."
        ),
    )
    insertion_density: Optional[float] = Field(
        None, ge=0.0,
        description=(
            "Vehicles inserted per hour per km of road. "
            "Overrides period when provided."
        ),
    )
    vehicle_class: VehicleClass = Field(
        VehicleClass.passenger,
        description="SUMO vehicle class assigned to all generated trips.",
    )
    min_distance: float = Field(
        300.0, ge=0.0,
        description="Minimum Euclidean trip distance in metres.",
    )
    max_distance: Optional[float] = Field(
        None, ge=0.0,
        description="Maximum trip distance in metres. None = unlimited.",
    )
    fringe_factor: float = Field(
        1.0, ge=0.0, le=100.0,
        description=(
            "Bias weight for selecting fringe edges as trip endpoints. "
            ">1 makes trips more likely to originate/terminate at network edges."
        ),
    )
    fringe_threshold: float = Field(
        0.0, ge=0.0, le=1.0,
        description=(
            "Minimum edge-speed fraction (relative to max network speed) "
            "to qualify as a fringe edge."
        ),
    )
    validate_routes: bool = Field(
        True,
        description="Discard trips that produce no valid route through the network.",
    )
    allow_loops: bool = Field(
        False,
        description="Allow trips that start and end on the same edge.",
    )
    random_depart_pos: bool = Field(
        False,
        description="Randomise departure position along the origin edge.",
    )
    random_arrival_pos: bool = Field(
        False,
        description="Randomise arrival position along the destination edge.",
    )
    seed: int = Field(
        42, ge=0,
        description="Random seed for reproducible trip generation.",
    )

    # ── Validators ──────────────────────────────────────────

    @model_validator(mode="after")
    def check_timeline(self) -> "RandomTripsParams":
        if self.begin >= self.end:
            raise ValueError(
                f"begin ({self.begin}) must be strictly less than end ({self.end})."
            )
        return self

    @model_validator(mode="after")
    def check_distance_bounds(self) -> "RandomTripsParams":
        if self.max_distance is not None and self.max_distance <= self.min_distance:
            raise ValueError(
                f"max_distance ({self.max_distance}) must be greater than "
                f"min_distance ({self.min_distance})."
            )
        return self


# ──────────────────────────────────────────────────────────────
# Stage 3+4 — SUMO simulation
# ──────────────────────────────────────────────────────────────

class SumoParams(BaseModel):
    """
    Controls the SUMO microscopic traffic simulation.
    Reference: https://sumo.dlr.de/docs/SUMO.html
    """

    begin: float = Field(
        0.0, ge=0.0,
        description="Simulation begin time in seconds.",
    )
    end: float = Field(
        3600.0, ge=1.0,
        description="Simulation end time in seconds. Must be > begin.",
    )
    step_length: float = Field(
        0.1, ge=0.01, le=10.0,
        description=(
            "Simulation time step in seconds. "
            "0.1 s recommended for VANET (matches 802.11p beacon rate). "
            "fcd_output_period must be a whole multiple of this value."
        ),
    )

    # ── Vehicle behaviour ────────────────────────────────────
    default_max_speed: float = Field(
        50.0, ge=1.0, le=200.0,
        description="Global maximum vehicle speed cap in m/s.",
    )
    default_accel: float = Field(
        2.6, ge=0.1, le=20.0,
        description="Default vehicle acceleration in m/s².",
    )
    default_decel: float = Field(
        4.5, ge=0.1, le=20.0,
        description=(
            "Default comfortable deceleration in m/s². "
            "Must be ≤ default_emergency_decel."
        ),
    )
    default_emergency_decel: float = Field(
        9.0, ge=0.1, le=30.0,
        description=(
            "Physical maximum deceleration in m/s² (used in emergencies). "
            "Must be ≥ default_decel."
        ),
    )
    default_sigma: float = Field(
        0.5, ge=0.0, le=1.0,
        description=(
            "Krauss driver imperfection factor. "
            "0.0 = perfect driver, 1.0 = maximum randomness."
        ),
    )
    default_tau: float = Field(
        1.0, ge=0.1, le=10.0,
        description="Minimum time headway / reaction time in seconds.",
    )
    default_vehicle_length: float = Field(
        5.0, ge=1.0, le=30.0,
        description="Default vehicle body length in metres.",
    )
    default_min_gap: float = Field(
        2.5, ge=0.0, le=20.0,
        description="Minimum bumper-to-bumper gap to the vehicle ahead in metres.",
    )

    # ── Speed / lane-change models ───────────────────────────
    speed_mode: SpeedMode = Field(
        SpeedMode.right_of_way,
        description=(
            "Speed regulation bitmask preset. "
            "'right_of_way' enforces junction right-of-way rules. "
            "'no_checks' removes all speed safety checks."
        ),
    )
    lanechange_mode: LaneChangeMode = Field(
        LaneChangeMode.default,
        description="Lane-change behaviour model.",
    )

    # ── Network / simulation processing ─────────────────────
    no_internal_links: bool = Field(
        False,
        description="Skip internal junction links (vehicles teleport through junctions).",
    )
    ignore_route_errors: bool = Field(
        False,
        description="Continue simulation when a vehicle cannot follow its route.",
    )
    collision_action: str = Field(
        "warn",
        description=(
            "Response to vehicle collisions. "
            "One of: 'warn', 'teleport', 'remove', 'none'."
        ),
    )
    lateral_resolution: float = Field(
        0.0, ge=0.0, le=5.0,
        description=(
            "Sub-lane lateral resolution in metres (0 = standard lane model). "
            "Enables fine-grained lateral position tracking."
        ),
    )

    # ── FCD output ───────────────────────────────────────────
    fcd_output_period: float = Field(
        0.1, ge=0.01, le=60.0,
        description=(
            "Floating Car Data write interval in seconds. "
            "Must be a whole multiple of step_length. "
            "Directly controls temporal resolution of the NS-3 trace."
        ),
    )
    fcd_output_geo: bool = Field(
        False,
        description=(
            "Write FCD in WGS84 lon/lat instead of Cartesian x/y. "
            "Keep False for NS-3 — it expects metric Cartesian coordinates."
        ),
    )
    fcd_filter_shapes: bool = Field(
        False,
        description="Restrict FCD output to vehicles inside a polygon (requires shape file).",
    )
    tripinfo_output: bool = Field(
        True,
        description="Emit per-vehicle trip statistics (departure, arrival, route length, etc.).",
    )
    summary_output: bool = Field(
        True,
        description="Emit per-step network-wide summary statistics.",
    )
    seed: int = Field(
        42, ge=0,
        description="Random seed for reproducible SUMO runs.",
    )

    # ── Validators ──────────────────────────────────────────

    @field_validator("collision_action")
    @classmethod
    def validate_collision_action(cls, v: str) -> str:
        if v not in _COLLISION_ACTIONS:
            raise ValueError(
                f"collision_action must be one of {sorted(_COLLISION_ACTIONS)}, got '{v}'."
            )
        return v

    @model_validator(mode="after")
    def check_timeline(self) -> "SumoParams":
        if self.begin >= self.end:
            raise ValueError(
                f"begin ({self.begin}) must be strictly less than end ({self.end})."
            )
        return self

    @model_validator(mode="after")
    def check_fcd_period_is_multiple_of_step(self) -> "SumoParams":
        ratio = self.fcd_output_period / self.step_length
        if abs(ratio - round(ratio)) > 1e-9:
            raise ValueError(
                f"fcd_output_period ({self.fcd_output_period} s) must be a whole "
                f"multiple of step_length ({self.step_length} s). "
                f"Current ratio is {ratio:.6f} — try "
                f"{round(ratio) * self.step_length:.4f} s instead."
            )
        return self

    @model_validator(mode="after")
    def check_decel_ordering(self) -> "SumoParams":
        if self.default_decel > self.default_emergency_decel:
            raise ValueError(
                f"default_decel ({self.default_decel} m/s²) cannot exceed "
                f"default_emergency_decel ({self.default_emergency_decel} m/s²). "
                "Emergency braking must be at least as strong as normal braking."
            )
        return self


# ──────────────────────────────────────────────────────────────
# Stage 5 — traceExporter
# ──────────────────────────────────────────────────────────────

class TraceExporterParams(BaseModel):
    """
    Controls conversion of SUMO FCD output to NS-2/NS-3 mobility traces.
    Reference: https://sumo.dlr.de/docs/Tools/TraceExporter.html
    """

    output_format: OutputFormat = Field(
        OutputFormat.both,
        description=(
            "Output format(s). "
            "'ns_movements' → NS-3 Ns2MobilityHelper format. "
            "'tcl' → NS-2 TCL Setdest format (also usable in NS-3). "
            "'both' → produce both files."
        ),
    )

    # ── Spatial ─────────────────────────────────────────────
    x_offset: float = Field(
        0.0,
        description="X translation applied to all exported coordinates (metres).",
    )
    y_offset: float = Field(
        0.0,
        description="Y translation applied to all exported coordinates (metres).",
    )
    boundary: Optional[str] = Field(
        None,
        description=(
            "Spatial filter as 'xMin,yMin,xMax,yMax' (four floats, comma-separated). "
            "Only vehicles inside this rectangle are exported. "
            "Coordinates are in the same system as the SUMO network (metres after UTM)."
        ),
    )

    # ── Temporal ─────────────────────────────────────────────
    begin: float = Field(
        0.0, ge=0.0,
        description="Export start time in seconds.",
    )
    end: Optional[float] = Field(
        None,
        description="Export end time in seconds. None = match simulation end.",
    )

    # ── Sampling ─────────────────────────────────────────────
    sampling_period: float = Field(
        1.0, ge=0.1, le=60.0,
        description=(
            "Position update interval in seconds. "
            "Must be ≥ sumo.fcd_output_period. "
            "1.0 s is typical for NS-3 VANET studies."
        ),
    )

    # ── NS-3 specific ─────────────────────────────────────────
    ns2_include_speed: bool = Field(
        True,
        description="Embed instantaneous speed in each NS-2/NS-3 output line.",
    )
    penetration_rate: float = Field(
        1.0, ge=0.01, le=1.0,
        description=(
            "Fraction of vehicles to export (1.0 = all). "
            "Values < 1.0 model partial OBU/VANET device deployment."
        ),
    )
    seed: int = Field(
        42, ge=0,
        description="Random seed for vehicle sub-sampling when penetration_rate < 1.",
    )
    write_fcd_filtered: bool = Field(
        False,
        description="Also write a filtered FCD XML containing only the exported vehicles.",
    )

    # ── Validators ──────────────────────────────────────────

    @field_validator("boundary")
    @classmethod
    def validate_boundary(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        if not _BOUNDARY_RE.match(v.strip()):
            raise ValueError(
                "boundary must be four comma-separated numbers: "
                "'xMin,yMin,xMax,yMax', e.g. '0.0,0.0,5000.0,5000.0'."
            )
        parts = [float(x) for x in v.split(",")]
        x_min, y_min, x_max, y_max = parts
        if x_min >= x_max:
            raise ValueError(
                f"boundary xMin ({x_min}) must be less than xMax ({x_max})."
            )
        if y_min >= y_max:
            raise ValueError(
                f"boundary yMin ({y_min}) must be less than yMax ({y_max})."
            )
        return v.strip()

    @model_validator(mode="after")
    def check_export_timeline(self) -> "TraceExporterParams":
        if self.end is not None and self.end <= self.begin:
            raise ValueError(
                f"TraceExporter end ({self.end}) must be greater than begin ({self.begin})."
            )
        return self


# ──────────────────────────────────────────────────────────────
# Top-level job request — cross-stage validation lives here
# ──────────────────────────────────────────────────────────────

class ConversionRequest(BaseModel):
    """Complete pipeline configuration submitted with the OSM file."""
    netconvert:     NetconvertParams     = Field(default_factory=NetconvertParams)
    random_trips:   RandomTripsParams    = Field(default_factory=RandomTripsParams)
    sumo:           SumoParams           = Field(default_factory=SumoParams)
    trace_exporter: TraceExporterParams  = Field(default_factory=TraceExporterParams)

    @model_validator(mode="after")
    def cross_stage_timeline(self) -> "ConversionRequest":
        """Warn / reject when stage timelines are obviously inconsistent."""
        rt_end   = self.random_trips.end
        sumo_end = self.sumo.end
        te_end   = self.trace_exporter.end

        if sumo_end > rt_end:
            raise ValueError(
                f"sumo.end ({sumo_end}) exceeds random_trips.end ({rt_end}). "
                "The simulation would run beyond the period for which vehicles exist. "
                "Set sumo.end ≤ random_trips.end."
            )
        if te_end is not None and te_end > sumo_end:
            raise ValueError(
                f"trace_exporter.end ({te_end}) exceeds sumo.end ({sumo_end}). "
                "Cannot export data beyond the simulation window."
            )
        return self

    @model_validator(mode="after")
    def cross_stage_sampling(self) -> "ConversionRequest":
        """Ensure trace sampling resolution is achievable given FCD output rate."""
        fcd_period      = self.sumo.fcd_output_period
        sampling_period = self.trace_exporter.sampling_period
        if sampling_period < fcd_period:
            raise ValueError(
                f"trace_exporter.sampling_period ({sampling_period} s) is finer than "
                f"sumo.fcd_output_period ({fcd_period} s). "
                "Cannot up-sample — set sampling_period ≥ fcd_output_period."
            )
        ratio = sampling_period / fcd_period
        if abs(ratio - round(ratio)) > 1e-9:
            raise ValueError(
                f"trace_exporter.sampling_period ({sampling_period} s) must be a "
                f"whole multiple of sumo.fcd_output_period ({fcd_period} s). "
                f"Current ratio is {ratio:.4f}."
            )
        return self


# ──────────────────────────────────────────────────────────────
# Job status types
# ──────────────────────────────────────────────────────────────

class StageStatus(str, Enum):
    pending = "pending"
    running = "running"
    done    = "done"
    failed  = "failed"
    skipped = "skipped"


class StageLog(BaseModel):
    status:   StageStatus
    stdout:   Optional[str] = None
    stderr:   Optional[str] = None
    duration: Optional[float] = None    # wall-clock seconds


class JobStatus(BaseModel):
    job_id:       str
    status:       StageStatus
    current_stage: Optional[str] = None
    stages:       dict            = Field(default_factory=dict)
    stage_logs:   dict            = Field(default_factory=dict)  # stage → StageLog
    error:        Optional[str]   = None
    outputs:      List[str]       = Field(default_factory=list)
    created_at:   str
    completed_at: Optional[str]   = None
    warnings:     List[str]       = Field(default_factory=list)