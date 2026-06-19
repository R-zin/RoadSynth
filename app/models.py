from typing import Optional,List
from pydantic import BaseModel,Field
from enum import Enum

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
    



