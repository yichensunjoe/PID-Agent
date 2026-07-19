from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter
from typing import Any, Literal

from pydantic import Field

from .agent_semantic_models import SemanticAgentReplanRequest
from .annotation_layout import measure_annotation_quality, normalize_annotation_text
from .llm import PlannerError
from .models import (
    AddElementOperation,
    AgentGenerateRequest,
    ConnectorElement,
    ConnectorEndpoint,
    CreateDocumentRequest,
    Point,
    ProviderConfig,
    StrictModel,
    SymbolElement,
    TransactionRequest,
)
from .semantic_compiler_engine import SemanticTransactionCompiler
from .semantic_planner import SemanticAgentPlanner
from .service import DocumentService
from .store import SQLiteDocumentStore
from .symbols import SymbolRegistry

MINIMUM_ACCEPTANCE_REPETITIONS = 3


class ModelMatrixRequest(StrictModel):
    provider: ProviderConfig
    repetitions: int = Field(default=3, ge=1, le=5)
    max_replans: int = Field(default=3, ge=0, le=5)
    include_complex_diagram: bool = False


class ModelMatrixCaseResult(StrictModel):
    scenario: str
    repetition: int
    status: Literal["passed", "failed", "blocked"]
    attempts: int = 0
    duration_ms: float = 0
    issue_codes: list[str] = Field(default_factory=list)
    message: str = ""


class ModelMatrixReport(StrictModel):
    provider_base_url: str
    provider_model: str
    repetitions: int
    minimum_acceptance_repetitions: int = MINIMUM_ACCEPTANCE_REPETITIONS
    max_replans: int
    total_cases: int
    passed_cases: int
    failed_cases: int
    blocked_cases: int
    pass_rate: float
    convergence_rate: float
    accepted: bool
    cases: list[ModelMatrixCaseResult]


def _symbol_choices(symbols: SymbolRegistry):
    candidates = []
    for definition in symbols.list():
        ids = {port.id for port in definition.ports}
        if {"in", "out"}.issubset(ids):
            candidates.append(definition)
    if not candidates:
        raise RuntimeError("symbol catalog requires at least one symbol with in/out ports")
    primary = next((item for item in candidates if item.key == "ball_valve"), candidates[0])
    replacement = next((item for item in candidates if item.key != primary.key), primary)
    return primary, replacement


def _symbol(element_id: str, definition, x: float, y: float) -> SymbolElement:
    return SymbolElement(
        id=element_id,
        symbol_key=definition.key,
        position=Point(x=x, y=y),
        width=definition.width,
        height=definition.height,
        label=element_id.upper(),
    )


def _port_point(symbol: SymbolElement, definition, port_id: str) -> Point:
    port = next(port for port in definition.ports if port.id == port_id)
    return Point(
        x=symbol.position.x + (port.x / definition.width) * symbol.width,
        y=symbol.position.y + (port.y / definition.height) * symbol.height,
    )


def _seed(service: DocumentService, symbols: SymbolRegistry):
    primary, replacement = _symbol_choices(symbols)
    document = service.create_document(CreateDocumentRequest(name="Model acceptance"), source="system")
    source = _symbol("source", primary, 100, 120)
    target = _symbol("target", primary, 360, 120)
    spare = _symbol("spare", primary, 620, 260)
    source_point = _port_point(source, primary, "out")
    target_point = _port_point(target, primary, "in")
    connector = ConnectorElement(
        id="pipe_main",
        points=[source_point, target_point],
        source=ConnectorEndpoint(element_id="source", port_id="out", point=source_point),
        target=ConnectorEndpoint(element_id="target", port_id="in", point=target_point),
        routing="manual",
        process_tag="P-100",
    )
    result = service.apply_transaction(
        document.id,
        TransactionRequest(
            expected_revision=document.revision,
            label="Seed model acceptance",
            source="system",
            operations=[
                AddElementOperation(element=source),
                AddElementOperation(element=target),
                AddElementOperation(element=spare),
                AddElementOperation(element=connector),
            ],
        ),
        source="system",
    )
    return result.document, primary, replacement


def _complex_diagram_check(document, symbols: SymbolRegistry) -> bool:
    elements = {element.id: element for element in document.elements}
    required = {
        "waste_in",
        "v101",
        "e101",
        "v102",
        "waste_out",
        "air_in",
        "air_out",
        "j_pt101",
        "j_te101",
        "j_pt102",
        "j_te102",
        "pt101",
        "te101",
        "pt102",
        "te102",
    }
    if not required.issubset(elements):
        return False
    if not 30 <= len(document.elements) <= 50:
        return False
    for instrument_id, label in {
        "pt101": "PT-101",
        "te101": "TE-101",
        "pt102": "PT-102",
        "te102": "TE-102",
    }.items():
        element = elements[instrument_id]
        if element.type != "symbol" or element.label:
            return False
        labels = [
            item
            for item in document.elements
            if item.type == "text"
            and item.metadata.get("parent_element_id") == instrument_id
            and item.text == label
        ]
        if len(labels) != 1:
            return False

    connectors = [element for element in document.elements if element.type == "connector"]
    junction_ids = {"j_pt101", "j_te101", "j_pt102", "j_te102"}
    for junction_id in junction_ids:
        bound = sum(
            1
            for connector in connectors
            for endpoint in (connector.source, connector.target)
            if endpoint
            and endpoint.element_id == junction_id
            and endpoint.port_id == "node"
        )
        if bound < 3:
            return False

    expected_pairs = {
        ("waste_in", "out", "v101", "in"),
        ("v101", "out", "e101", "tube_in"),
        ("e101", "tube_out", "v102", "in"),
        ("v102", "out", "waste_out", "in"),
        ("air_in", "out", "e101", "shell_out"),
        ("e101", "shell_in", "air_out", "in"),
    }
    actual_pairs = {
        (
            connector.source.element_id,
            connector.source.port_id,
            connector.target.element_id,
            connector.target.port_id,
        )
        for connector in connectors
        if connector.source
        and connector.target
        and connector.source.element_id
        and connector.target.element_id
    }
    if not expected_pairs.issubset(actual_pairs):
        return False

    quality = measure_annotation_quality(document, symbols)
    if any(
        (
            quality.duplicate_label_count,
            quality.text_text_overlaps,
            quality.text_symbol_overlaps,
            quality.text_connector_intersections,
        )
    ):
        return False
    normalized_labels = [
        normalize_annotation_text(item.text)
        for item in document.elements
        if item.type == "text" and item.text.strip()
    ]
    return len(normalized_labels) == len(set(normalized_labels))


def _scenario(name: str, primary, replacement, symbols: SymbolRegistry) -> tuple[str, Any]:
    if name == "complex_full_diagram":
        prompt = (
            "生成复杂冷凝流程图：上游废气接口经 V-101、E-101、V-102 到尾气处理接口；"
            "E-101 上下游分别建立 PT 和 TE instrument_tap，共四个真实 junction；"
            "增加使用 E-101 shell_in/shell_out 的冷却空气线路；添加工艺说明文字。"
            "使用给定固定 element id，保持正交连接并避免重复标签。"
        )
        return prompt, lambda document: _complex_diagram_check(document, symbols)
    if name == "add_connect":
        prompt = (
            f"新增一个 {primary.key}，element id 必须为 added_valve，放在 (850,120)，"
            "并新增 connector id added_pipe，从 target.out 连接到 added_valve.in。不要修改其他元素。"
        )

        def check(document):
            added = next((item for item in document.elements if item.id == "added_valve"), None)
            pipe = next((item for item in document.elements if item.id == "added_pipe"), None)
            return bool(
                added
                and added.type == "symbol"
                and pipe
                and pipe.type == "connector"
                and pipe.source
                and pipe.target
                and pipe.source.element_id == "target"
                and pipe.source.port_id == "out"
                and pipe.target.element_id == "added_valve"
                and pipe.target.port_id == "in"
            )

        return prompt, check
    if name == "move":
        prompt = "把 target 设备向右移动 40 个单位，只修改 target 以及保持其相连管线端口绑定所需的内容。"
        return prompt, lambda document: (
            next(item for item in document.elements if item.id == "target").position.x >= 399
        )
    if name == "replace":
        prompt = (
            f"把 target 替换为 {replacement.key}，保持 element id、位号和 pipe_main 的 "
            "connector id 与端口连接。"
        )
        return prompt, lambda document: (
            next(item for item in document.elements if item.id == "target").symbol_key
            == replacement.key
        )
    if name == "reconnect":
        prompt = "把 pipe_main 的 target 端从 target.in 重新连接到 spare.in，保持 connector id 不变。"

        def check(document):
            pipe = next(item for item in document.elements if item.id == "pipe_main")
            return bool(
                pipe.type == "connector"
                and pipe.target
                and pipe.target.element_id == "spare"
                and pipe.target.port_id == "in"
            )

        return prompt, check
    prompt = "删除 target，并级联删除与 target 连接的管线。不要删除 source 或 spare。"

    def check_delete(document):
        ids = {item.id for item in document.elements}
        return "target" not in ids and "pipe_main" not in ids and {"source", "spare"}.issubset(ids)

    return prompt, check_delete


def _run_case(
    provider: ProviderConfig,
    scenario: str,
    repetition: int,
    max_replans: int,
    symbols: SymbolRegistry,
) -> ModelMatrixCaseResult:
    started = perf_counter()
    try:
        with TemporaryDirectory(prefix="pid-agent-matrix-") as directory:
            service = DocumentService(SQLiteDocumentStore(Path(directory) / "matrix.db"), symbols)
            if scenario == "complex_full_diagram":
                primary, replacement = _symbol_choices(symbols)
                document = service.create_document(
                    CreateDocumentRequest(name="Complex full diagram acceptance"),
                    source="system",
                )
            else:
                document, primary, replacement = _seed(service, symbols)
            planner = SemanticAgentPlanner(service, symbols)
            compiler = SemanticTransactionCompiler(service)
            prompt, check = _scenario(scenario, primary, replacement, symbols)
            request = AgentGenerateRequest(
                prompt=prompt,
                context="Model acceptance matrix. Preserve unrelated elements.",
                provider=provider,
                expected_revision=document.revision,
            )
            plan = planner.plan(document.id, request)
            compiled = compiler.compile(document.id, plan.transaction)
            attempts = 0
            issue_codes: list[str] = []
            while not compiled.assessment.valid and attempts < max_replans:
                issue_codes.extend(issue.code for issue in compiled.assessment.issues)
                attempts += 1
                replan_request = SemanticAgentReplanRequest(
                    prompt=prompt,
                    context=request.context,
                    provider=provider,
                    expected_revision=service.get_document(document.id).revision,
                    failed_plan=plan,
                    attempt=attempts,
                )
                plan = planner.replan(document.id, replan_request, compiled.assessment)
                compiled = compiler.compile(document.id, plan.transaction)
            issue_codes.extend(issue.code for issue in compiled.assessment.issues)
            if not compiled.assessment.valid or compiled.transaction is None:
                return ModelMatrixCaseResult(
                    scenario=scenario,
                    repetition=repetition,
                    status="failed",
                    attempts=attempts,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    issue_codes=issue_codes,
                    message="semantic plan did not converge to a valid transaction",
                )
            result = service.apply_transaction(document.id, compiled.transaction, source="llm")
            passed = bool(check(result.document))
            return ModelMatrixCaseResult(
                scenario=scenario,
                repetition=repetition,
                status="passed" if passed else "failed",
                attempts=attempts,
                duration_ms=round((perf_counter() - started) * 1000, 2),
                issue_codes=issue_codes,
                message=(
                    "topology assertion passed"
                    if passed
                    else "transaction applied but final topology assertion failed"
                ),
            )
    except PlannerError as exc:
        return ModelMatrixCaseResult(
            scenario=scenario,
            repetition=repetition,
            status="blocked" if exc.retryable else "failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            message=exc.code,
        )
    except Exception as exc:
        return ModelMatrixCaseResult(
            scenario=scenario,
            repetition=repetition,
            status="failed",
            duration_ms=round((perf_counter() - started) * 1000, 2),
            message=f"{type(exc).__name__}: {exc}",
        )


def run_model_matrix(request: ModelMatrixRequest, symbols: SymbolRegistry) -> ModelMatrixReport:
    provider = request.provider
    scenarios = ["add_connect", "move", "replace", "reconnect", "delete"]
    if request.include_complex_diagram:
        scenarios.append("complex_full_diagram")
    cases = [
        _run_case(provider, scenario, repetition, request.max_replans, symbols)
        for repetition in range(1, request.repetitions + 1)
        for scenario in scenarios
    ]
    passed = sum(case.status == "passed" for case in cases)
    failed = sum(case.status == "failed" for case in cases)
    blocked = sum(case.status == "blocked" for case in cases)
    completed = passed + failed
    repaired_passes = sum(case.status == "passed" and case.attempts > 0 for case in cases)
    repair_candidates = sum(case.attempts > 0 for case in cases)
    pass_rate = passed / completed if completed else 0.0
    convergence_rate = repaired_passes / repair_candidates if repair_candidates else 1.0
    accepted = (
        request.repetitions >= MINIMUM_ACCEPTANCE_REPETITIONS
        and blocked == 0
        and failed == 0
        and passed == len(cases)
    )
    return ModelMatrixReport(
        provider_base_url=provider.base_url or "",
        provider_model=provider.model or "",
        repetitions=request.repetitions,
        max_replans=request.max_replans,
        total_cases=len(cases),
        passed_cases=passed,
        failed_cases=failed,
        blocked_cases=blocked,
        pass_rate=round(pass_rate, 4),
        convergence_rate=round(convergence_rate, 4),
        accepted=accepted,
        cases=cases,
    )
