from __future__ import annotations

from typing import Literal

from pydantic import Field

from .models import StrictModel, TransactionRequest


class AutoLayoutRequest(StrictModel):
    expected_revision: int | None = Field(default=None, ge=0)
    element_ids: list[str] = Field(default_factory=list, max_length=5000)
    direction: Literal["horizontal", "vertical"] = "horizontal"
    rank_gap: float = Field(default=180, ge=60, le=1000)
    node_gap: float = Field(default=90, ge=20, le=500)
    component_gap: float = Field(default=180, ge=40, le=1000)
    obstacle_margin: float = Field(default=24, ge=4, le=200)
    lane_gap: float = Field(default=24, ge=4, le=120)
    reroute_connectors: bool = True
    include_hidden: bool = False


class LayoutBounds(StrictModel):
    min_x: float = 0
    min_y: float = 0
    max_x: float = 0
    max_y: float = 0
    width: float = 0
    height: float = 0


class AutoLayoutMetrics(StrictModel):
    node_count: int = Field(default=0, ge=0)
    connector_count: int = Field(default=0, ge=0)
    overlaps_before: int = Field(default=0, ge=0)
    overlaps_after: int = Field(default=0, ge=0)
    pipe_obstacle_intersections_before: int = Field(default=0, ge=0)
    pipe_obstacle_intersections_after: int = Field(default=0, ge=0)
    shared_lane_segments_before: int = Field(default=0, ge=0)
    shared_lane_segments_after: int = Field(default=0, ge=0)
    total_route_length_before: float = Field(default=0, ge=0)
    total_route_length_after: float = Field(default=0, ge=0)
    bounds_before: LayoutBounds = Field(default_factory=LayoutBounds)
    bounds_after: LayoutBounds = Field(default_factory=LayoutBounds)


class AutoLayoutPreview(StrictModel):
    valid: bool = True
    document_id: str
    current_revision: int = Field(ge=0)
    transaction: TransactionRequest | None = None
    moved_element_ids: list[str] = Field(default_factory=list)
    rerouted_connector_ids: list[str] = Field(default_factory=list)
    moved_annotation_ids: list[str] = Field(default_factory=list)
    skipped_locked_element_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    metrics: AutoLayoutMetrics = Field(default_factory=AutoLayoutMetrics)
