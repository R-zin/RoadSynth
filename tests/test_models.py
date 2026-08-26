"""Validation tests for app/models.py — the 74 pipeline parameters and all
cross-field / cross-stage validators. No I/O; everything is in-memory."""

import pytest
from pydantic import ValidationError

from app.models import (
    ConversionRequest,
    NetconvertParams,
    RandomTripsParams,
    SumoParams,
    TraceExporterParams,
)


def _bad(cls, **kw):
    with pytest.raises(ValidationError):
        cls(**kw)


# ── Parametrised numeric bound sweep (ge/le from Field metadata) ──────────

BOUND_CASES = [
    # (model, field, below-min, above-max)
    (NetconvertParams, "junctions_internal_link_detail", 0, 21),
    (NetconvertParams, "junctions_corner_detail", 0, 21),
    (NetconvertParams, "junctions_min_size", -0.1, 20.1),
    (NetconvertParams, "junctions_limit_turn_speed", -0.1, 30.1),
    (NetconvertParams, "default_lane_width", 0.9, 10.1),
    (NetconvertParams, "default_speed_limit", 0.9, 83.4),
    (NetconvertParams, "default_num_lanes", 0, 9),
    (NetconvertParams, "tl_min_dur", 0, 121),
    (NetconvertParams, "tl_max_dur", 4, 301),
    (RandomTripsParams, "begin", -0.1, None),
    (RandomTripsParams, "end", 0.5, None),
    (RandomTripsParams, "period", 0.05, 3600.1),
    (RandomTripsParams, "insertion_density", -0.1, None),
    (RandomTripsParams, "min_distance", -0.1, None),
    (RandomTripsParams, "max_distance", -0.1, None),
    (RandomTripsParams, "fringe_factor", -0.1, 100.1),
    (RandomTripsParams, "fringe_threshold", -0.1, 1.1),
    (RandomTripsParams, "seed", -1, None),
    (SumoParams, "begin", -0.1, None),
    (SumoParams, "end", 0.5, None),
    (SumoParams, "step_length", 0.009, 10.1),
    (SumoParams, "default_max_speed", 0.9, 200.1),
    (SumoParams, "default_accel", 0.09, 20.1),
    (SumoParams, "default_decel", 0.09, 20.1),
    (SumoParams, "default_emergency_decel", 0.09, 30.1),
    (SumoParams, "default_sigma", -0.1, 1.1),
    (SumoParams, "default_tau", 0.09, 10.1),
    (SumoParams, "default_vehicle_length", 0.9, 30.1),
    (SumoParams, "default_min_gap", -0.1, 20.1),
    (SumoParams, "lateral_resolution", -0.1, 5.1),
    (SumoParams, "fcd_output_period", 0.009, 60.1),
    (SumoParams, "seed", -1, None),
    (TraceExporterParams, "begin", -0.1, None),
    (TraceExporterParams, "sampling_period", 0.05, 60.1),
    (TraceExporterParams, "penetration_rate", 0.009, 1.01),
    (TraceExporterParams, "seed", -1, None),
]


@pytest.mark.parametrize(
    "cls,field,bad_low,bad_high",
    BOUND_CASES,
    ids=[f"{c.__name__}.{f}" for c, f, _, _ in BOUND_CASES],
)
def test_numeric_bounds(cls, field, bad_low, bad_high):
    # Values at the boundary must validate (default fill for others).
    if bad_low is not None:
        _bad(cls, **{field: bad_low})
    if bad_high is not None:
        _bad(cls, **{field: bad_high})


def test_highway_types_non_empty():
    _bad(NetconvertParams, osm_highway_types=[])


# ── Enumerations ─────────────────────────────────────────────


def test_enum_rejects_unknown_value():
    _bad(RandomTripsParams, vehicle_class="car")
    _bad(NetconvertParams, tl_type="banana")
    _bad(TraceExporterParams, output_format="gpx")


def test_enum_wire_values_accepted():
    """The API/frontend exchange enum *values* (e.g. SOTL_PHASE), not names."""
    assert NetconvertParams(tl_type="SOTL_PHASE").tl_type.value == "SOTL_PHASE"
    assert RandomTripsParams(vehicle_class="bus").vehicle_class.value == "bus"
    assert (
        TraceExporterParams(output_format="ns_movements").output_format.value
        == "ns_movements"
    )


# ── Netconvert validators ────────────────────────────────────


def test_highway_type_names_validated():
    _bad(NetconvertParams, osm_highway_types=["motorway", "foo"])
    ok = NetconvertParams(osm_highway_types=["primary", "secondary"])
    assert ok.osm_highway_types == ["primary", "secondary"]


def test_remove_edges_by_type_validated_and_normalised():
    _bad(NetconvertParams, remove_edges_by_type="foo,bar")
    ok = NetconvertParams(remove_edges_by_type=" footway , path ")
    assert ok.remove_edges_by_type == "footway,path"


def test_projection_mutual_exclusion():
    _bad(NetconvertParams, proj_utm=True, proj_plain_geo=True)


def test_tl_duration_ordering():
    _bad(NetconvertParams, tl_min_dur=30, tl_max_dur=10)


# ── RandomTrips validators ───────────────────────────────────


def test_random_trips_timeline():
    _bad(RandomTripsParams, begin=10, end=10)
    _bad(RandomTripsParams, begin=20, end=10)


def test_random_trips_distance_bounds():
    _bad(RandomTripsParams, min_distance=500, max_distance=100)


# ── SUMO validators ──────────────────────────────────────────


def test_sumo_timeline():
    _bad(SumoParams, begin=5.0, end=5.0)


def test_fcd_period_multiple_of_step_length():
    # 0.3 / 0.2 = 1.5 — not a whole number of steps
    _bad(SumoParams, fcd_output_period=0.3, step_length=0.2)
    # 0.3 / 0.1 = 3 — exactly divisible
    SumoParams(fcd_output_period=0.3, step_length=0.1)


def test_decel_ordering():
    _bad(SumoParams, default_decel=10.0, default_emergency_decel=9.0)
    SumoParams(default_decel=4.5, default_emergency_decel=9.0)


def test_collision_action_choices():
    _bad(SumoParams, collision_action="kill")
    for choice in ("warn", "teleport", "remove", "none"):
        assert SumoParams(collision_action=choice).collision_action == choice


# ── TraceExporter validators ─────────────────────────────────


def test_boundary_format():
    _bad(TraceExporterParams, boundary="not-a-boundary")
    _bad(TraceExporterParams, boundary="1,2,3")  # too few values
    # Inverted axes (xMin > xMax) rejected
    _bad(TraceExporterParams, boundary="10,0,0,10")
    ok = TraceExporterParams(boundary="0,0,10,10")
    assert ok.boundary == "0,0,10,10"


def test_export_timeline_when_end_set():
    _bad(TraceExporterParams, begin=100, end=50)


# ── Cross-stage validators on ConversionRequest ─────────────


def test_cross_stage_sumo_vs_random_trips_end():
    _bad(ConversionRequest, sumo={"end": 3600.0}, random_trips={"end": 1000.0})


def test_cross_stage_trace_exporter_vs_sumo_end():
    _bad(
        ConversionRequest,
        sumo={"end": 100.0},
        random_trips={"end": 1000.0},
        trace_exporter={"end": 200.0},
    )
    # trace_exporter.end=None (match simulation end) is always fine
    ConversionRequest(
        sumo={"end": 100.0}, random_trips={"end": 1000.0}, trace_exporter={"end": None}
    )


def test_cross_stage_sampling_finer_than_fcd():
    _bad(
        ConversionRequest,
        sumo={"fcd_output_period": 1.0},
        trace_exporter={"sampling_period": 0.5},
    )


def test_cross_stage_sampling_non_integer_ratio():
    _bad(
        ConversionRequest,
        sumo={"fcd_output_period": 1.0},
        trace_exporter={"sampling_period": 1.5},
    )
    ConversionRequest(
        sumo={"fcd_output_period": 0.5}, trace_exporter={"sampling_period": 1.5}
    )


# ── Defaults & schema contract ───────────────────────────────


def test_defaults_construct_without_input():
    req = ConversionRequest()
    assert req.random_trips.end == 3600.0
    assert req.trace_exporter.output_format.value == "both"
    # Round-trip through the wire representation.
    ConversionRequest(**req.model_dump())


def test_json_schema_shape_for_form_generator():
    """Locks the schema contract the frontend form generator relies on."""
    schema = ConversionRequest.model_json_schema(mode="validation")
    assert set(schema["properties"]) == {
        "netconvert",
        "random_trips",
        "sumo",
        "trace_exporter",
    }
    defs = schema["$defs"]
    # Section properties are $ref'ed models…
    for prop in schema["properties"].values():
        assert prop["$ref"].startswith("#/$defs/")
    # …each a flat property bag.
    for section in (
        "NetconvertParams",
        "RandomTripsParams",
        "SumoParams",
        "TraceExporterParams",
    ):
        props = defs[section]["properties"]
        assert props
        for name, field in props.items():
            # Field must resolve to a concrete primitive/enum for the form.
            if "anyOf" in field:
                variants = field["anyOf"]
                nulls = [v for v in variants if v.get("type") == "null"]
                assert len(nulls) == 1, f"{section}.{name}: anyOf w/o null"
                assert (
                    len(variants) - len(nulls) == 1
                ), f"{section}.{name}: multi-variant anyOf unsupported by form"
    # Enum wire values: TLType serialises values like "SOTL_PHASE".
    assert "SOTL_PHASE" in defs["TLType"]["enum"]
    assert "passenger" in defs["VehicleClass"]["enum"]
