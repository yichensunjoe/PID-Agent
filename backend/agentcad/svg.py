from __future__ import annotations

from html import escape
from math import atan2, cos, sin
from typing import Any

from .models import ConnectorElement, Document, Element, Point, Style
from .symbols import SymbolRegistry


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


def _render_symbol_shape(shape: dict[str, Any]) -> str:
    kind = shape.get("type")
    if kind == "line":
        return f'<line x1="{shape["x1"]}" y1="{shape["y1"]}" x2="{shape["x2"]}" y2="{shape["y2"]}" />'
    if kind == "polyline":
        points = " ".join(f"{x},{y}" for x, y in shape["points"])
        tag = "polygon" if shape.get("closed") else "polyline"
        fill = shape.get("fill", "none")
        return f'<{tag} points="{points}" fill="{escape(str(fill), quote=True)}" />'
    if kind == "rect":
        return (
            f'<rect x="{shape["x"]}" y="{shape["y"]}" '
            f'width="{shape["width"]}" height="{shape["height"]}" '
            f'rx="{shape.get("rx", 0)}" />'
        )
    if kind == "circle":
        return f'<circle cx="{shape["cx"]}" cy="{shape["cy"]}" r="{shape["r"]}" />'
    if kind == "path":
        return f'<path d="{escape(str(shape["d"]), quote=True)}" />'
    if kind == "text":
        return (
            f'<text x="{shape["x"]}" y="{shape["y"]}" '
            f'font-size="{shape.get("font_size", 12)}" text-anchor="{shape.get("anchor", "middle")}">'
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
        shapes = "".join(_render_symbol_shape(shape) for shape in definition.shapes)
        label = ""
        if element.label:
            label = (
                f'<text x="{definition.width / 2}" y="{definition.height + 16}" '
                f'text-anchor="middle" font-size="12" fill="{escape(element.style.stroke, quote=True)}">'
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


def _render_jumps(connector: ConnectorElement, connectors: list[ConnectorElement], background: str) -> str:
    if connector.crossing_style != "jump":
        return ""
    pieces: list[str] = []
    for index, (first, second) in enumerate(zip(connector.points, connector.points[1:], strict=False)):
        for other in connectors:
            if other.id == connector.id:
                continue
            shared = {
                endpoint.element_id
                for endpoint in (connector.source, connector.target)
                if endpoint and endpoint.element_id
            } & {
                endpoint.element_id
                for endpoint in (other.source, other.target)
                if endpoint and endpoint.element_id
            }
            for third, fourth in zip(other.points, other.points[1:], strict=False):
                point = _crossing(first, second, third, fourth)
                if point is None or shared:
                    continue
                radius = connector.jump_radius
                mask_width = connector.style.stroke_width + 4
                if first.y == second.y:
                    mask = f'M {point.x - radius} {point.y} L {point.x + radius} {point.y}'
                    arc = f'M {point.x - radius} {point.y} Q {point.x} {point.y - radius} {point.x + radius} {point.y}'
                else:
                    mask = f'M {point.x} {point.y - radius} L {point.x} {point.y + radius}'
                    arc = f'M {point.x} {point.y - radius} Q {point.x + radius} {point.y} {point.x} {point.y + radius}'
                pieces.append(
                    f'<path data-jump-for="{escape(connector.id, quote=True)}" data-segment="{index}" '
                    f'd="{mask}" stroke="{escape(background, quote=True)}" stroke-width="{mask_width}" fill="none" />'
                    f'<path d="{arc}" stroke="{escape(connector.style.stroke, quote=True)}" '
                    f'stroke-width="{connector.style.stroke_width}" opacity="{connector.style.opacity}" '
                    f'fill="none" vector-effect="non-scaling-stroke" />'
                )
    return "".join(pieces)


def render_svg(document: Document, registry: SymbolRegistry) -> str:
    visible_layers = {layer.id for layer in document.layers if layer.visible}
    visible_systems = {system.id for system in document.systems if system.visible}
    visible_elements = [
        element
        for element in document.elements
        if element.layer_id in visible_layers and element.system_id in visible_systems
    ]
    connectors = [element for element in visible_elements if element.type == "connector"]
    body = "".join(_render_element(element, registry) for element in visible_elements)
    overlays = "".join(_render_jumps(connector, connectors, document.canvas.background) for connector in connectors)
    arrows = "".join(_render_arrow(connector) for connector in connectors)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{document.canvas.width}" '
        f'height="{document.canvas.height}" viewBox="0 0 {document.canvas.width} {document.canvas.height}" '
        f'data-document-id="{escape(document.id, quote=True)}" data-revision="{document.revision}">'
        f'<rect width="100%" height="100%" fill="{escape(document.canvas.background, quote=True)}" />'
        f"{body}{overlays}{arrows}</svg>"
    )
