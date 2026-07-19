import type { AgentTransaction } from "./types";

export type AutoLayoutOptions = {
  expected_revision?: number | null;
  element_ids: string[];
  direction: "horizontal" | "vertical";
  rank_gap: number;
  node_gap: number;
  component_gap: number;
  obstacle_margin: number;
  lane_gap: number;
  reroute_connectors: boolean;
  include_hidden: boolean;
};

export type LayoutBounds = {
  min_x: number;
  min_y: number;
  max_x: number;
  max_y: number;
  width: number;
  height: number;
};

export type AutoLayoutMetrics = {
  node_count: number;
  connector_count: number;
  overlaps_before: number;
  overlaps_after: number;
  pipe_obstacle_intersections_before: number;
  pipe_obstacle_intersections_after: number;
  shared_lane_segments_before: number;
  shared_lane_segments_after: number;
  total_route_length_before: number;
  total_route_length_after: number;
  bounds_before: LayoutBounds;
  bounds_after: LayoutBounds;
};

export type AutoLayoutPreview = {
  valid: boolean;
  document_id: string;
  current_revision: number;
  transaction?: AgentTransaction | null;
  moved_element_ids: string[];
  rerouted_connector_ids: string[];
  moved_annotation_ids: string[];
  skipped_locked_element_ids: string[];
  warnings: string[];
  metrics: AutoLayoutMetrics;
};
