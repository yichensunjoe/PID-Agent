from __future__ import annotations

from agentcad.agent_semantic_models import (
    ConnectPortsOperation,
    InstrumentTapOperation,
    ReconnectConnectorOperation,
    ReplaceSymbolOperation,
    SafeDeleteElementOperation,
    SemanticAgentPlan,
    SemanticTransaction,
)
from agentcad.model_acceptance import ModelMatrixRequest, run_model_matrix
from agentcad.models import (
    AddElementOperation,
    CreateDocumentRequest,
    Point,
    ProviderConfig,
    SymbolElement,
    TextElement,
    UpdateElementOperation,
)
from agentcad.semantic_compiler_engine import SemanticTransactionCompiler
from agentcad.semantic_planner import SemanticAgentPlanner
from agentcad.service import DocumentService
from agentcad.store import SQLiteDocumentStore
from agentcad.symbols import SymbolRegistry


def _provider() -> ProviderConfig:
    return ProviderConfig(base_url="http://model.test/v1", model="complex-matrix")


def _symbol(symbols, element_id, key, x, y, label=""):
    definition = symbols.get(key)
    return SymbolElement(
        id=element_id,
        symbol_key=key,
        position=Point(x=x, y=y),
        width=definition.width,
        height=definition.height,
        label=label,
    )


def _complex_operations(planner: SemanticAgentPlanner):
    symbols = planner.symbols
    operations = [
        AddElementOperation(element=_symbol(symbols, "waste_in", "system_interface", 80, 380)),
        AddElementOperation(element=_symbol(symbols, "v101", "ball_valve", 260, 380, "V-101")),
        AddElementOperation(element=_symbol(symbols, "e101", "heat_exchanger", 700, 340, "E-101")),
        AddElementOperation(element=_symbol(symbols, "v102", "ball_valve", 1180, 380, "V-102")),
        AddElementOperation(element=_symbol(symbols, "waste_out", "system_interface", 1400, 380)),
        AddElementOperation(element=_symbol(symbols, "air_out", "system_interface", 480, 600)),
        AddElementOperation(element=_symbol(symbols, "air_in", "system_interface", 1000, 600)),
        ConnectPortsOperation(
            connector_id="pipe_inlet",
            source_element_id="waste_in",
            source_port_id="right",
            target_element_id="v101",
            target_port_id="in",
            medium="waste_gas",
            flow_direction="forward",
        ),
        ConnectPortsOperation(
            connector_id="pipe_upstream",
            source_element_id="v101",
            source_port_id="out",
            target_element_id="e101",
            target_port_id="tube_in",
            waypoints=[Point(x=650, y=400), Point(x=650, y=360)],
            medium="waste_gas",
            flow_direction="forward",
        ),
        ConnectPortsOperation(
            connector_id="pipe_downstream",
            source_element_id="e101",
            source_port_id="tube_out",
            target_element_id="v102",
            target_port_id="in",
            waypoints=[Point(x=870, y=390), Point(x=870, y=400)],
            medium="waste_gas",
            flow_direction="forward",
        ),
        ConnectPortsOperation(
            connector_id="pipe_outlet",
            source_element_id="v102",
            source_port_id="out",
            target_element_id="waste_out",
            target_port_id="left",
            medium="waste_gas",
            flow_direction="forward",
        ),
        InstrumentTapOperation(
            main_connector_id="pipe_upstream",
            junction_point=Point(x=420, y=418),
            measurement="pressure",
            instrument_label="PT-101",
            junction_id="j_pt101",
            downstream_connector_id="pipe_upstream_after_pt101",
            root_valve_id="root_pt101",
            instrument_id="pt101",
            junction_to_valve_connector_id="branch_pt101_a",
            valve_to_instrument_connector_id="branch_pt101_b",
        ),
        InstrumentTapOperation(
            main_connector_id="pipe_upstream",
            junction_point=Point(x=560, y=382),
            measurement="temperature",
            instrument_label="TE-101",
            junction_id="j_te101",
            downstream_connector_id="pipe_upstream_after_te101",
            root_valve_id="root_te101",
            instrument_id="te101",
            junction_to_valve_connector_id="branch_te101_a",
            valve_to_instrument_connector_id="branch_te101_b",
        ),
        InstrumentTapOperation(
            main_connector_id="pipe_downstream",
            junction_point=Point(x=930, y=420),
            measurement="pressure",
            instrument_label="PT-102",
            junction_id="j_pt102",
            downstream_connector_id="pipe_downstream_after_pt102",
            root_valve_id="root_pt102",
            instrument_id="pt102",
            junction_to_valve_connector_id="branch_pt102_a",
            valve_to_instrument_connector_id="branch_pt102_b",
        ),
        InstrumentTapOperation(
            main_connector_id="pipe_downstream",
            junction_point=Point(x=1050, y=450),
            measurement="temperature",
            instrument_label="TE-102",
            junction_id="j_te102",
            downstream_connector_id="pipe_downstream_after_te102",
            root_valve_id="root_te102",
            instrument_id="te102",
            junction_to_valve_connector_id="branch_te102_a",
            valve_to_instrument_connector_id="branch_te102_b",
        ),
        ConnectPortsOperation(
            connector_id="air_inlet_pipe",
            source_element_id="air_in",
            source_port_id="left",
            target_element_id="e101",
            target_port_id="shell_out",
            waypoints=[Point(x=1000, y=540), Point(x=765, y=540)],
            medium="cooling_air",
            flow_direction="forward",
        ),
        ConnectPortsOperation(
            connector_id="air_outlet_pipe",
            source_element_id="e101",
            source_port_id="shell_in",
            target_element_id="air_out",
            target_port_id="right",
            waypoints=[Point(x=765, y=540), Point(x=600, y=540)],
            medium="cooling_air",
            flow_direction="forward",
        ),
    ]
    for element_id, parent_id, text in [
        ("txt_waste_in", "waste_in", "上游废气来气"),
        ("txt_e101_name", "e101", "气体冷凝器 E-101"),
        ("txt_waste_out", "waste_out", "尾气处理系统"),
        ("txt_air_out", "air_out", "空气出口"),
        ("txt_air_in", "air_in", "空气进口"),
    ]:
        operations.append(
            AddElementOperation(
                element=TextElement(
                    id=element_id,
                    position=Point(x=760, y=400),
                    text=text,
                    anchor="middle",
                    metadata={"parent_element_id": parent_id},
                )
            )
        )
    return operations


def _matrix_plan(self, document_id, request):
    revision = self.service.get_document(document_id).revision
    prompt = request.prompt
    if "复杂冷凝流程图" in prompt:
        operations = _complex_operations(self)
    elif "added_valve" in prompt:
        definition = self.symbols.get("ball_valve")
        operations = [
            AddElementOperation(
                element=SymbolElement(
                    id="added_valve",
                    symbol_key="ball_valve",
                    position=Point(x=850, y=120),
                    width=definition.width,
                    height=definition.height,
                    label="ADDED",
                )
            ),
            ConnectPortsOperation(
                connector_id="added_pipe",
                source_element_id="target",
                source_port_id="out",
                target_element_id="added_valve",
                target_port_id="in",
            ),
        ]
    elif "向右移动" in prompt:
        operations = [
            UpdateElementOperation(
                element_id="target",
                patch={"position": {"x": 400, "y": 120}},
            )
        ]
    elif "替换为" in prompt:
        symbol_key = prompt.split("替换为", 1)[1].split("，", 1)[0].strip()
        operations = [ReplaceSymbolOperation(element_id="target", symbol_key=symbol_key)]
    elif "重新连接" in prompt:
        operations = [
            ReconnectConnectorOperation(
                connector_id="pipe_main",
                endpoint="target",
                element_id="spare",
                port_id="in",
            )
        ]
    else:
        operations = [
            SafeDeleteElementOperation(
                element_id="target",
                connection_policy="delete_connectors",
            )
        ]
    return SemanticAgentPlan(
        explanation="deterministic matrix plan",
        transaction=SemanticTransaction(
            expected_revision=revision,
            label="Matrix scenario",
            operations=operations,
        ),
    )


def test_complex_operations_compile_to_polished_transaction(tmp_path):
    symbols = SymbolRegistry()
    service = DocumentService(SQLiteDocumentStore(tmp_path / "complex.db"), symbols)
    document = service.create_document(CreateDocumentRequest(name="Complex"), source="system")
    planner = SemanticAgentPlanner(service, symbols)
    transaction = SemanticTransaction(
        expected_revision=document.revision,
        label="Complex full diagram",
        operations=_complex_operations(planner),
    )
    compiled = SemanticTransactionCompiler(service).compile(document.id, transaction)

    assert compiled.assessment.valid, compiled.assessment.model_dump_json(indent=2)
    assert compiled.transaction is not None
    assert compiled.annotation_metrics is not None
    assert 30 <= compiled.assessment.resulting_element_count <= 50
    generated = [
        operation.element
        for operation in compiled.transaction.operations
        if isinstance(operation, AddElementOperation)
    ]
    process_connectors = [
        element
        for element in generated
        if element.type == "connector"
        and element.medium in {"waste_gas", "cooling_air"}
        and element.metadata.get("assembly") != "instrument_tap"
    ]
    assert process_connectors
    assert all(connector.flow_direction == "forward" for connector in process_connectors)
    assert not any(
        element.type == "text" and element.text.strip() in {"→", "←"}
        for element in generated
    )


def test_optional_complex_matrix_adds_one_49_element_case(monkeypatch):
    monkeypatch.setattr(SemanticAgentPlanner, "plan", _matrix_plan)
    report = run_model_matrix(
        ModelMatrixRequest(
            provider=_provider(),
            repetitions=1,
            max_replans=1,
            include_complex_diagram=True,
        ),
        SymbolRegistry(),
    )

    assert report.total_cases == 6
    assert report.passed_cases == 6
    complex_case = next(case for case in report.cases if case.scenario == "complex_full_diagram")
    assert complex_case.status == "passed"
    assert complex_case.attempts == 0
    assert complex_case.message == "topology assertion passed"
