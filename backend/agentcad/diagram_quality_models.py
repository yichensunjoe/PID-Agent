from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from .models import StrictModel


class DiagramQualityIssue(StrictModel):
    severity: Literal["warning", "error"]
    code: str
    message: str
    element_ids: list[str] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class DiagramQualityMetrics(StrictModel):
    symbol_count: int = Field(default=0, ge=0)
    connector_count: int = Field(default=0, ge=0)
    total_bends: int = Field(default=0, ge=0)
    non_orthogonal_segments: int = Field(default=0, ge=0)
    micro_segments: int = Field(default=0, ge=0)
    unnecessary_bends: int = Field(default=0, ge=0)
    excessive_bend_connectors: int = Field(default=0, ge=0)
    node_overlaps: int = Field(default=0, ge=0)
    crowded_node_pairs: int = Field(default=0, ge=0)
    pipe_obstacle_intersections: int = Field(default=0, ge=0)
    geometric_crossings: int = Field(default=0, ge=0)
    unbridged_crossings: int = Field(default=0, ge=0)
    port_direction_mismatches: int = Field(default=0, ge=0)
    port_exit_mismatches: int = Field(default=0, ge=0)
    port_facing_mismatches: int = Field(default=0, ge=0)
    backward_flow_connectors: int = Field(default=0, ge=0)
    out_of_bounds_symbols: int = Field(default=0, ge=0)
    out_of_bounds_connector_points: int = Field(default=0, ge=0)
    duplicate_label_count: int = Field(default=0, ge=0)
    text_text_overlaps: int = Field(default=0, ge=0)
    text_symbol_overlaps: int = Field(default=0, ge=0)
    text_connector_intersections: int = Field(default=0, ge=0)


class DiagramQualityReport(StrictModel):
    schema_name: Literal["pid-agent.diagram-quality"] = Field(
        default="pid-agent.diagram-quality",
        alias="schema",
    )
    version: Literal[2] = 2
    passed: bool
    score: float = Field(ge=0, le=100)
    metrics: DiagramQualityMetrics
    issues: list[DiagramQualityIssue] = Field(default_factory=list)
