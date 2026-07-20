from agentcad.agent_semantic_models import ConnectPortsOperation, SemanticTransaction
from agentcad.models import AddElementOperation, CreateDocumentRequest, Point, SymbolElement, TransactionRequest
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _symbol(symbols: SymbolRegistry, element_id: str, key: str, x: float, y: float) -> SymbolElement:
    definition = symbols.get(key)
    return SymbolElement(
        id=element_id,
        symbol_key=key,
        position=Point(x=x, y=y),
        width=definition.width,
        height=definition.height,
    )


def test_horizontal_shell_exchanger_exposes_two_left_right_streams():
    definition = SymbolRegistry().get("heat_exchanger_horizontal_shell")
    ports = {port.id: port for port in definition.ports}

    assert definition.category == "换热设备"
    assert ports["tube_in"].x == 0
    assert ports["tube_out"].x == definition.width
    assert ports["shell_in"].x == definition.width
    assert ports["shell_out"].x == 0
    assert ports["tube_in"].y != ports["shell_out"].y
    assert "水平" in definition.description
    assert "从右向左" in definition.description


def test_waypoint_route_is_orthogonalized_without_replanning(tmp_path):
    symbols = SymbolRegistry()
    service = DocumentService(SQLiteDocumentStore(tmp_path / "route.db"), symbols)
    document = service.create_document(CreateDocumentRequest(name="Route normalization"), source="system")
    document = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            operations=[
                AddElementOperation(element=_symbol(symbols, "source", "ball_valve", 100, 100)),
                AddElementOperation(element=_symbol(symbols, "target", "ball_valve", 500, 220)),
            ],
        ),
        source="system",
    ).document

    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=document.revision,
            operations=[
                ConnectPortsOperation(
                    connector_id="pipe",
                    source_element_id="source",
                    source_port_id="out",
                    target_element_id="target",
                    target_port_id="in",
                    waypoints=[Point(x=280, y=180), Point(x=420, y=180)],
                    flow_direction="forward",
                )
            ],
        ),
    )

    assert compiled.assessment.valid, compiled.assessment.model_dump_json(indent=2)
    assert compiled.transaction is not None
    connector = next(
        operation.element
        for operation in compiled.transaction.operations
        if isinstance(operation, AddElementOperation)
        and operation.element.type == "connector"
        and operation.element.id == "pipe"
    )
    assert connector.points[0] == Point(x=160, y=120)
    assert connector.points[-1] == Point(x=500, y=240)
    assert all(
        first.x == second.x or first.y == second.y
        for first, second in zip(connector.points, connector.points[1:], strict=False)
    )
    assert connector.metadata["route_normalized"] is True
    assert connector.metadata["requested_waypoints"] == [
        {"x": 280.0, "y": 180.0},
        {"x": 420.0, "y": 180.0},
    ]
    assert connector.flow_direction == "forward"
