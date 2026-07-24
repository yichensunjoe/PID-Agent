from __future__ import annotations

from agentcad.flow_topology import (
    build_agent_harness_context,
    flow_rule_findings,
    normalize_flow_medium,
    opc_direction,
    valve_state,
)
from agentcad.models import (
    ConnectorElement,
    ConnectorEndpoint,
    Document,
    JunctionElement,
    Point,
    SymbolElement,
)
from agentcad.symbols import SymbolRegistry


def _junction(element_id: str, x: float) -> JunctionElement:
    return JunctionElement(id=element_id, position=Point(x=x, y=100))


def _valve(state: str | None = None) -> SymbolElement:
    properties = {} if state is None else {"valve_state": state}
    return SymbolElement(
        id="valve_1",
        symbol_key="gate_valve",
        position=Point(x=100, y=70),
        width=60,
        height=50,
        label="XV-101",
        properties=properties,
    )


def _connector(
    element_id: str,
    source_id: str,
    source_port: str,
    target_id: str,
    target_port: str,
    start: Point,
    end: Point,
) -> ConnectorElement:
    return ConnectorElement(
        id=element_id,
        points=[start, end],
        source=ConnectorEndpoint(element_id=source_id, port_id=source_port, point=start),
        target=ConnectorEndpoint(element_id=target_id, port_id=target_port, point=end),
        process_tag="CW-101",
        medium="cooling water",
        nominal_diameter="DN50",
        flow_direction="forward",
        metadata={"main_route_id": "route_1"},
    )


def _document(state: str | None) -> Document:
    return Document(
        id="doc_flow",
        name="Flow topology",
        elements=[
            _junction("source", 0),
            _valve(state),
            _junction("sink", 260),
            _connector(
                "line_in",
                "source",
                "node",
                "valve_1",
                "in",
                Point(x=0, y=100),
                Point(x=100, y=100),
            ),
            _connector(
                "line_out",
                "valve_1",
                "out",
                "sink",
                "node",
                Point(x=160, y=100),
                Point(x=260, y=100),
            ),
        ],
    )


def test_valves_are_normally_open_and_closed_valves_block_directed_flow() -> None:
    registry = SymbolRegistry()
    assert valve_state(_valve()) == "open"
    assert flow_rule_findings(_document(None), registry) == []

    findings = flow_rule_findings(_document("closed"), registry)
    assert len(findings) == 1
    finding = findings[0]
    assert finding.code == "VALVE_CLOSED_BLOCKING_FLOW"
    assert finding.severity == "error"
    assert set(finding.element_ids) == {"valve_1", "line_in", "line_out"}
    assert finding.details["incoming_connector_ids"] == ["line_in"]
    assert finding.details["outgoing_connector_ids"] == ["line_out"]


def test_agent_harness_context_exposes_topology_state_and_contract() -> None:
    registry = SymbolRegistry()
    context = build_agent_harness_context(_document("closed"), registry)
    assert context["schema"] == "pid-agent.agent-harness-context"
    assert context["revision"] == 0
    assert context["connectors"][0]["medium_class"] == "water"
    valve = next(item for item in context["symbols"] if item["id"] == "valve_1")
    assert valve["capability"] == "valve"
    assert valve["valve_state"] == "closed"
    assert valve["default_valve_state"] == "open"
    assert context["flow_findings"][0]["code"] == "VALVE_CLOSED_BLOCKING_FLOW"
    assert any("real symbol ports" in rule for rule in context["engineering_contract"])


def test_opc_symbols_have_opposite_directions_and_are_loaded() -> None:
    registry = SymbolRegistry()
    incoming = registry.get("off_page_connector_in")
    outgoing = registry.get("off_page_connector_out")
    assert incoming.metadata["capability"] == "opc"
    assert outgoing.metadata["capability"] == "opc"
    assert incoming.ports[0].direction == "out"
    assert outgoing.ports[0].direction == "in"

    symbol = SymbolElement(
        symbol_key="off_page_connector_in",
        position=Point(x=0, y=0),
        width=incoming.width,
        height=incoming.height,
        properties={"target_document_id": "doc_2"},
    )
    assert opc_direction(symbol, registry) == "in"
    assert normalize_flow_medium("instrument air") == "gas"
