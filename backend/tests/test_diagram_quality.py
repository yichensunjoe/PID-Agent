from pathlib import Path

from agentcad.agent_semantic_models import ConnectPortsOperation, SemanticTransaction
from agentcad.diagram_quality import analyze_diagram_quality
from agentcad.models import (
    AddElementOperation,
    ConnectorElement,
    CreateDocumentRequest,
    Document,
    Point,
    SymbolElement,
    TransactionRequest,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _service(tmp_path: Path) -> DocumentService:
    return DocumentService(SQLiteDocumentStore(tmp_path / "quality.db"), SymbolRegistry())


def _symbol(service: DocumentService, element_id: str, key: str, x: float, y: float):
    definition = service.symbols.get(key)
    return SymbolElement(
        id=element_id,
        symbol_key=key,
        position=Point(x=x, y=y),
        width=definition.width,
        height=definition.height,
    )


def test_compiler_routes_from_pump_discharge_and_into_target_port_side(tmp_path: Path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Port-aware routing"))
    pump = _symbol(service, "pump", "centrifugal_pump", 100, 300)
    valve = _symbol(service, "valve", "ball_valve", 420, 150)
    seeded = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=0,
            operations=[
                AddElementOperation(element=pump),
                AddElementOperation(element=valve),
            ],
        ),
    ).document
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=seeded.revision,
            operations=[
                ConnectPortsOperation(
                    connector_id="pump_discharge",
                    source_element_id="pump",
                    source_port_id="discharge",
                    target_element_id="valve",
                    target_port_id="in",
                    flow_direction="forward",
                )
            ],
        ),
    )

    assert compiled.assessment.valid is True
    assert compiled.transaction is not None
    result = service.apply_transaction(document.id, compiled.transaction).document
    connector = next(item for item in result.elements if item.id == "pump_discharge")
    assert connector.type == "connector"
    assert connector.points[1].x == connector.points[0].x
    assert connector.points[1].y < connector.points[0].y
    assert connector.points[-2].x < connector.points[-1].x
    assert connector.points[-2].y == connector.points[-1].y
    assert analyze_diagram_quality(result, service.symbols).passed is True


def test_empty_full_diagram_rejects_inlet_to_inlet_process_flow(tmp_path: Path):
    service = _service(tmp_path)
    document = service.create_document(CreateDocumentRequest(name="Wrong ports"))
    source = _symbol(service, "source", "ball_valve", 100, 200)
    target = _symbol(service, "target", "ball_valve", 500, 200)
    compiled = SemanticTransactionCompiler(service).compile(
        document.id,
        SemanticTransaction(
            expected_revision=0,
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                ConnectPortsOperation(
                    connector_id="wrong_pipe",
                    source_element_id="source",
                    source_port_id="in",
                    target_element_id="target",
                    target_port_id="in",
                    flow_direction="forward",
                ),
            ],
        ),
    )

    assert compiled.assessment.valid is False
    assert compiled.transaction is None
    assert "drafting_port_direction_mismatch" in {
        issue.code for issue in compiled.assessment.issues
    }


def test_quality_requires_jump_for_non_connecting_geometric_crossing():
    horizontal = ConnectorElement(
        id="horizontal",
        points=[Point(x=100, y=200), Point(x=500, y=200)],
        routing="manual",
    )
    vertical = ConnectorElement(
        id="vertical",
        points=[Point(x=300, y=80), Point(x=300, y=360)],
        routing="manual",
    )
    document = Document(elements=[horizontal, vertical])

    failed = analyze_diagram_quality(document, SymbolRegistry())
    assert failed.passed is False
    assert failed.metrics.unbridged_crossings == 1

    vertical.crossing_style = "jump"
    passed = analyze_diagram_quality(
        Document.model_validate(document.model_dump(mode="python")),
        SymbolRegistry(),
    )
    assert passed.passed is True
    assert passed.metrics.geometric_crossings == 1
    assert passed.metrics.unbridged_crossings == 0


def test_empty_document_passes_with_full_score():
    report = analyze_diagram_quality(Document(), SymbolRegistry())
    assert report.passed is True
    assert report.score == 100
    assert report.issues == []
    assert report.metrics.symbol_count == 0
    assert report.metrics.connector_count == 0


def test_rotated_symbol_bounding_box_respects_rotation():
    registry = SymbolRegistry()
    opc = registry.get("off_page_connector_in")
    valve = registry.get("ball_valve")
    # 100×50 符号旋转 90° 后实际占位是 50×100（中心不变）。
    rotated = SymbolElement(
        id="rotated",
        symbol_key="off_page_connector_in",
        position=Point(x=0, y=0),
        width=opc.width,
        height=opc.height,
        rotation=90,
    )
    # 放在未旋转包围盒 (0,0)-(100,50) 的右下方、旋转包围盒 (25,-25)-(75,25) 之外：
    # 只有正确考虑旋转才会认为两者不重叠。
    neighbor = SymbolElement(
        id="neighbor",
        symbol_key="ball_valve",
        position=Point(x=80, y=-20),
        width=valve.width,
        height=valve.height,
    )
    report = analyze_diagram_quality(Document(elements=[rotated, neighbor]), registry)
    assert report.metrics.node_overlaps == 0
    assert not any(issue.code == "NODE_OVERLAP" for issue in report.issues)


def test_rotated_symbol_bounding_box_still_detects_true_overlap():
    registry = SymbolRegistry()
    opc = registry.get("off_page_connector_in")
    valve = registry.get("ball_valve")
    rotated = SymbolElement(
        id="rotated",
        symbol_key="off_page_connector_in",
        position=Point(x=0, y=0),
        width=opc.width,
        height=opc.height,
        rotation=90,
    )
    # 与旋转包围盒 (25,-25)-(75,25) 真正重叠。
    neighbor = SymbolElement(
        id="neighbor",
        symbol_key="ball_valve",
        position=Point(x=40, y=-20),
        width=valve.width,
        height=valve.height,
    )
    report = analyze_diagram_quality(Document(elements=[rotated, neighbor]), registry)
    assert report.metrics.node_overlaps == 1
    assert any(issue.code == "NODE_OVERLAP" for issue in report.issues)


def test_diagonal_segment_through_equipment_is_detected():
    registry = SymbolRegistry()
    valve = registry.get("ball_valve")
    symbol = SymbolElement(
        id="block",
        symbol_key="ball_valve",
        position=Point(x=200, y=100),
        width=valve.width,
        height=valve.height,
    )
    diagonal = ConnectorElement(
        id="diagonal",
        points=[Point(x=50, y=50), Point(x=400, y=150)],
        routing="manual",
    )
    document = Document(elements=[symbol, diagonal])

    report = analyze_diagram_quality(document, registry)
    codes = {issue.code for issue in report.issues}
    assert "PIPE_THROUGH_EQUIPMENT" in codes
    assert report.metrics.pipe_obstacle_intersections >= 1


def test_diagonal_segment_avoiding_equipment_is_not_false_positive():
    registry = SymbolRegistry()
    valve = registry.get("ball_valve")
    symbol = SymbolElement(
        id="block",
        symbol_key="ball_valve",
        position=Point(x=200, y=100),
        width=valve.width,
        height=valve.height,
    )
    diagonal = ConnectorElement(
        id="diagonal",
        points=[Point(x=50, y=50), Point(x=150, y=150)],
        routing="manual",
    )
    document = Document(elements=[symbol, diagonal])

    report = analyze_diagram_quality(document, registry)
    codes = {issue.code for issue in report.issues}
    # 斜线不穿过设备：只报非正交，不报穿设备（修复前会误报）。
    assert "PIPE_THROUGH_EQUIPMENT" not in codes
    assert "NON_ORTHOGONAL_SEGMENT" in codes
    assert report.metrics.pipe_obstacle_intersections == 0


def test_node_overlap_reported_for_colliding_symbols():
    registry = SymbolRegistry()
    valve = registry.get("ball_valve")
    first = SymbolElement(
        id="first",
        symbol_key="ball_valve",
        position=Point(x=100, y=100),
        width=valve.width,
        height=valve.height,
    )
    second = SymbolElement(
        id="second",
        symbol_key="ball_valve",
        position=Point(x=120, y=110),
        width=valve.width,
        height=valve.height,
    )
    report = analyze_diagram_quality(Document(elements=[first, second]), registry)
    assert report.metrics.node_overlaps == 1
    assert any(issue.code == "NODE_OVERLAP" for issue in report.issues)
    assert report.passed is False


def test_large_diagram_quality_analysis_completes():
    registry = SymbolRegistry()
    valve = registry.get("ball_valve")
    elements = []
    for index in range(120):
        elements.append(
            SymbolElement(
                id=f"symbol_{index}",
                symbol_key="ball_valve",
                position=Point(x=50 + (index % 12) * 160, y=50 + (index // 12) * 120),
                width=valve.width,
                height=valve.height,
            )
        )
    for index in range(100):
        row = index // 10
        elements.append(
            ConnectorElement(
                id=f"pipe_{index}",
                points=[
                    Point(x=110 + (index % 10) * 160, y=80 + row * 120),
                    Point(x=110 + (index % 10) * 160, y=130 + row * 120),
                ],
                routing="manual",
                flow_direction="forward",
            )
        )
    report = analyze_diagram_quality(Document(elements=elements), registry)
    assert report.metrics.symbol_count == 120
    assert report.metrics.connector_count == 100
