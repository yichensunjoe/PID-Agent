from __future__ import annotations

from math import isfinite

from .dxf_core import (
    DXF_UNIT_CODES,
    DxfExportError,
    DxfExportOptions,
    DxfExportResult,
    DxfUnits,
    _Builder,
    _document_payload,
    _layer_names,
    max_dxf_entities,
)
from .dxf_render import render_elements
from .exporting import ExportBounds, elements_in_bounds, visible_elements
from .models import Document
from .symbols import SymbolRegistry


def render_dxf(
    document: Document,
    registry: SymbolRegistry,
    bounds: ExportBounds,
    options: DxfExportOptions | None = None,
    *,
    entity_limit: int | None = None,
) -> DxfExportResult:
    options = options or DxfExportOptions()
    if not all(isfinite(value) for value in (bounds.x, bounds.y, bounds.width, bounds.height)):
        raise DxfExportError("invalid_dxf_geometry", "DXF export bounds must be finite")
    if bounds.width <= 0 or bounds.height <= 0:
        raise DxfExportError(
            "invalid_dxf_geometry", "DXF export bounds must be greater than zero"
        )
    selected = elements_in_bounds(visible_elements(document), registry, bounds)
    layer_names = _layer_names(document, selected)
    builder = _Builder(bounds, options.scale, layer_names)
    render_elements(builder, selected, registry)
    limit = entity_limit if entity_limit is not None else max_dxf_entities()
    if len(builder.entities) > limit:
        raise DxfExportError(
            "dxf_entity_limit_exceeded",
            f"DXF export requires {len(builder.entities)} entities, exceeding the limit of {limit}",
        )
    payload = _document_payload(document, bounds, options, layer_names, builder.entities)
    return DxfExportResult(
        payload=payload,
        entity_count=len(builder.entities),
        layer_count=len(layer_names),
        units=options.units,
        scale=options.scale,
    )


__all__ = [
    "DXF_UNIT_CODES",
    "DxfExportError",
    "DxfExportOptions",
    "DxfExportResult",
    "DxfUnits",
    "max_dxf_entities",
    "render_dxf",
]
