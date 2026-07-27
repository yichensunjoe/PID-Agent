from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Any, Literal

from .models import ConnectorElement, Document, SymbolElement
from .symbols import SymbolRegistry

FlowMedium = Literal["water", "gas", "other"]
ValveState = Literal["open", "closed"]

_WATER_NAMES = {
    "water",
    "h2o",
    "cw",
    "chw",
    "hw",
    "cooling water",
    "chilled water",
    "hot water",
    "水",
    "冷却水",
    "冷冻水",
    "热水",
}
_GAS_NAMES = {
    "gas",
    "air",
    "steam",
    "natural gas",
    "fuel gas",
    "instrument air",
    "气体",
    "空气",
    "蒸汽",
    "天然气",
    "燃气",
}
_CLOSED_STATES = {"closed", "close", "shut", "blocked", "off", "关", "关闭", "已关"}


@dataclass(frozen=True)
class FlowFinding:
    severity: Literal["info", "warning", "error"]
    code: str
    message: str
    element_ids: tuple[str, ...]
    details: dict[str, Any]


def normalize_flow_medium(value: str) -> FlowMedium:
    normalized = " ".join(value.strip().casefold().replace("_", " ").replace("-", " ").split())
    if normalized in _WATER_NAMES or "water" in normalized or "水" in normalized:
        return "water"
    if normalized in _GAS_NAMES or any(
        token in normalized for token in (" gas", "air", "steam", "气", "蒸汽")
    ):
        return "gas"
    return "other"


def is_valve_symbol(symbol: SymbolElement, registry: SymbolRegistry) -> bool:
    try:
        definition = registry.get(symbol.symbol_key)
    except KeyError:
        return "valve" in symbol.symbol_key.casefold()
    capability = str(definition.metadata.get("capability", "")).casefold()
    return (
        capability == "valve"
        or "阀" in definition.category
        or "valve" in symbol.symbol_key.casefold()
    )


def valve_state(symbol: SymbolElement) -> ValveState:
    value = str(symbol.properties.get("valve_state", "open")).strip().casefold()
    return "closed" if value in _CLOSED_STATES else "open"


def is_opc_symbol(symbol: SymbolElement, registry: SymbolRegistry) -> bool:
    try:
        definition = registry.get(symbol.symbol_key)
    except KeyError:
        return symbol.symbol_key.startswith("off_page_connector_")
    return (
        str(definition.metadata.get("capability", "")).casefold() == "opc"
        or symbol.symbol_key.startswith("off_page_connector_")
    )


def opc_direction(symbol: SymbolElement, registry: SymbolRegistry) -> Literal["in", "out"] | None:
    explicit = str(symbol.properties.get("opc_direction", "")).strip().casefold()
    if explicit in {"in", "out"}:
        return explicit  # type: ignore[return-value]
    try:
        definition = registry.get(symbol.symbol_key)
    except KeyError:
        definition = None
    metadata_value = (
        str(definition.metadata.get("opc_direction", "")).strip().casefold()
        if definition
        else ""
    )
    if metadata_value in {"in", "out"}:
        return metadata_value  # type: ignore[return-value]
    if symbol.symbol_key.endswith("_in"):
        return "in"
    if symbol.symbol_key.endswith("_out"):
        return "out"
    return None


def _directed_element_ids(connector: ConnectorElement) -> tuple[str | None, str | None]:
    source_id = connector.source.element_id if connector.source else None
    target_id = connector.target.element_id if connector.target else None
    if connector.flow_direction == "forward":
        return source_id, target_id
    if connector.flow_direction == "reverse":
        return target_id, source_id
    return None, None


def blocked_downstream_connectors(
    document: Document,
    registry: SymbolRegistry,
) -> dict[str, tuple[str, ...]]:
    """Return directed connector ids isolated downstream of each closed valve.

    Operating state affects flow semantics and visualization, but never invalidates a
    drawing transaction. Connectors without a declared flow direction are excluded
    because upstream/downstream cannot be determined reliably.
    """

    closed_valves = {
        element.id
        for element in document.elements
        if element.type == "symbol"
        and is_valve_symbol(element, registry)
        and valve_state(element) == "closed"
    }
    outgoing: dict[str, list[ConnectorElement]] = defaultdict(list)
    for element in document.elements:
        if element.type != "connector":
            continue
        upstream_id, _ = _directed_element_ids(element)
        if upstream_id:
            outgoing[upstream_id].append(element)

    result: dict[str, tuple[str, ...]] = {}
    for valve_id in sorted(closed_valves):
        blocked: set[str] = set()
        queue: deque[str] = deque([valve_id])
        visited_elements: set[str] = set()
        while queue:
            element_id = queue.popleft()
            if element_id in visited_elements:
                continue
            visited_elements.add(element_id)
            for connector in outgoing.get(element_id, []):
                if connector.id in blocked:
                    continue
                blocked.add(connector.id)
                _, downstream_id = _directed_element_ids(connector)
                if downstream_id and downstream_id not in closed_valves:
                    queue.append(downstream_id)
        if blocked:
            result[valve_id] = tuple(sorted(blocked))
    return result


def flow_rule_findings(document: Document, registry: SymbolRegistry) -> list[FlowFinding]:
    findings: list[FlowFinding] = []
    element_map = {element.id: element for element in document.elements}
    connector_map = {
        element.id: element for element in document.elements if element.type == "connector"
    }
    for valve_id, connector_ids in blocked_downstream_connectors(document, registry).items():
        valve = element_map[valve_id]
        assert valve.type == "symbol"
        media = sorted(
            {
                normalize_flow_medium(connector_map[connector_id].medium)
                for connector_id in connector_ids
                if connector_id in connector_map
            }
        )
        display = valve.label.strip() or valve.id
        findings.append(
            FlowFinding(
                severity="info",
                code="VALVE_CLOSED_FLOW_ISOLATION",
                message=(
                    f"阀门 {display} 已关闭，其下游 "
                    f"{', '.join(media) or 'process'} 介质流动已停止。"
                ),
                element_ids=(valve_id, *connector_ids),
                details={
                    "valve_id": valve_id,
                    "valve_state": "closed",
                    "blocked_connector_ids": list(connector_ids),
                    "media": media,
                    "drawing_blocked": False,
                },
            )
        )
    return findings


def build_agent_harness_context(document: Document, registry: SymbolRegistry) -> dict[str, Any]:
    findings = flow_rule_findings(document, registry)
    blocked_connector_ids = {
        connector_id
        for finding in findings
        for connector_id in finding.details.get("blocked_connector_ids", [])
    }
    symbols: list[dict[str, Any]] = []
    connectors: list[dict[str, Any]] = []
    for element in document.elements:
        if element.type == "symbol":
            try:
                definition = registry.get(element.symbol_key)
            except KeyError:
                definition = None
            record: dict[str, Any] = {
                "id": element.id,
                "symbol_key": element.symbol_key,
                "label": element.label,
                "ports": [
                    {
                        "id": port.id,
                        "direction": port.direction,
                        "medium": port.medium,
                    }
                    for port in (definition.ports if definition else [])
                ],
            }
            if is_valve_symbol(element, registry):
                record["capability"] = "valve"
                record["valve_state"] = valve_state(element)
                record["default_valve_state"] = "open"
            if is_opc_symbol(element, registry):
                record["capability"] = "opc"
                record["opc_direction"] = opc_direction(element, registry)
                record["target_document_id"] = element.properties.get("target_document_id")
            symbols.append(record)
        elif element.type == "connector":
            upstream_id, downstream_id = _directed_element_ids(element)
            connectors.append(
                {
                    "id": element.id,
                    "process_tag": element.process_tag,
                    "medium": element.medium,
                    "medium_class": normalize_flow_medium(element.medium),
                    "flow_direction": element.flow_direction,
                    "flow_blocked": element.id in blocked_connector_ids,
                    "upstream_element_id": upstream_id,
                    "downstream_element_id": downstream_id,
                    "source": element.source.model_dump(mode="json") if element.source else None,
                    "target": element.target.model_dump(mode="json") if element.target else None,
                    "main_route_id": element.metadata.get("main_route_id"),
                }
            )
    return {
        "schema": "pid-agent.agent-harness-context",
        "version": 1,
        "document_id": document.id,
        "revision": document.revision,
        "symbols": symbols,
        "connectors": connectors,
        "flow_findings": [
            {
                "severity": finding.severity,
                "code": finding.code,
                "message": finding.message,
                "element_ids": list(finding.element_ids),
                "details": finding.details,
            }
            for finding in findings
        ],
        "engineering_contract": [
            "Use real symbol ports and semantic connector operations; never fake connectivity with decorative lines or arrow text.",
            "Connector medium should be water, gas, or an explicit project medium; use flow_direction for visual direction.",
            "Valve properties.valve_state is open or closed; a missing value means normally open.",
            "A closed valve stops directed downstream medium flow, but operating state must never reject or block drawing edits.",
            "Use junction elements as semantic tees when process connectors intentionally join.",
            "Geometric crossings without a shared junction are non-connecting crossings and should use a jump bridge.",
            "Use 5-unit coordinate increments for precise alignment unless a real symbol port or connector intersection supplies the exact point.",
            "Use off_page_connector_in/out for cross-drawing boundaries and set properties.target_document_id.",
            "Preserve document_id and expected_revision and avoid changing unrelated elements.",
        ],
    }
