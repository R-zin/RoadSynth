from typing import Optional, List, Any
from typing_extensions import Self

from pydantic import BaseModel, Field, field_validator
from enum import Enum
import re

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
class OutputFormat(str, Enum):
    ns_movements = "ns_movements"
    tcl = "tcl"

class VehicleClass(str, Enum):
    motorcycle = "motorcycle"
    bicycle = "bicycle"
    passenger = "passenger"
    bus = "bus"
    truck = "truck"
    pedestrian = "pedestrian"
    emergency = "emergency"

class TLType(str, Enum):
    static = "static"
    actuated = "actuated"
    delayed_based = "delay_based"

class EdgeRemoval(str, Enum):
    all = "all"
    noFringe = "noFringe"

class JunctionType(str, Enum):
    priority = "priority"
    traffic_light = "traffic_light"
    right_before_left = "right_before_left"
    unregulated = "unregulated"
    allway_stop = "allway_stop"
    zipper = "zipper"

class SpeedMode(str, Enum):
    right_of_way = "right_of_way"
    no_checks = "no_checks"
    all_checks = "all_checks"

class LaneChangeMode(str, Enum):
    default = "default"
    no_lc = "no_lc"
    strategic_only = "strategic_only"

class NetconvertParams(BaseModel):
    osm_highway_types:List[str] = Field(default=["motorway", "trunk", "primary", "secondary",
                 "tertiary", "residential", "living_street",
                 "unclassified"])
    osm_remove_isolated_edges:bool = Field(default=True)
    osm_no_large_roundabouts:bool = Field(default=False)
    osm_oneway_spread:bool = Field(default=False)

    geometry_remove_isolated_nodes:bool = Field(default=True)
    geometry_no_internal_links:bool = Field(default=False)
    junctions_internal_link_detail:int = Field(5,ge=1,le=20)
    junctions_corner_detail:int = Field(5,ge=1,le=20)
    default_junction_type: JunctionType = Field(JunctionType.priority)
    junctions_min_size:float = Field(1.5,ge=0.0,le=20)
    junctions_limit_turn_speed:float = Field(5.5,ge=0.0,le=30)

    default_lane_width:float = Field(3.2,ge=1.0,le=10)
    default_speed_limit:float = Field(13.9,ge=1.0,le=80)
    default_num_lanes:int = Field(1,ge=1,le=8)
    no_turnarounds:bool = Field(default=False)
    no_left_connections:bool = Field(default=False) #Disallow left turn connections

    tl_guess:bool = Field(default=True)
    tl_type:TLType = Field(TLType.static)
    tl_join:bool = Field(default=False)
    tl_min_duration:int = Field(5,ge=1,le=120)
    tl_max_duration:int = Field(50,ge=5,le=300)

    keep_edges_by_vclass:Optional[VehicleClass] = Field(default=None)
    remove_edges_by_type:Optional[str] = Field(default=None)
    keep_fringes:EdgeRemoval= Field(default=EdgeRemoval.all)

    proj_utm:bool = Field(default=True)
    proj_plain_geo:bool = Field(default=False)

    @field_validator("osm_highway_types")
    @classmethod
    def validate_highway_types(cls,v: List[str]):
        if not v:
            raise ValueError("highway types cannot be empty")
        invalid = [t for t in v if t not in _VALID_HIGHWAY_TYPES]
        if invalid:
            raise ValueError(f"Unknow highway types {invalid}")
        return v

    @field_validator("remove_edges_by_type")
    @classmethod
    def validate_remove_types(cls, value: Optional[str])->Optional[str] :
        if value is None:
            raise ValueError("remove_edges_by_type cannot be None")
        tokens = [t.strip() for t in value.split(",") if t.strip()]
        if not tokens:
            raise ValueError("remove_edges_by_type cannot be empty")
        return ",".join(tokens)
    








