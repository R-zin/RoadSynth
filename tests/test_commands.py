"""Tests for the pure command builders and XML writers in app/worker.py.
SUMO lookup is mocked by the autouse no_sumo fixture in conftest."""

from pathlib import Path

from app.models import (
    LaneChangeMode,
    NetconvertParams,
    RandomTripsParams,
    SpeedMode,
    SumoParams,
    TraceExporterParams,
    VehicleClass,
)
from app.worker import (
    _duarouter_cmd,
    _lc_mode_int,
    _netconvert_cmd,
    _random_trips_cmd,
    _speed_mode_int,
    _sumo_cmd,
    _trace_export_cmds,
    _write_sumo_cfg,
    _write_vtype_xml,
    check_tools,
)

OSM = Path("/in/map.osm")
NET = Path("/w/network.net.xml")


def pairs(cmd):
    """Dict view of a [--flag, value, ...] argv (flags starting with '--')."""
    out = {}
    i = 0
    while i < len(cmd):
        if cmd[i].startswith("--"):
            out[cmd[i]] = (
                cmd[i + 1]
                if i + 1 < len(cmd) and not cmd[i + 1].startswith("--")
                else None
            )
            i += 2 if out[cmd[i]] is not None else 1
        else:
            i += 1
    return out


# ── netconvert ────────────────────────────────────────────────


def test_netconvert_basics():
    cmd = _netconvert_cmd(OSM, NET, NetconvertParams())
    p = pairs(cmd)
    assert cmd[0] == "/mock/bin/netconvert"
    assert p["--osm-files"] == str(OSM)
    assert p["--output-file"] == str(NET)
    assert p["--proj.utm"] == "true"
    assert p["--osm.highway.type-tag"] == ",".join(NetconvertParams().osm_highway_types)
    # Highway types are joined into ONE argv item (comma-separated).
    tag_idx = cmd.index("--osm.highway.type-tag")
    assert "," in cmd[tag_idx + 1]
    # (type-tag may be the final flag when no conditionals are enabled)


def test_netconvert_optional_flags():
    default_cmd = _netconvert_cmd(OSM, NET, NetconvertParams())
    for flag in (
        "--no-turnarounds",
        "--no-left-connections",
        "--remove-edges.by-type",
        "--proj.plain-geo",
        "--roundabouts.guess",
        "--osm.oneway-spread-right",
        "--keep-edges.fringe-edges",
    ):
        assert flag not in default_cmd

    p = NetconvertParams(
        no_turnarounds=True,
        no_left_connections=True,
        remove_edges_by_type="footway,path",
        proj_utm=False,
        proj_plain_geo=True,
        osm_no_large_roundabouts=True,
        osm_oneway_spread=True,
        keep_fringe="noFringe",
    )
    cmd = _netconvert_cmd(OSM, NET, p)
    assert pairs(cmd)["--no-turnarounds"] == "true"
    assert pairs(cmd)["--remove-edges.by-type"] == "footway,path"
    assert pairs(cmd)["--proj.plain-geo"] == "true"
    assert pairs(cmd)["--roundabouts.guess"] == "false"
    assert pairs(cmd)["--keep-edges.fringe-edges"] == "false"


def test_netconvert_plain_geo_requires_no_utm():
    # proj_utm=True + proj_plain_geo=True is rejected by the model validator
    # (mutual exclusion). Only plain_geo alone emits the flag.
    plain_only = _netconvert_cmd(
        OSM, NET, NetconvertParams(proj_utm=False, proj_plain_geo=True)
    )
    assert "--proj.plain-geo" in plain_only
    assert pairs(plain_only)["--proj.utm"] == "false"


# ── randomTrips ───────────────────────────────────────────────


def test_random_trips_basics():
    cmd = _random_trips_cmd(NET, Path("/w/trips.xml"), RandomTripsParams())
    p = pairs(cmd)
    assert cmd[0] == "python3"
    assert cmd[1] == "/mock/tools/randomTrips.py"
    assert p["--seed"] == "42"
    assert "--max-distance" not in p
    assert "--insertion-density" not in p
    # validate_routes defaults to True → --validate IS present by default
    assert "--validate" in cmd


def test_random_trips_optional_args():
    params = RandomTripsParams(
        max_distance=5000.0,
        insertion_density=12.0,
        validate_routes=True,
        random_depart_pos=True,
        random_arrival_pos=True,
        allow_loops=True,
    )
    cmd = _random_trips_cmd(NET, Path("/w/trips.xml"), params)
    p = pairs(cmd)
    assert p["--max-distance"] == "5000.0"
    assert p["--insertion-density"] == "12.0"
    assert "--validate" in cmd
    assert "--random-depart-pos" in cmd
    assert "--random-arrival-pos" in cmd
    assert "--allow-fringe.min-length" in cmd


# ── duarouter / sumo ──────────────────────────────────────────


def test_duarouter_cmd():
    cmd = _duarouter_cmd(
        NET, Path("/w/trips.xml"), Path("/w/routes.rou.xml"), RandomTripsParams()
    )
    p = pairs(cmd)
    assert cmd[0] == "/mock/bin/duarouter"
    assert p["--ignore-errors"] == "true"
    assert "--no-step-log" in cmd


def test_sumo_cmd():
    cmd = _sumo_cmd(Path("/w/sim.sumocfg"), Path("/w/vtypes.add.xml"))
    assert cmd[0] == "/mock/bin/sumo"
    assert pairs(cmd)["--configuration-file"] == "/w/sim.sumocfg"
    assert pairs(cmd)["--additional-files"] == "/w/vtypes.add.xml"


# ── traceExporter ─────────────────────────────────────────────


FCD = Path("/w/fcd-output.xml")
WORK = Path("/w")


def test_trace_export_both_formats():
    specs = _trace_export_cmds(FCD, WORK, TraceExporterParams())  # both
    assert [s[0] for s in specs] == ["ns_movements", "tcl"]
    assert specs[0][2].name == "ns_movements"
    assert specs[1][2].name == "mobility.tcl"
    # ns_movements carries the speed flag by default, tcl does not
    assert "--ns2-include-speed" in specs[0][1]
    assert "--ns2-include-speed" not in specs[1][1]


def test_trace_export_single_formats():
    ns_only = _trace_export_cmds(
        FCD, WORK, TraceExporterParams(output_format="ns_movements")
    )
    assert len(ns_only) == 1 and ns_only[0][0] == "ns_movements"
    tcl_only = _trace_export_cmds(FCD, WORK, TraceExporterParams(output_format="tcl"))
    assert len(tcl_only) == 1 and tcl_only[0][0] == "tcl"


def test_trace_export_optional_args():
    params = TraceExporterParams(end=500.0, begin=10.0, boundary="0,0,100,100")
    cmd = _trace_export_cmds(FCD, WORK, params)[0][1]
    p = pairs(cmd)
    assert p["--end"] == "500.0"
    assert p["--begin"] == "10.0"
    assert p["--boundary"] == "0,0,100,100"
    base = _trace_export_cmds(FCD, WORK, TraceExporterParams())[0][1]
    assert "--end" not in pairs(base)
    assert "--boundary" not in pairs(base)


# ── Bitmask mappings ──────────────────────────────────────────


def test_mode_bitmasks():
    assert _speed_mode_int(SpeedMode.right_of_way) == 31
    assert _speed_mode_int(SpeedMode.no_checks) == 32
    assert _speed_mode_int(SpeedMode.all_checks) == 31
    assert _lc_mode_int(LaneChangeMode.default) == 1621
    assert _lc_mode_int(LaneChangeMode.no_lc) == 0
    assert _lc_mode_int(LaneChangeMode.strategic_only) == 256


# ── XML writers ───────────────────────────────────────────────


async def test_write_sumo_cfg(tmp_path):
    # fcd_output_period must be a whole multiple of step_length.
    params = SumoParams(step_length=0.5, seed=7, fcd_output_period=0.5)
    cfg = await _write_sumo_cfg(
        tmp_path,
        NET,
        Path("/w/routes.rou.xml"),
        Path("/w/fcd.xml"),
        Path("/w/trip.xml"),
        Path("/w/sum.xml"),
        params,
    )
    text = cfg.read_text()
    assert '<step-length value="0.5"/>' in text
    assert '<seed value="7"/>' in text
    assert "tripinfo-output" in text
    assert "summary-output" in text

    sparse = SumoParams(
        tripinfo_output=False, summary_output=False, fcd_output_period=0.1
    )
    cfg2 = await _write_sumo_cfg(
        tmp_path,
        NET,
        Path("/w/routes.rou.xml"),
        Path("/w/fcd.xml"),
        Path("/w/trip.xml"),
        Path("/w/sum.xml"),
        sparse,
    )
    text2 = cfg2.read_text()
    assert "tripinfo-output" not in text2
    assert "summary-output" not in text2


async def test_write_vtype_xml(tmp_path):
    params = SumoParams(default_decel=4.5, default_emergency_decel=9.0)
    path = await _write_vtype_xml(tmp_path, params, VehicleClass.bus)
    text = path.read_text()
    assert 'vClass="bus"' in text
    assert 'speedMode="31"' in text
    assert 'lcMode="1621"' in text
    assert 'emergencyDecel="9.0"' in text


# ── Tool checking ─────────────────────────────────────────────


def test_check_tools_all_found(no_sumo):
    tools = check_tools("")
    assert all(tools.values())
    assert set(tools) == {
        "netconvert",
        "duarouter",
        "sumo",
        "traceExporter.py",
        "randomTrips.py",
    }


def test_check_tools_missing(monkeypatch):
    import app.worker as worker_mod

    monkeypatch.setattr(worker_mod, "_find_binary", lambda names: None)
    monkeypatch.setattr(worker_mod, "_find_sumo_script", lambda f, h="": None)
    tools = check_tools("")
    assert not any(tools.values())
