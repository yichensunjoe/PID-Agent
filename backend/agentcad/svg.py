from __future__ import annotations

from html import escape
from typing import Any

from .models import Document, Element, Style
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
        return (
            f'<line x1="{shape["x1"]}" y1="{shape["y1"]}" x2="{shape["x2"]}" y2="{shape["y2"]}" />'
        )
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
    if element.type == "line":
        return (
            f'<line id="{escape(element.id, quote=True)}" x1="{element.start.x}" '
            f'y1="{element.start.y}" x2="{element.end.x}" y2="{element.end.y}"{attrs} />'
        )
    if element.type == "polyline":
        tag = "polygon" if element.closed else "polyline"
        return f'<{tag} id="{escape(element.id, quote=True)}" points="{_points(element.points)}"{attrs} />'
    if element.type == "rectangle":
        return (
            f'<rect id="{escape(element.id, quote=True)}" x="{element.x}" y="{element.y}" '
            f'width="{element.width}" height="{element.height}" rx="{element.corner_radius}"{attrs} />'
        )
    if element.type == "circle":
        return (
            f'<circle id="{escape(element.id, quote=True)}" cx="{element.center.x}" '
            f'cy="{element.center.y}" r="{element.radius}"{attrs} />'
        )
    if element.type == "text":
        return (
            f'<text id="{escape(element.id, quote=True)}" x="{element.position.x}" '
            f'y="{element.position.y}" font-size="{element.font_size}" '
            f'text-anchor="{element.anchor}" fill="{escape(element.style.stroke, quote=True)}" '
            f'opacity="{element.style.opacity}">{escape(element.text)}</text>'
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
            f'<g id="{escape(element.id, quote=True)}" data-element-type="junction">'
            f'<circle cx="{element.position.x}" cy="{element.position.y}" r="{element.radius}" '
            f'fill="{escape(element.style.stroke, quote=True)}" '
            f'stroke="{escape(element.style.stroke, quote=True)}" '
            f'opacity="{element.style.opacity}" />{label}</g>'
        )
    if element.type == "connector":
        return (
            f'<polyline id="{escape(element.id, quote=True)}" points="{_points(element.points)}"'
            f'{attrs} data-process-tag="{escape(element.process_tag, quote=True)}" '
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
            f'{attrs} data-symbol-key="{escape(element.symbol_key, quote=True)}">{shapes}{label}</g>'
        )
    return ""


def render_svg(document: Document, registry: SymbolRegistry) -> str:
    visible_layers = {layer.id for layer in document.layers if layer.visible}
    body = "".join(
        _render_element(element, registry)
        for element in document.elements
        if element.layer_id in visible_layers
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{document.canvas.width}" '
        f'height="{document.canvas.height}" viewBox="0 0 {document.canvas.width} {document.canvas.height}" '
        f'data-document-id="{escape(document.id, quote=True)}" data-revision="{document.revision}">'
        f'<rect width="100%" height="100%" fill="{escape(document.canvas.background, quote=True)}" />'
        f"{body}</svg>"
    )
