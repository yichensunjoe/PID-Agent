from __future__ import annotations

from dataclasses import dataclass
from math import cos, isfinite, radians, sin
from typing import Literal

from .models import Document, Element
from .symbols import SymbolRegistry

ExportRange = Literal["canvas", "content", "viewport"]


@dataclass(frozen=True)
class ExportBounds:
    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    def expanded(self, padding: float) -> ExportBounds:
        return ExportBounds(
            x=self.x - padding,
            y=self.y - padding,
            width=self.width + padding * 2,
            height=self.height + padding * 2,
        )

    def as_dict(self) -> dict[str, float]:
        return {
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
        }


def visible_elements(document: Document) -> list[Element]:
    visible_layers = {layer.id for layer in document.layers if layer.visible}
    visible_systems = {system.id for system in document.systems if system.visible}
    return [
        element
        for element in document.elements
        if element.layer_id in visible_layers and element.system_id in visible_systems
    ]


def _bounds_from_points(points: list[tuple[float, float]]) -> ExportBounds:
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return ExportBounds(
        x=min(xs),
        y=min(ys),
        width=max(max(xs) - min(xs), 0.001),
        height=max(max(ys) - min(ys), 0.001),
    )


def element_bounds(element: Element, registry: SymbolRegistry) -> ExportBounds:
    if element.type == "line":
        return _bounds_from_points(
            [(element.start.x, element.start.y), (element.end.x, element.end.y)]
        )
    if element.type in {"polyline", "connector"}:
        return _bounds_from_points([(point.x, point.y) for point in element.points])
    if element.type == "rectangle":
        return ExportBounds(element.x, element.y, element.width, element.height)
    if element.type == "circle":
        return ExportBounds(
            element.center.x - element.radius,
            element.center.y - element.radius,
            element.radius * 2,
            element.radius * 2,
        )
    if element.type == "text":
        width = max(element.font_size, len(element.text) * element.font_size * 0.6)
        offset = width / 2 if element.anchor == "middle" else width if element.anchor == "end" else 0
        return ExportBounds(
            element.position.x - offset,
            element.position.y - element.font_size,
            width,
            element.font_size * 1.35,
        )
    if element.type == "junction":
        label_width = len(element.label) * 7 if element.label else 0
        return ExportBounds(
            element.position.x - element.radius,
            element.position.y - max(element.radius, 20 if element.label else element.radius),
            element.radius * 2 + label_width + (8 if element.label else 0),
            element.radius * 2 + (20 if element.label else 0),
        )
    if element.type == "symbol":
        center_x = element.position.x + element.width / 2
        center_y = element.position.y + element.height / 2
        angle = radians(element.rotation)
        corners: list[tuple[float, float]] = []
        for local_x, local_y in (
            (-element.width / 2, -element.height / 2),
            (element.width / 2, -element.height / 2),
            (element.width / 2, element.height / 2),
            (-element.width / 2, element.height / 2),
        ):
            corners.append(
                (
                    center_x + local_x * cos(angle) - local_y * sin(angle),
                    center_y + local_x * sin(angle) + local_y * cos(angle),
                )
            )
        result = _bounds_from_points(corners)
        if element.label:
            definition = registry.get(element.symbol_key)
            label_width = max(12.0, len(element.label) * 7.2)
            label_center_x = element.position.x + element.width / 2
            label_y = element.position.y + element.height + 16 * (element.height / definition.height)
            label_bounds = ExportBounds(label_center_x - label_width / 2, label_y - 12, label_width, 16)
            result = union_bounds([result, label_bounds])
        return result
    raise ValueError(f"unsupported element type: {element.type}")


def union_bounds(bounds: list[ExportBounds]) -> ExportBounds:
    if not bounds:
        raise ValueError("at least one bounds value is required")
    x1 = min(item.x for item in bounds)
    y1 = min(item.y for item in bounds)
    x2 = max(item.x2 for item in bounds)
    y2 = max(item.y2 for item in bounds)
    return ExportBounds(x=x1, y=y1, width=max(x2 - x1, 0.001), height=max(y2 - y1, 0.001))


def content_bounds(
    document: Document,
    registry: SymbolRegistry,
    *,
    padding: float = 24,
) -> ExportBounds:
    elements = visible_elements(document)
    if not elements:
        return ExportBounds(0, 0, document.canvas.width, document.canvas.height)
    result = union_bounds([element_bounds(element, registry) for element in elements])
    return result.expanded(max(0, padding))


def resolve_export_bounds(
    document: Document,
    registry: SymbolRegistry,
    *,
    export_range: ExportRange,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    padding: float = 24,
) -> ExportBounds:
    if export_range == "canvas":
        return ExportBounds(0, 0, document.canvas.width, document.canvas.height)
    if export_range == "content":
        return content_bounds(document, registry, padding=padding)
    if export_range != "viewport":
        raise ValueError(f"unsupported export range: {export_range}")
    if x is None or y is None or width is None or height is None:
        raise ValueError("viewport export requires x, y, width and height")
    if not all(isfinite(value) for value in (x, y, width, height)):
        raise ValueError("viewport x, y, width and height must be finite numbers")
    if width <= 0 or height <= 0:
        raise ValueError("viewport width and height must be greater than zero")
    return ExportBounds(x=x, y=y, width=width, height=height)


def intersects(left: ExportBounds, right: ExportBounds, *, margin: float = 0) -> bool:
    return not (
        left.x2 < right.x - margin
        or right.x2 < left.x - margin
        or left.y2 < right.y - margin
        or right.y2 < left.y - margin
    )


def elements_in_bounds(
    elements: list[Element],
    registry: SymbolRegistry,
    bounds: ExportBounds,
    *,
    margin: float = 12,
) -> list[Element]:
    return [
        element
        for element in elements
        if intersects(element_bounds(element, registry), bounds, margin=margin)
    ]
