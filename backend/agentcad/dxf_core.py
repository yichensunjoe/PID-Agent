from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass
from math import isfinite, pi
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .exporting import ExportBounds
from .models import Document, Element

DxfUnits = Literal["unitless", "mm", "cm", "m", "in", "ft"]
DXF_UNIT_CODES: dict[DxfUnits, int] = {
    "unitless": 0,
    "in": 1,
    "ft": 2,
    "mm": 4,
    "cm": 5,
    "m": 6,
}
DEFAULT_MAX_DXF_ENTITIES = 100_000
_PATH_TOKEN = re.compile(r"([MLQZ])|(-?(?:\d+(?:\.\d*)?|\.\d+))")


class DxfExportError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class DxfExportOptions(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    units: DxfUnits = "mm"
    scale: float = Field(default=1.0, gt=0, le=1000)


@dataclass(frozen=True)
class DxfExportResult:
    payload: str
    entity_count: int
    layer_count: int
    units: DxfUnits
    scale: float


@dataclass(frozen=True)
class _CadPoint:
    x: float
    y: float


@dataclass(frozen=True)
class _DxfEntity:
    kind: str
    pairs: tuple[tuple[int, Any], ...]


def max_dxf_entities() -> int:
    raw = os.getenv("PID_AGENT_MAX_DXF_ENTITIES", str(DEFAULT_MAX_DXF_ENTITIES))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_DXF_ENTITIES
    return max(1000, value)


def _number(value: float | int) -> str:
    if isinstance(value, int):
        return str(value)
    if not isfinite(value):
        raise DxfExportError("invalid_dxf_geometry", "DXF geometry contains a non-finite number")
    normalized = 0.0 if abs(value) < 0.0000005 else value
    text = f"{normalized:.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _pair(code: int, value: Any) -> str:
    return f"{code}\n{_number(value) if isinstance(value, (int, float)) else value}\n"


def _clean_text(value: str, *, limit: int = 250) -> str:
    cleaned = " ".join(value.replace("\r", " ").replace("\n", " ").replace("\t", " ").split())
    return cleaned[:limit]


def _true_color(stroke: str) -> int | None:
    value = stroke.strip()
    if re.fullmatch(r"#[0-9a-fA-F]{6}", value):
        return int(value[1:], 16)
    if re.fullmatch(r"#[0-9a-fA-F]{3}", value):
        return int("".join(character * 2 for character in value[1:]), 16)
    return None


def _safe_layer_component(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", normalized).strip("_")
    return cleaned[:48]


def _layer_names(document: Document, elements: list[Element]) -> dict[str, str]:
    used = {element.layer_id for element in elements}
    mapping: dict[str, str] = {}
    occupied: set[str] = {"0", "DEFPOINTS"}
    for layer in document.layers:
        if layer.id not in used:
            continue
        component = _safe_layer_component(layer.name) or _safe_layer_component(layer.id) or "LAYER"
        base = f"PID_{component}"[:60]
        candidate = base
        suffix = 2
        while candidate.upper() in occupied:
            marker = f"_{suffix}"
            candidate = f"{base[: 60 - len(marker)]}{marker}"
            suffix += 1
        mapping[layer.id] = candidate
        occupied.add(candidate.upper())
    for layer_id in sorted(used - set(mapping)):
        component = _safe_layer_component(layer_id) or "LAYER"
        mapping[layer_id] = f"PID_{component}"[:60]
    return mapping


class _Builder:
    def __init__(self, bounds: ExportBounds, scale: float, layer_names: dict[str, str]):
        self.bounds = bounds
        self.scale = scale
        self.layer_names = layer_names
        self.entities: list[_DxfEntity] = []

    def point(self, x: float, y: float) -> _CadPoint:
        return _CadPoint(
            x=(x - self.bounds.x) * self.scale,
            y=(self.bounds.y + self.bounds.height - y) * self.scale,
        )

    def layer(self, element: Element) -> str:
        return self.layer_names.get(element.layer_id, "0")

    def _common(
        self,
        element: Element,
        *,
        subtype: str | None = None,
        extra_metadata: list[str] | None = None,
    ) -> tuple[list[tuple[int, Any]], list[tuple[int, Any]]]:
        common: list[tuple[int, Any]] = [(100, "AcDbEntity"), (8, self.layer(element))]
        if element.style.dash:
            common.append((6, "DASHED"))
        color = _true_color(element.style.stroke)
        if color is not None:
            common.append((420, color))
        metadata = [
            f"element_id={element.id}",
            f"element_type={subtype or element.type}",
            f"system_id={element.system_id}",
        ]
        if element.name:
            metadata.append(f"name={_clean_text(element.name, limit=180)}")
        metadata.extend(extra_metadata or [])
        xdata: list[tuple[int, Any]] = [(1001, "PID_AGENT")]
        xdata.extend((1000, _clean_text(item)) for item in metadata)
        return common, xdata

    def add(self, kind: str, pairs: list[tuple[int, Any]]) -> None:
        self.entities.append(_DxfEntity(kind=kind, pairs=tuple(pairs)))

    def line(self, element: Element, first: tuple[float, float], second: tuple[float, float], *, subtype: str | None = None) -> None:
        start = self.point(*first)
        end = self.point(*second)
        if start == end:
            return
        common, xdata = self._common(element, subtype=subtype)
        pairs = common + [(100, "AcDbLine")]
        pairs.extend([(10, start.x), (20, start.y), (30, 0.0), (11, end.x), (21, end.y), (31, 0.0)])
        self.add("LINE", pairs + xdata)

    def polyline(
        self,
        element: Element,
        points: list[tuple[float, float]],
        *,
        closed: bool = False,
        subtype: str | None = None,
        extra_metadata: list[str] | None = None,
    ) -> None:
        transformed = [self.point(x, y) for x, y in points]
        deduplicated: list[_CadPoint] = []
        for point in transformed:
            if not deduplicated or point != deduplicated[-1]:
                deduplicated.append(point)
        if closed and len(deduplicated) > 1 and deduplicated[0] == deduplicated[-1]:
            deduplicated.pop()
        if len(deduplicated) < 2:
            return
        common, xdata = self._common(element, subtype=subtype, extra_metadata=extra_metadata)
        pairs = common + [(100, "AcDbPolyline"), (90, len(deduplicated)), (70, 1 if closed else 0)]
        for point in deduplicated:
            pairs.extend([(10, point.x), (20, point.y)])
        self.add("LWPOLYLINE", pairs + xdata)

    def circle(self, element: Element, center: tuple[float, float], radius: float, *, subtype: str | None = None) -> None:
        cad = self.point(*center)
        common, xdata = self._common(element, subtype=subtype)
        pairs = common + [(100, "AcDbCircle")]
        pairs.extend([(10, cad.x), (20, cad.y), (30, 0.0), (40, radius * self.scale)])
        self.add("CIRCLE", pairs + xdata)

    def ellipse(
        self,
        element: Element,
        center: tuple[float, float],
        major_axis: tuple[float, float],
        ratio: float,
        *,
        subtype: str | None = None,
    ) -> None:
        cad = self.point(*center)
        common, xdata = self._common(element, subtype=subtype)
        pairs = common + [(100, "AcDbEllipse")]
        pairs.extend(
            [
                (10, cad.x),
                (20, cad.y),
                (30, 0.0),
                (11, major_axis[0] * self.scale),
                (21, -major_axis[1] * self.scale),
                (31, 0.0),
                (40, ratio),
                (41, 0.0),
                (42, 2 * pi),
            ]
        )
        self.add("ELLIPSE", pairs + xdata)

    def text(
        self,
        element: Element,
        position: tuple[float, float],
        text: str,
        height: float,
        *,
        anchor: str = "start",
        rotation: float = 0.0,
        subtype: str | None = None,
    ) -> None:
        cleaned = _clean_text(text)
        if not cleaned:
            return
        cad = self.point(*position)
        horizontal = {"start": 0, "middle": 1, "end": 2}.get(anchor, 0)
        common, xdata = self._common(element, subtype=subtype)
        pairs = common + [(100, "AcDbText")]
        pairs.extend(
            [
                (10, cad.x),
                (20, cad.y),
                (30, 0.0),
                (40, max(height * self.scale, 0.001)),
                (1, cleaned),
                (7, "PID_TEXT"),
                (50, -rotation),
                (72, horizontal),
                (73, 0),
            ]
        )
        if horizontal:
            pairs.extend([(11, cad.x), (21, cad.y), (31, 0.0)])
        pairs.append((100, "AcDbText"))
        self.add("TEXT", pairs + xdata)

    def solid(self, element: Element, points: list[tuple[float, float]], *, subtype: str) -> None:
        if len(points) != 3:
            raise DxfExportError("invalid_dxf_geometry", "DXF solid requires three points")
        cad = [self.point(x, y) for x, y in points]
        common, xdata = self._common(element, subtype=subtype)
        pairs = common + [(100, "AcDbTrace")]
        for index, point in enumerate([cad[0], cad[1], cad[2], cad[2]]):
            x_code = 10 + index
            pairs.extend([(x_code, point.x), (x_code + 10, point.y), (x_code + 20, 0.0)])
        self.add("SOLID", pairs + xdata)


def _table(name: str, records: list[str]) -> str:
    return _pair(0, "TABLE") + _pair(2, name) + _pair(70, len(records)) + "".join(records) + _pair(0, "ENDTAB")


def _layer_record(name: str) -> str:
    return (
        _pair(0, "LAYER")
        + _pair(2, name)
        + _pair(70, 0)
        + _pair(62, 7)
        + _pair(6, "CONTINUOUS")
    )


def _block(name: str) -> str:
    return (
        _pair(0, "BLOCK")
        + _pair(8, "0")
        + _pair(2, name)
        + _pair(70, 0)
        + _pair(10, 0.0)
        + _pair(20, 0.0)
        + _pair(30, 0.0)
        + _pair(3, name)
        + _pair(1, "")
        + _pair(0, "ENDBLK")
        + _pair(8, "0")
    )


def _document_payload(
    document: Document,
    bounds: ExportBounds,
    options: DxfExportOptions,
    layer_names: dict[str, str],
    entities: list[_DxfEntity],
) -> str:
    width = bounds.width * options.scale
    height = bounds.height * options.scale
    header = (
        _pair(0, "SECTION")
        + _pair(2, "HEADER")
        + _pair(9, "$ACADVER")
        + _pair(1, "AC1027")
        + _pair(9, "$DWGCODEPAGE")
        + _pair(3, "UTF-8")
        + _pair(9, "$INSUNITS")
        + _pair(70, DXF_UNIT_CODES[options.units])
        + _pair(9, "$EXTMIN")
        + _pair(10, 0.0)
        + _pair(20, 0.0)
        + _pair(30, 0.0)
        + _pair(9, "$EXTMAX")
        + _pair(10, width)
        + _pair(20, height)
        + _pair(30, 0.0)
        + _pair(9, "$HANDSEED")
        + _pair(5, "FFFF")
        + _pair(0, "ENDSEC")
    )
    ltype_records = [
        _pair(0, "LTYPE") + _pair(2, "CONTINUOUS") + _pair(70, 0) + _pair(3, "Solid line") + _pair(72, 65) + _pair(73, 0) + _pair(40, 0.0),
        _pair(0, "LTYPE") + _pair(2, "DASHED") + _pair(70, 0) + _pair(3, "Dashed") + _pair(72, 65) + _pair(73, 2) + _pair(40, 12.0) + _pair(49, 8.0) + _pair(74, 0) + _pair(49, -4.0) + _pair(74, 0),
    ]
    layer_records = [_layer_record("0"), *[_layer_record(name) for name in layer_names.values()]]
    style_records = [
        _pair(0, "STYLE") + _pair(2, "PID_TEXT") + _pair(70, 0) + _pair(40, 0.0) + _pair(41, 1.0) + _pair(50, 0.0) + _pair(71, 0) + _pair(42, 2.5) + _pair(3, "Noto Sans CJK SC") + _pair(4, "")
    ]
    appid_records = [_pair(0, "APPID") + _pair(2, "PID_AGENT") + _pair(70, 0)]
    block_records = [
        _pair(0, "BLOCK_RECORD") + _pair(2, "*Model_Space") + _pair(70, 0),
        _pair(0, "BLOCK_RECORD") + _pair(2, "*Paper_Space") + _pair(70, 0),
    ]
    tables = (
        _pair(0, "SECTION")
        + _pair(2, "TABLES")
        + _table("LTYPE", ltype_records)
        + _table("LAYER", layer_records)
        + _table("STYLE", style_records)
        + _table("APPID", appid_records)
        + _table("BLOCK_RECORD", block_records)
        + _pair(0, "ENDSEC")
    )
    blocks = (
        _pair(0, "SECTION")
        + _pair(2, "BLOCKS")
        + _block("*Model_Space")
        + _block("*Paper_Space")
        + _pair(0, "ENDSEC")
    )
    entity_text = "".join(
        _pair(0, entity.kind) + "".join(_pair(code, value) for code, value in entity.pairs)
        for entity in entities
    )
    entities_section = _pair(0, "SECTION") + _pair(2, "ENTITIES") + entity_text + _pair(0, "ENDSEC")
    comments = (
        _pair(999, "Generated by P&ID-Agent")
        + _pair(999, f"document_id={_clean_text(document.id)}")
        + _pair(999, f"revision={document.revision}")
        + _pair(999, f"units={options.units};scale={_number(options.scale)}")
    )
    return comments + header + tables + blocks + entities_section + _pair(0, "EOF")


