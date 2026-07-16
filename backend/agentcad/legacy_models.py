from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class LegacyLineRequest(BaseModel):
    start: list[float]
    end: list[float]
    color: str = "#111827"
    linewidth: float = 1.5
    layer: str = "default"


class LegacyCircleRequest(BaseModel):
    center: list[float]
    radius: float = Field(gt=0)
    color: str = "#111827"
    linewidth: float = 1.5
    layer: str = "default"


class LegacyRectangleRequest(BaseModel):
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "#111827"
    linewidth: float = 1.5
    layer: str = "default"


class LegacyPolylineRequest(BaseModel):
    points: list[list[float]]
    color: str = "#111827"
    linewidth: float = 1.5
    layer: str = "default"


class LegacyTextRequest(BaseModel):
    content: str
    x: float
    y: float
    font_size: float = 14
    color: str = "#111827"
    layer: str = "default"


class LegacySymbolRequest(BaseModel):
    symbol_type: str
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    rotation: float = 0
    label: str = ""
    color: str = "#111827"
    linewidth: float = 1.5
    layer: str = "default"


class LegacyBatchRequest(BaseModel):
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class LegacyCreateLayerRequest(BaseModel):
    name: str
    visible: bool = True
