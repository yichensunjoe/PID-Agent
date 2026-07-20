import json

from agentcad.agent_semantic_models import (
    ConnectPortsOperation,
    FullDiagramTransaction,
    SemanticTransaction,
)
from agentcad.models import (
    AddElementOperation,
    CreateDocumentRequest,
    Point,
    SymbolElement,
    TransactionRequest,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _seed(tmp_path):
    symbols = SymbolRegistry()
    service = DocumentService(SQLiteDocumentStore(tmp_path / "flow.db"), symbols)
    document = service.create_document(CreateDocumentRequest(name="Flow semantics"), source="system")
    definition = symbols.get("ball_valve")
    source = SymbolElement(
        id="source",
        symbol_key=definition.key,
        position=Point(x=100, y=100),
        width=definition.width,
        height=definition.height,
    )
    target = SymbolElement(
        id="target",
        symbol_key=definition.key,
        position=Point(x=500, y=220),
        width=definition.width,
        height=definition.height,
    )
    document = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
            ],
        ),
        source="system",
    ).document
    return service, document


def _compiled_connector(compiled, connector_id):
    assert compiled.assessment.valid, compiled.assessment.model_dump(mode="json")
    assert compiled.transaction is not None
    return next(
        operation.element
        for operation in compiled.transaction.operations
        if isinstance(operation, AddElementOperation)
        and operation.element.type == "connector"
        and operation.element.id == connector_id
    )


def test_full_diagram_schema_tells_models_to_use_connector_flow_not_arrow_text():
    schema_text = json.dumps(FullDiagramTransaction.model_json_schema(), ensure_ascii=False)

    assert "flow_direction" in schema_text
    assert "source→target" in schema_text
    assert "standalone arrow text" in schema_text


def test_automatic_connect_ports_preserves_flow_arrow_properties(tmp_path):
    service, document = _seed(tmp_path)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                ConnectPortsOperation(
                    connector_id="automatic",
                    source_element_id="source",
                    source_port_id="out",
                    target_element_id="target",
                    target_port_id="in",
                    flow_direction="forward",
                    arrow_position="end",
                    crossing_style="jump",
                    jump_radius=9,
                )
            ],
        ),
    )

    connector = _compiled_connector(compiled, "automatic")
    assert connector.flow_direction == "forward"
    assert connector.arrow_position == "end"
    assert connector.crossing_style == "jump"
    assert connector.jump_radius == 9


def test_waypoint_connect_ports_preserves_reverse_flow_properties(tmp_path):
    service, document = _seed(tmp_path)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                ConnectPortsOperation(
                    connector_id="manual",
                    source_element_id="source",
                    source_port_id="out",
                    target_element_id="target",
                    target_port_id="in",
                    waypoints=[Point(x=300, y=120), Point(x=300, y=240)],
                    flow_direction="reverse",
                    arrow_position="middle",
                )
            ],
        ),
    )

    connector = _compiled_connector(compiled, "manual")
    assert connector.routing == "manual"
    assert connector.flow_direction == "reverse"
    assert connector.arrow_position == "middle"
