from __future__ import annotations

from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

CoordinatePair = Annotated[list[float], Field(min_length=2, max_length=2)]
LINE_WIDTH = Field(default=1.5, gt=0, le=100)


class LegacyModel(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)


class LegacyLineRequest(LegacyModel):
    start: CoordinatePair
    end: CoordinatePair
    color: str = "#111827"
    linewidth: float = LINE_WIDTH
    layer: str = "default"


class LegacyCircleRequest(LegacyModel):
    center: CoordinatePair
    radius: float = Field(gt=0)
    color: str = "#111827"
    linewidth: float = LINE_WIDTH
    layer: str = "default"


class LegacyRectangleRequest(LegacyModel):
    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "#111827"
    linewidth: float = LINE_WIDTH
    layer: str = "default"

    @model_validator(mode="after")
    def validate_dimensions(self) -> LegacyRectangleRequest:
        if self.x1 == self.x2 or self.y1 == self.y2:
            raise ValueError("rectangle must have non-zero width and height")
        return self


class LegacyPolylineRequest(LegacyModel):
    points: list[CoordinatePair] = Field(min_length=2, max_length=500)
    color: str = "#111827"
    linewidth: float = LINE_WIDTH
    layer: str = "default"


class LegacyTextRequest(LegacyModel):
    content: str
    x: float
    y: float
    font_size: float = 14
    color: str = "#111827"
    layer: str = "default"


class LegacySymbolRequest(LegacyModel):
    symbol_type: str
    x: float = 0
    y: float = 0
    width: float | None = None
    height: float | None = None
    rotation: float = 0
    label: str = ""
    color: str = "#111827"
    linewidth: float = LINE_WIDTH
    layer: str = "default"


class LegacyBatchRequest(LegacyModel):
    operations: list[dict[str, Any]] = Field(default_factory=list, max_length=500)


class LegacyCreateLayerRequest(LegacyModel):
    name: str
    visible: bool = True
