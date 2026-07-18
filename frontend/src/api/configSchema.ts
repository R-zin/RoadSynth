export type FieldType =
  | 'number'
  | 'text'
  | 'boolean'
  | 'select'
  | 'multiselect';

export interface FieldDef {
  key: string;
  label: string;
  type: FieldType;
  options?: string[];
  min?: number;
  max?: number;
  step?: number;
  /** When true, an empty "(none)" option is allowed (server default null). */
  nullable?: boolean;
  group: 'key' | 'advanced';
  placeholder?: string;
}

export interface SectionDef {
  key: string;
  title: string;
  fields: FieldDef[];
}

const HIGHWAY = [
  'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link',
  'secondary', 'secondary_link', 'tertiary', 'tertiary_link', 'residential',
  'living_street', 'unclassified', 'service', 'road', 'track', 'footway',
  'cycleway', 'path', 'steps', 'pedestrian', 'bus_guideway', 'raceway',
  'construction',
];
const VCLASS = [
  'passenger', 'bus', 'truck', 'motorcycle', 'bicycle', 'pedestrian',
  'emergency', 'authority', 'army', 'vip', 'hov', 'custom1', 'custom2',
];
const JTYPE = [
  'priority', 'traffic_light', 'right_before_left', 'unregulated',
  'allway_stop', 'zipper',
];
const TLTYPE = ['static', 'actuated', 'delay_based', 'sotl_phase', 'sotl_platoon'];
const EREM = ['all', 'noFringe'];
const OFMT = ['ns_movements', 'tcl', 'both'];
const SMODE = ['right_of_way', 'no_checks', 'all_checks'];
const LCMODE = ['default', 'no_lc', 'strategic'];
const COLL = ['warn', 'teleport', 'remove', 'none'];

export const SECTIONS: SectionDef[] = [
  {
    key: 'netconvert',
    title: 'Netconvert',
    fields: [
      { key: 'osm_highway_types', label: 'osm_highway_types', type: 'multiselect', options: HIGHWAY, group: 'key' },
      { key: 'default_speed_limit', label: 'default_speed_limit (m/s)', type: 'number', min: 1, max: 83.3, step: 0.1, group: 'key' },
      { key: 'default_junction_type', label: 'default_junction_type', type: 'select', options: JTYPE, group: 'key' },
      { key: 'tl_type', label: 'tl_type', type: 'select', options: TLTYPE, group: 'key' },
      { key: 'proj_utm', label: 'proj_utm', type: 'boolean', group: 'key' },
      { key: 'osm_remove_isolated_edges', label: 'osm_remove_isolated_edges', type: 'boolean', group: 'advanced' },
      { key: 'osm_no_large_roundabouts', label: 'osm_no_large_roundabouts', type: 'boolean', group: 'advanced' },
      { key: 'osm_oneway_spread', label: 'osm_oneway_spread', type: 'boolean', group: 'advanced' },
      { key: 'geometry_remove_isolated_nodes', label: 'geometry_remove_isolated_nodes', type: 'boolean', group: 'advanced' },
      { key: 'geometry_no_internal_links', label: 'geometry_no_internal_links', type: 'boolean', group: 'advanced' },
      { key: 'junctions_internal_link_detail', label: 'junctions_internal_link_detail', type: 'number', min: 1, max: 20, group: 'advanced' },
      { key: 'junctions_corner_detail', label: 'junctions_corner_detail', type: 'number', min: 1, max: 20, group: 'advanced' },
      { key: 'junctions_min_size', label: 'junctions_min_size (m)', type: 'number', min: 0, max: 20, step: 0.1, group: 'advanced' },
      { key: 'junctions_limit_turn_speed', label: 'junctions_limit_turn_speed (m/s)', type: 'number', min: 0, max: 30, step: 0.1, group: 'advanced' },
      { key: 'default_lane_width', label: 'default_lane_width (m)', type: 'number', min: 1, max: 10, step: 0.1, group: 'advanced' },
      { key: 'default_num_lanes', label: 'default_num_lanes', type: 'number', min: 1, max: 8, group: 'advanced' },
      { key: 'no_turnarounds', label: 'no_turnarounds', type: 'boolean', group: 'advanced' },
      { key: 'no_left_connections', label: 'no_left_connections', type: 'boolean', group: 'advanced' },
      { key: 'tl_guess', label: 'tl_guess', type: 'boolean', group: 'advanced' },
      { key: 'tl_join', label: 'tl_join', type: 'boolean', group: 'advanced' },
      { key: 'tl_min_dur', label: 'tl_min_dur (s)', type: 'number', min: 1, max: 120, group: 'advanced' },
      { key: 'tl_max_dur', label: 'tl_max_dur (s)', type: 'number', min: 5, max: 300, group: 'advanced' },
      { key: 'keep_edges_by_vclass', label: 'keep_edges_by_vclass', type: 'select', options: VCLASS, nullable: true, group: 'advanced' },
      { key: 'remove_edges_by_type', label: 'remove_edges_by_type', type: 'text', placeholder: 'footway,cycleway,path', group: 'advanced' },
      { key: 'keep_fringe', label: 'keep_fringe', type: 'select', options: EREM, group: 'advanced' },
      { key: 'proj_plain_geo', label: 'proj_plain_geo', type: 'boolean', group: 'advanced' },
    ],
  },
  {
    key: 'random_trips',
    title: 'Random Trips',
    fields: [
      { key: 'end', label: 'end (s)', type: 'number', min: 1, group: 'key' },
      { key: 'period', label: 'period (s)', type: 'number', min: 0.1, max: 3600, step: 0.1, group: 'key' },
      { key: 'vehicle_class', label: 'vehicle_class', type: 'select', options: VCLASS, group: 'key' },
      { key: 'seed', label: 'seed', type: 'number', min: 0, group: 'key' },
      { key: 'begin', label: 'begin (s)', type: 'number', min: 0, group: 'advanced' },
      { key: 'insertion_density', label: 'insertion_density (/h/km)', type: 'number', min: 0, group: 'advanced' },
      { key: 'min_distance', label: 'min_distance (m)', type: 'number', min: 0, group: 'advanced' },
      { key: 'max_distance', label: 'max_distance (m)', type: 'number', min: 0, group: 'advanced' },
      { key: 'fringe_factor', label: 'fringe_factor', type: 'number', min: 0, max: 100, step: 0.1, group: 'advanced' },
      { key: 'fringe_threshold', label: 'fringe_threshold', type: 'number', min: 0, max: 1, step: 0.01, group: 'advanced' },
      { key: 'validate_routes', label: 'validate_routes', type: 'boolean', group: 'advanced' },
      { key: 'allow_loops', label: 'allow_loops', type: 'boolean', group: 'advanced' },
      { key: 'random_depart_pos', label: 'random_depart_pos', type: 'boolean', group: 'advanced' },
      { key: 'random_arrival_pos', label: 'random_arrival_pos', type: 'boolean', group: 'advanced' },
    ],
  },
  {
    key: 'sumo',
    title: 'SUMO Simulation',
    fields: [
      { key: 'end', label: 'end (s)', type: 'number', min: 1, group: 'key' },
      { key: 'step_length', label: 'step_length (s)', type: 'number', min: 0.01, max: 10, step: 0.01, group: 'key' },
      { key: 'fcd_output_period', label: 'fcd_output_period (s)', type: 'number', min: 0.01, max: 60, step: 0.01, group: 'key' },
      { key: 'default_max_speed', label: 'default_max_speed (m/s)', type: 'number', min: 1, max: 200, step: 0.1, group: 'key' },
      { key: 'begin', label: 'begin (s)', type: 'number', min: 0, group: 'advanced' },
      { key: 'default_accel', label: 'default_accel (m/s²)', type: 'number', min: 0.1, max: 20, step: 0.1, group: 'advanced' },
      { key: 'default_decel', label: 'default_decel (m/s²)', type: 'number', min: 0.1, max: 20, step: 0.1, group: 'advanced' },
      { key: 'default_emergency_decel', label: 'default_emergency_decel (m/s²)', type: 'number', min: 0.1, max: 30, step: 0.1, group: 'advanced' },
      { key: 'default_sigma', label: 'default_sigma', type: 'number', min: 0, max: 1, step: 0.01, group: 'advanced' },
      { key: 'default_tau', label: 'default_tau (s)', type: 'number', min: 0.1, max: 10, step: 0.1, group: 'advanced' },
      { key: 'default_vehicle_length', label: 'default_vehicle_length (m)', type: 'number', min: 1, max: 30, step: 0.1, group: 'advanced' },
      { key: 'default_min_gap', label: 'default_min_gap (m)', type: 'number', min: 0, max: 20, step: 0.1, group: 'advanced' },
      { key: 'speed_mode', label: 'speed_mode', type: 'select', options: SMODE, group: 'advanced' },
      { key: 'lanechange_mode', label: 'lanechange_mode', type: 'select', options: LCMODE, group: 'advanced' },
      { key: 'no_internal_links', label: 'no_internal_links', type: 'boolean', group: 'advanced' },
      { key: 'ignore_route_errors', label: 'ignore_route_errors', type: 'boolean', group: 'advanced' },
      { key: 'collision_action', label: 'collision_action', type: 'select', options: COLL, group: 'advanced' },
      { key: 'lateral_resolution', label: 'lateral_resolution (m)', type: 'number', min: 0, max: 5, step: 0.1, group: 'advanced' },
      { key: 'fcd_output_geo', label: 'fcd_output_geo', type: 'boolean', group: 'advanced' },
      { key: 'fcd_filter_shapes', label: 'fcd_filter_shapes', type: 'boolean', group: 'advanced' },
      { key: 'tripinfo_output', label: 'tripinfo_output', type: 'boolean', group: 'advanced' },
      { key: 'summary_output', label: 'summary_output', type: 'boolean', group: 'advanced' },
      { key: 'seed', label: 'seed', type: 'number', min: 0, group: 'advanced' },
    ],
  },
  {
    key: 'trace_exporter',
    title: 'Trace Exporter',
    fields: [
      { key: 'output_format', label: 'output_format', type: 'select', options: OFMT, group: 'key' },
      { key: 'sampling_period', label: 'sampling_period (s)', type: 'number', min: 0.1, max: 60, step: 0.1, group: 'key' },
      { key: 'penetration_rate', label: 'penetration_rate', type: 'number', min: 0.01, max: 1, step: 0.01, group: 'key' },
      { key: 'begin', label: 'begin (s)', type: 'number', min: 0, group: 'advanced' },
      { key: 'end', label: 'end (s)', type: 'number', min: 0, group: 'advanced' },
      { key: 'x_offset', label: 'x_offset (m)', type: 'number', group: 'advanced' },
      { key: 'y_offset', label: 'y_offset (m)', type: 'number', group: 'advanced' },
      { key: 'boundary', label: 'boundary (xMin,yMin,xMax,yMax)', type: 'text', placeholder: '0,0,5000,5000', group: 'advanced' },
      { key: 'ns2_include_speed', label: 'ns2_include_speed', type: 'boolean', group: 'advanced' },
      { key: 'write_fcd_filtered', label: 'write_fcd_filtered', type: 'boolean', group: 'advanced' },
      { key: 'seed', label: 'seed', type: 'number', min: 0, group: 'advanced' },
    ],
  },
];
