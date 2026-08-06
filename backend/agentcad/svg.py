from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from html import escape
from math import atan2, cos, floor, sin
from typing import Any

from .exporting import ExportBounds, elements_in_bounds, visible_elements
from .models import ConnectorElement, Document, Element, Point, Style
from .symbols import SymbolRegistry

SVG_FONT_FAMILY = "Noto Sans CJK SC, Noto Sans CJK, DejaVu Sans, sans-serif"


@dataclass(frozen=True)
class _SegmentRecord:
    connector: ConnectorElement
    index: int
    first: Point
    second: Point


def _attrs(style: Style) -> str:
    dash = ""
    if style.dash:
        dash = f' stroke-dasharray="{",".join(str(value) for value in style.dash)}"'
    return (
        f' stroke="{escape(style.stroke, quote=True)}"'
        f' fill="{escape(style.fill, quote=True)}"'
        f' stroke-width="{style.stroke_width}"'
        f' opacity="{style.opacity}"{dash}'
        ' vector-effect="non-scaling-stroke"'
    )


def _points(points: list[Any]) -> str:
    return " ".join(f"{point.x},{point.y}" for point in points)


def _render_symbol_shape(shape: dict[str, Any], *, counter_rotation: float = 0) -> str:
    kind = shape.get("type")
    dash = ""
    raw_dash = shape.get("dash")
    if isinstance(raw_dash, list) and raw_dash and all(
        isinstance(value, (int, float)) and value > 0 for value in raw_dash
    ):
        dash = f' stroke-dasharray="{",".join(str(value) for value in raw_dash)}"'
    if kind == "line":
        return (
            f'<line x1="{shape["x1"]}" y1="{shape["y1"]}" '
            f'x2="{shape["x2"]}" y2="{shape["y2"]}"{dash} />'
        )
    if kind == "polyline":
        points = " ".join(f"{x},{y}" for x, y in shape["points"])
        tag = "polygon" if shape.get("closed") else "polyline"
        fill = shape.get("fill", "none")
        return f'<{tag} points="{points}" fill="{escape(str(fill), quote=True)}"{dash} />'
    if kind == "rect":
        return (
            f'<rect x="{shape["x"]}" y="{shape["y"]}" '
            f'width="{shape["width"]}" height="{shape["height"]}" '
            f'rx="{shape.get("rx", 0)}"{dash} />'
        )
    if kind == "circle":
        return f'<circle cx="{shape["cx"]}" cy="{shape["cy"]}" r="{shape["r"]}"{dash} />'
    if kind == "path":
        return f'<path d="{escape(str(shape["d"]), quote=True)}"{dash} />'
    if kind == "text":
        transform = (
            f' transform="rotate({-counter_rotation} {shape["x"]} {shape["y"]})"'
            if counter_rotation
            else ""
        )
        return (
            f'<text x="{shape["x"]}" y="{shape["y"]}" '
            f'font-size="{shape.get("font_size", 12)}" '
            f'text-anchor="{shape.get("anchor", "middle")}"{transform}>'
            f"{escape(str(shape.get('text', '')))}</text>"
        )
    return ""


def _render_element(element: Element, registry: SymbolRegistry) -> str:
    attrs = _attrs(element.style)
    common = (
        f' data-layer-id="{escape(element.layer_id, quote=True)}"'
        f' data-system-id="{escape(element.system_id, quote=True)}"'
    )
    if element.type == "line":
        return (
            f'<line id="{escape(element.id, quote=True)}" x1="{element.start.x}" '
            f'y1="{element.start.y}" x2="{element.end.x}" y2="{element.end.y}"{attrs}{common} />'
        )
    if element.type == "polyline":
        tag = "polygon" if element.closed else "polyline"
        return f'<{tag} id="{escape(element.id, quote=True)}" points="{_points(element.points)}"{attrs}{common} />'
    if element.type == "rectangle":
        return (
            f'<rect id="{escape(element.id, quote=True)}" x="{element.x}" y="{element.y}" '
            f'width="{element.width}" height="{element.height}" rx="{element.corner_radius}"{attrs}{common} />'
        )
    if element.type == "circle":
        return (
            f'<circle id="{escape(element.id, quote=True)}" cx="{element.center.x}" '
            f'cy="{element.center.y}" r="{element.radius}"{attrs}{common} />'
        )
    if element.type == "text":
        return (
            f'<text id="{escape(element.id, quote=True)}" x="{element.position.x}" '
            f'y="{element.position.y}" font-size="{element.font_size}" '
            f'text-anchor="{element.anchor}" fill="{escape(element.style.stroke, quote=True)}" '
            f'opacity="{element.style.opacity}"{common}>{escape(element.text)}</text>'
        )
    if element.type == "junction":
        label = ""
        if element.label:
            label = (
                f'<text x="{element.position.x + 8}" y="{element.position.y - 8}" '
                f'font-size="12" fill="{escape(element.style.stroke, quote=True)}">'
                f"{escape(element.label)}</text>"
            )
        return (
            f'<g id="{escape(element.id, quote=True)}" data-element-type="junction"{common}>'
            f'<circle cx="{element.position.x}" cy="{element.position.y}" r="{element.radius}" '
            f'fill="{escape(element.style.stroke, quote=True)}" '
            f'stroke="{escape(element.style.stroke, quote=True)}" '
            f'opacity="{element.style.opacity}" />{label}</g>'
        )
    if element.type == "connector":
        return (
            f'<polyline id="{escape(element.id, quote=True)}" points="{_points(element.points)}"'
            f'{attrs}{common} data-process-tag="{escape(element.process_tag, quote=True)}" '
            f'data-medium="{escape(element.medium, quote=True)}" '
            f'data-nominal-diameter="{escape(element.nominal_diameter, quote=True)}" '
            f'data-flow-direction="{element.flow_direction}" '
            f'data-routing="{escape(element.routing, quote=True)}" />'
        )
    if element.type == "symbol":
        definition = registry.get(element.symbol_key)
        sx = element.width / definition.width
        sy = element.height / definition.height
        embedded_off_page_label = element.metadata.get("embedded_off_page_label")
        has_embedded = isinstance(embedded_off_page_label, str) and bool(embedded_off_page_label)
        text_overrides = element.metadata.get("text_overrides")
        if not isinstance(text_overrides, dict):
            text_overrides = {}
        rendered_shapes: list[str] = []
        for index, shape in enumerate(definition.shapes):
            if has_embedded and shape.get("type") == "text":
                continue
            if (
                not has_embedded
                and shape.get("type") == "text"
                and str(index) in text_overrides
            ):
                override = text_overrides[str(index)]
                if isinstance(override, dict) and "x" in override and "y" in override:
                    shape = {**shape, "x": override["x"], "y": override["y"]}
            rendered_shapes.append(
                _render_symbol_shape(shape, counter_rotation=element.rotation)
            )
        shapes = "".join(rendered_shapes)
        if isinstance(embedded_off_page_label, str) and embedded_off_page_label:
            label_font_size = max(
                7.0,
                min(13.0, 96.0 / max(1, len(embedded_off_page_label))),
            )
            label_x = definition.width / 2
            label_y = definition.height / 2
            label_transform = (
                f' transform="rotate({-element.rotation:g} {label_x} {label_y})"'
                if element.rotation
                else ""
            )
            shapes += (
                f'<text x="{label_x}" y="{label_y}" text-anchor="middle" '
                f'font-size="{label_font_size:g}" fill="{escape(element.style.stroke, quote=True)}"'
                f'{label_transform}>'
                f"{escape(embedded_off_page_label)}</text>"
            )
        label = ""
        if element.label:
            label_x = definition.width / 2
            label_y = definition.height + 16
            transform = (
                f' transform="rotate({-element.rotation} {label_x} {label_y})"'
                if element.rotation
                else ""
            )
            label = (
                f'<text x="{label_x}" y="{label_y}" text-anchor="middle" '
                f'font-size="12" fill="{escape(element.style.stroke, quote=True)}"{transform}>'
                f"{escape(element.label)}</text>"
            )
        return (
            f'<g id="{escape(element.id, quote=True)}" '
            f'transform="translate({element.position.x} {element.position.y}) '
            f'rotate({element.rotation} {element.width / 2} {element.height / 2}) scale({sx} {sy})"'
            f'{attrs}{common} data-symbol-key="{escape(element.symbol_key, quote=True)}">{shapes}{label}</g>'
        )
    return ""


def _path_point(points: list[Point], fraction: float) -> tuple[Point, float]:
    segments = [
        (first, second, ((second.x - first.x) ** 2 + (second.y - first.y) ** 2) ** 0.5)
        for first, second in zip(points, points[1:], strict=False)
    ]
    total = sum(length for _, _, length in segments)
    if total <= 0:
        return points[0], 0.0
    target = total * fraction
    walked = 0.0
    for first, second, length in segments:
        if walked + length >= target and length > 0:
            ratio = (target - walked) / length
            point = Point(
                x=first.x + (second.x - first.x) * ratio,
                y=first.y + (second.y - first.y) * ratio,
            )
            return point, atan2(second.y - first.y, second.x - first.x)
        walked += length
    first, second, _ = segments[-1]
    return second, atan2(second.y - first.y, second.x - first.x)


def _render_arrow(connector: ConnectorElement) -> str:
    if connector.flow_direction == "none":
        return ""
    fraction = {"start": 0.15, "middle": 0.5, "end": 0.85}[connector.arrow_position]
    point, angle = _path_point(connector.points, fraction)
    if connector.flow_direction == "reverse":
        angle += 3.141592653589793
    size = max(6.0, connector.style.stroke_width * 3.2)
    tip = (point.x + cos(angle) * size, point.y + sin(angle) * size)
    left = (
        point.x + cos(angle + 2.45) * size,
        point.y + sin(angle + 2.45) * size,
    )
    right = (
        point.x + cos(angle - 2.45) * size,
        point.y + sin(angle - 2.45) * size,
    )
    return (
        f'<polygon data-arrow-for="{escape(connector.id, quote=True)}" '
        f'points="{tip[0]},{tip[1]} {left[0]},{left[1]} {right[0]},{right[1]}" '
        f'fill="{escape(connector.style.stroke, quote=True)}" opacity="{connector.style.opacity}" />'
    )


def _arrow_connectors(connectors: list[ConnectorElement]) -> list[ConnectorElement]:
    """Render one arrow for each logical route and declared direction.

    Instrument taps split a logical pipe into multiple connector elements. Flow
    semantics stay on every segment, while the drawing should not expose those
    internal splits as a row of repeated arrowheads.
    """

    selected: dict[tuple[str, str], ConnectorElement] = {}
    lengths: dict[tuple[str, str], float] = {}
    for connector in connectors:
        if connector.flow_direction == "none":
            continue
        route_value = connector.metadata.get("main_route_id")
        route_id = route_value if isinstance(route_value, str) and route_value else connector.id
        key = (route_id, connector.flow_direction)
        length = sum(
            abs(second.x - first.x) + abs(second.y - first.y)
            for first, second in zip(connector.points, connector.points[1:], strict=False)
        )
        current = selected.get(key)
        if current is None or length > lengths[key] or (
            length == lengths[key] and connector.id < current.id
        ):
            selected[key] = connector
            lengths[key] = length
    selected_ids = {connector.id for connector in selected.values()}
    return [connector for connector in connectors if connector.id in selected_ids]


def _crossing(first: Point, second: Point, third: Point, fourth: Point) -> Point | None:
    first_horizontal = first.y == second.y
    third_horizontal = third.y == fourth.y
    if first_horizontal == third_horizontal:
        return None
    horizontal_start, horizontal_end = (first, second) if first_horizontal else (third, fourth)
    vertical_start, vertical_end = (third, fourth) if first_horizontal else (first, second)
    x = vertical_start.x
    y = horizontal_start.y
    if not (
        min(horizontal_start.x, horizontal_end.x) < x < max(horizontal_start.x, horizontal_end.x)
        and min(vertical_start.y, vertical_end.y) < y < max(vertical_start.y, vertical_end.y)
    ):
        return None
    return Point(x=x, y=y)


def _shares_endpoint(left: ConnectorElement, right: ConnectorElement) -> bool:
    left_ids = {
        endpoint.element_id
        for endpoint in (left.source, left.target)
        if endpoint and endpoint.element_id
    }
    return any(
        endpoint and endpoint.element_id in left_ids
        for endpoint in (right.source, right.target)
    )


def _segment_cells(record: _SegmentRecord, cell_size: float) -> set[tuple[int, int]]:
    x1 = floor(min(record.first.x, record.second.x) / cell_size)
    x2 = floor(max(record.first.x, record.second.x) / cell_size)
    y1 = floor(min(record.first.y, record.second.y) / cell_size)
    y2 = floor(max(record.first.y, record.second.y) / cell_size)
    return {(x, y) for x in range(x1, x2 + 1) for y in range(y1, y2 + 1)}


def _render_jumps(connectors: list[ConnectorElement], background: str, cell_size: float = 240) -> str:
    records: list[_SegmentRecord] = []
    cells: dict[tuple[int, int], list[int]] = defaultdict(list)
    for connector in connectors:
        for index, (first, second) in enumerate(
            zip(connector.points, connector.points[1:], strict=False)
        ):
            record = _SegmentRecord(connector, index, first, second)
            record_index = len(records)
            records.append(record)
            for cell in _segment_cells(record, cell_size):
                cells[cell].append(record_index)

    pieces: list[str] = []
    for record_index, record in enumerate(records):
        connector = record.connector
        if connector.crossing_style != "jump":
            continue
        candidates: set[int] = set()
        for cell in _segment_cells(record, cell_size):
            candidates.update(cells.get(cell, []))
        seen_points: set[tuple[float, float]] = set()
        for candidate_index in candidates:
            if candidate_index == record_index:
                continue
            other = records[candidate_index]
            if other.connector.id == connector.id or _shares_endpoint(connector, other.connector):
                continue
            point = _crossing(record.first, record.second, other.first, other.second)
            if point is None or (point.x, point.y) in seen_points:
                continue
            seen_points.add((point.x, point.y))
            radius = connector.jump_radius
            mask_width = connector.style.stroke_width + 4
            if record.first.y == record.second.y:
                mask = f'M {point.x - radius} {point.y} L {point.x + radius} {point.y}'
                arc = f'M {point.x - radius} {point.y} Q {point.x} {point.y - radius} {point.x + radius} {point.y}'
            else:
                mask = f'M {point.x} {point.y - radius} L {point.x} {point.y + radius}'
                arc = f'M {point.x} {point.y - radius} Q {point.x + radius} {point.y} {point.x} {point.y + radius}'
            pieces.append(
                f'<path data-jump-for="{escape(connector.id, quote=True)}" data-segment="{record.index}" '
                f'd="{mask}" stroke="{escape(background, quote=True)}" stroke-width="{mask_width}" fill="none" />'
                f'<path d="{arc}" stroke="{escape(connector.style.stroke, quote=True)}" '
                f'stroke-width="{connector.style.stroke_width}" opacity="{connector.style.opacity}" '
                f'fill="none" vector-effect="non-scaling-stroke" />'
            )
    return "".join(pieces)


def _render_svg_content(
    document: Document,
    registry: SymbolRegistry,
    export_bounds: ExportBounds,
) -> tuple[str, int]:
    visible = visible_elements(document)
    rendered_elements = elements_in_bounds(visible, registry, export_bounds)
    connectors = [element for element in rendered_elements if element.type == "connector"]
    body = "".join(_render_element(element, registry) for element in rendered_elements)
    overlays = _render_jumps(connectors, document.canvas.background)
    arrows = "".join(_render_arrow(connector) for connector in _arrow_connectors(connectors))
    background = (
        f'<rect x="{export_bounds.x}" y="{export_bounds.y}" '
        f'width="{export_bounds.width}" height="{export_bounds.height}" '
        f'fill="{escape(document.canvas.background, quote=True)}" />'
    )
    return f"{background}{body}{overlays}{arrows}", len(rendered_elements)


def render_svg_fragment(
    document: Document,
    registry: SymbolRegistry,
    bounds: ExportBounds,
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    preserve_aspect_ratio: str = "none",
) -> str:
    content, rendered_count = _render_svg_content(document, registry, bounds)
    return (
        f'<svg x="{x}" y="{y}" width="{width}" height="{height}" '
        f'viewBox="{bounds.x} {bounds.y} {bounds.width} {bounds.height}" '
        f'font-family="{SVG_FONT_FAMILY}" preserveAspectRatio="{escape(preserve_aspect_ratio, quote=True)}" overflow="hidden" '
        f'data-document-id="{escape(document.id, quote=True)}" '
        f'data-revision="{document.revision}" data-rendered-elements="{rendered_count}">'
        f"{content}</svg>"
    )


def render_svg(
    document: Document,
    registry: SymbolRegistry,
    bounds: ExportBounds | None = None,
) -> str:
    export_bounds = bounds or ExportBounds(0, 0, document.canvas.width, document.canvas.height)
    content, rendered_count = _render_svg_content(document, registry, export_bounds)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{export_bounds.width}" '
        f'height="{export_bounds.height}" '
        f'viewBox="{export_bounds.x} {export_bounds.y} {export_bounds.width} {export_bounds.height}" '
        f'font-family="{SVG_FONT_FAMILY}" data-document-id="{escape(document.id, quote=True)}" data-revision="{document.revision}" '
        f'data-rendered-elements="{rendered_count}">{content}</svg>'
    )


def render_png(
    document: Document,
    registry: SymbolRegistry,
    *,
    output_width: int,
    output_height: int,
    bounds: ExportBounds | None = None,
) -> bytes:
    """Render the canonical SVG scene to PNG using one shared implementation."""
    import cairosvg

    return cairosvg.svg2png(
        bytestring=render_svg(document, registry, bounds).encode("utf-8"),
        output_width=output_width,
        output_height=output_height,
    )
