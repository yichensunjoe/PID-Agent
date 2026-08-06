from __future__ import annotations

import json
from collections import Counter
from contextvars import ContextVar
from statistics import median
from time import perf_counter
from typing import Any, Literal

import httpx
from pydantic import Field, ValidationError, model_validator

from .agent_semantic_models import (
    AgentTransactionAssessment,
    ConnectPortsOperation,
    FullDiagramTransaction,
    SemanticAgentPlan,
    SemanticTransaction,
)
from .diagram_quality import port_outward_normal
from .llm import (
    LLMPlanValidationError,
    LLMResponseError,
    OpenAICompatiblePlanner,
    PlannerError,
    ProviderConfig,
    ProviderConnectionError,
    ProviderNetworkPolicyError,
    ProviderResponseTooLargeError,
    ProviderTimeoutError,
)
from .models import (
    AddElementOperation,
    JunctionElement,
    Point,
    ProviderConfig,
    RectangleElement,
    StrictModel,
    Style,
    SymbolElement,
    TextElement,
)
from .provider_compat import (
    completion_budget_fields,
    completion_temperature,
    extract_chat_content,
    is_kimi_k3_provider,
    thinking_request_fields,
)
from .provider_security import (
    ProviderURLPolicyError,
    provider_http_transport,
    request_with_response_limit,
)
from .semantic_planner import SemanticAgentPlanner
from .vision_inputs import multimodal_user_content, reference_image_prompt
from .vision_request_models import (
    AgentImageInput,
    VisionAgentGenerateRequest,
    VisionSemanticAgentReplanRequest,
)


class ProviderVisionUnsupportedError(PlannerError):
    code = "provider_vision_unsupported"
    status_code = 422


def _provider_error_text(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text[:1000]
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            parts = [error.get(key) for key in ("message", "type", "code", "param")]
            text = " ".join(str(part) for part in parts if part)
            if text:
                return text[:1000]
        if isinstance(error, str):
            return error[:1000]
        message = payload.get("message")
        if isinstance(message, str):
            return message[:1000]
    return json.dumps(payload, ensure_ascii=False)[:1000]


def _response_format_rejected(response: httpx.Response) -> bool:
    if response.status_code not in {400, 422}:
        return False
    text = _provider_error_text(response).lower()
    mentions_format = "response_format" in text or "json_object" in text
    rejected = any(
        marker in text
        for marker in (
            "not supported",
            "unsupported",
            "unknown parameter",
            "unrecognized",
            "not allowed",
            "invalid parameter",
        )
    )
    return mentions_format and rejected


def _vision_input_rejected(response: httpx.Response) -> bool:
    if response.status_code not in {400, 415, 422}:
        return False
    text = _provider_error_text(response).lower()
    mentions_image = any(
        marker in text
        for marker in (
            "image_url",
            "image input",
            "image content",
            "images are",
            "vision",
            "multimodal",
        )
    )
    rejected = any(
        marker in text
        for marker in (
            "not supported",
            "unsupported",
            "does not support",
            "text-only",
            "only text",
            "invalid content type",
        )
    )
    return mentions_image and rejected


class _CompactVisualNode(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    symbol_key: str = Field(min_length=1, max_length=120)
    label: str = Field(default="", max_length=240)
    x: float
    y: float
    rotation: float = 0


class _CompactVisualConnection(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=120)
    source_port: str = Field(default="", max_length=120)
    target_id: str = Field(min_length=1, max_length=120)
    target_port: str = Field(default="", max_length=120)
    flow: str = "forward"
    tag: str = Field(default="", max_length=240)
    medium: str = Field(default="", max_length=240)
    color: str = Field(default="black", max_length=40)
    stroke_width: float = Field(default=1.5, ge=0.5, le=10)


class _CompactVisualJunction(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    x: float
    y: float
    label: str = Field(default="", max_length=240)


class _CompactVisualGroup(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=240)
    x: float
    y: float
    width: float = Field(gt=20, le=1600)
    height: float = Field(gt=20, le=900)
    border: Literal["solid", "dashed"] = "dashed"


class _CompactVisualText(StrictModel):
    id: str = Field(min_length=1, max_length=120)
    text: str = Field(min_length=1, max_length=1000)
    x: float
    y: float
    font_size: float = Field(default=14, gt=0, le=60)


class _CompactVisualGraph(StrictModel):
    explanation: str = Field(default="", max_length=2000)
    nodes: list[_CompactVisualNode] = Field(min_length=1, max_length=250)
    connections: list[_CompactVisualConnection] = Field(default_factory=list, max_length=400)
    junctions: list[_CompactVisualJunction] = Field(default_factory=list, max_length=250)
    groups: list[_CompactVisualGroup] = Field(default_factory=list, max_length=80)
    texts: list[_CompactVisualText] = Field(default_factory=list, max_length=250)

    @model_validator(mode="after")
    def validate_ids(self) -> _CompactVisualGraph:
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("compact visual node ids must be unique")
        element_ids = [
            *node_ids,
            *(junction.id for junction in self.junctions),
            *(group.id for group in self.groups),
            *(text.id for text in self.texts),
            *(connection.id for connection in self.connections),
        ]
        if len(element_ids) != len(set(element_ids)):
            raise ValueError("compact visual element ids must be unique")
        return self


class VisionSemanticAgentPlanner(SemanticAgentPlanner):
    """Semantic planner that preserves schema repair and adds validated images."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._request_images: ContextVar[tuple[AgentImageInput, ...]] = ContextVar(
            "pid_agent_request_images",
            default=(),
        )

    def plan(
        self,
        document_id: str,
        request: VisionAgentGenerateRequest,
    ) -> SemanticAgentPlan:
        compact_provider = self._compact_k3_provider(document_id, request)
        if compact_provider is not None:
            evidence = self._extract_k3_visual_evidence(
                compact_provider,
                tuple(request.images),
                request.prompt,
            )
            return self._plan_k3_compact_visual_graph(
                document_id,
                request,
                compact_provider,
                evidence,
            )
        prepared = self._prepare_k3_vision_request(request)
        token = self._request_images.set(tuple(prepared.images))
        try:
            return super().plan(document_id, prepared)
        finally:
            self._request_images.reset(token)

    def replan(
        self,
        document_id: str,
        request: VisionSemanticAgentReplanRequest,
        failure: AgentTransactionAssessment,
    ) -> SemanticAgentPlan:
        compact_provider = self._compact_k3_provider(document_id, request)
        if compact_provider is not None:
            evidence = self._extract_k3_visual_evidence(
                compact_provider,
                tuple(request.images),
                request.prompt,
            )
            return self._plan_k3_compact_visual_graph(
                document_id,
                request,
                compact_provider,
                evidence,
                repair_context=failure.model_dump(mode="json"),
            )
        prepared = self._prepare_k3_vision_request(request)
        token = self._request_images.set(tuple(prepared.images))
        try:
            return super().replan(document_id, prepared, failure)
        finally:
            self._request_images.reset(token)

    def _compact_k3_provider(
        self,
        document_id: str,
        request: VisionAgentGenerateRequest | VisionSemanticAgentReplanRequest,
    ) -> ProviderConfig | None:
        if not request.images or self.service.get_document(document_id).elements:
            return None
        provider = self.provider_transport._resolve_provider(
            request.provider,
            self.provider_transport.provider_policy,
            self.provider_transport.max_timeout_seconds,
        )
        return provider if is_kimi_k3_provider(provider) else None

    def _plan_k3_compact_visual_graph(
        self,
        document_id: str,
        request: VisionAgentGenerateRequest | VisionSemanticAgentReplanRequest,
        provider: ProviderConfig,
        evidence: dict[str, Any],
        *,
        repair_context: dict[str, Any] | None = None,
    ) -> SemanticAgentPlan:
        document = self.service.get_document(document_id)
        compact_provider = provider.model_copy(
            update={"thinking_enabled": True, "thinking_level": "low"}
        )
        system_prompt = self._compact_visual_system_prompt()
        user_context = request.context.partition(
            "Automatic P&ID-Agent Harness Context:"
        )[0].strip()
        user_prompt = (
            f"Canvas: {document.canvas.width:g}x{document.canvas.height:g}, "
            f"grid {document.canvas.grid_size:g}.\n"
            f"User request: {request.prompt}\n"
            f"Additional user context: {user_context or '(none)'}\n"
            f"Visual evidence JSON: {json.dumps(evidence, ensure_ascii=False, separators=(',', ':'))}"
        )
        if repair_context is not None:
            user_prompt += (
                "\nPrevious compile failure to avoid: "
                + json.dumps(repair_context, ensure_ascii=False, separators=(",", ":"))
            )

        started = perf_counter()
        last_error = ""
        if self.diagnostics is not None:
            self.diagnostics.emit(
                "llm.vision_compact_plan.started",
                document_id=document_id,
                model=provider.model,
                base_url=provider.base_url,
                evidence_chars=len(json.dumps(evidence, ensure_ascii=False)),
            )

        for attempt, max_tokens in enumerate((16_384, 24_576), start=1):
            attempt_prompt = user_prompt
            if last_error:
                attempt_prompt += (
                    "\nThe previous compact graph was invalid. Return a complete replacement and fix: "
                    + last_error[:2000]
                )
            try:
                raw_graph = self._request_model_json_once(
                    compact_provider,
                    system_prompt=system_prompt,
                    user_prompt=attempt_prompt,
                    temperature=0.0,
                    images=(),
                    max_completion_tokens=max_tokens,
                )
                graph = _CompactVisualGraph.model_validate(
                    raw_graph.get("graph", raw_graph)
                )
                graph = self._expand_compact_cabinet_branches(
                    graph,
                    evidence,
                    document.canvas.width,
                    document.canvas.height,
                )
                self._validate_compact_visual_graph(graph, evidence)
            except (LLMPlanValidationError, LLMResponseError, ValidationError, ValueError) as exc:
                last_error = self._compact_graph_error(exc)
                if self.diagnostics is not None:
                    self.diagnostics.emit(
                        "llm.vision_compact_plan.retry",
                        document_id=document_id,
                        model=provider.model,
                        base_url=provider.base_url,
                        attempt=attempt,
                        error=last_error,
                    )
                if attempt < 2:
                    continue
                raise LLMPlanValidationError(
                    "K3 returned an invalid compact P&ID graph after repair: " + last_error,
                    provider=provider,
                ) from exc

            plan = self._compact_visual_graph_to_plan(
                graph,
                document.revision,
                document.canvas.width,
                document.canvas.height,
            )
            FullDiagramTransaction.model_validate(
                plan.transaction.model_dump(mode="python")
            )
            if self.diagnostics is not None:
                self.diagnostics.emit(
                    "llm.vision_compact_plan.completed",
                    document_id=document_id,
                    model=provider.model,
                    base_url=provider.base_url,
                    duration_ms=round((perf_counter() - started) * 1000, 2),
                    attempt=attempt,
                    node_count=len(graph.nodes),
                    junction_count=len(graph.junctions),
                    group_count=len(graph.groups),
                    connection_count=len(graph.connections),
                    text_count=len(graph.texts),
                )
            return plan

        raise AssertionError("unreachable compact visual planning state")

    def _compact_visual_system_prompt(self) -> str:
        catalog: list[dict[str, Any]] = []
        for symbol in self.symbols.list():
            catalog.append(
                {
                    "key": symbol.key,
                    "name": symbol.name,
                    "category": symbol.category,
                    "size": [symbol.width, symbol.height],
                    "ports": [
                        {
                            "id": port.id,
                            "flow": port.direction,
                            "offset": [port.x, port.y],
                        }
                        for port in symbol.ports
                    ],
                }
            )
        return (
            "Convert extracted P&ID evidence into one faithful compact drawing graph. Return JSON only. "
            "Use exactly these top-level keys: explanation, nodes, junctions, groups, connections, texts. "
            "nodes use {id,symbol_key,label,x,y,rotation}; junctions use {id,x,y,label}; groups use "
            "{id,label,x,y,width,height,border} where border is solid or dashed; connections use "
            "{id,source_id,source_port,target_id,target_port,flow,tag,medium,color,stroke_width}; texts use "
            "{id,text,x,y,font_size}. A connection endpoint may reference a symbol node or a junction; a "
            "junction always uses port 'node'. Groups are non-connectable dashed/solid cabinet or skid boxes; "
            "place junctions inside them for pipe takeoffs. Preserve the reference's actual system architecture, "
            "repeated modules, cabinet count, labels, colors and relative zones. Do not reinterpret a cabinet "
            "distribution diagram as a different process train. Every visible equipment, valve, instrument and "
            "off-page arrow uses an exact catalog symbol_key. Use groups for supply cabinets and purification "
            "skids that have no exact symbol. Use texts for every visible Chinese label, DN size and "
            "cabinet name. Preserve 供气柜1 through 供气柜8 as eight separate dashed groups. Preserve the blue "
            "upper DN50 header and the orange lower DN100 header with four DN80 risers. Use color '#0877bd' and "
            "stroke_width 5 for blue highlighted mains; color '#e66b00' and stroke_width 5 for orange mains; "
            "use black and 1.5 for ordinary thin branches. source_id is upstream and target_id downstream. "
            "Use off_page_connector_in/out for labeled chevron boundaries, pipe_tee or junctions for branches, "
            "and real catalog port IDs. Node x/y is top-left. Align repeated cabinet columns and their branch "
            "rows. The harness expands cabinet_branches deterministically after your response: for each numbered "
            "supply cabinet, return one narrow dashed group and exactly one inlet junction inside it, but OMIT "
            "that cabinet's repeated outlet nodes, internal outlet branches, and outlet-label texts. Do not copy "
            "cabinet_branches into explanation or merge destinations with '/', '、', or '|'. Preserve each "
            "major_paths item as a continuous connected path and connect every numbered cabinet inlet to its "
            "correct blue/orange header or riser. Non-numbered cabinets and skids that contain visible internal "
            "lines must not be returned as empty boxes. Use rotations "
            "only in multiples of 90. Do not output transaction/schema fields, raw line "
            "shapes, waypoints, nulls, or keys outside the contract. Keep IDs short and globally unique.\n"
            "CATALOG="
            + json.dumps(catalog, ensure_ascii=False, separators=(",", ":"))
        )

    def _validate_compact_visual_graph(
        self,
        graph: _CompactVisualGraph,
        evidence: dict[str, Any],
    ) -> None:
        symbol_keys = {symbol.key for symbol in self.symbols.list()}
        unknown_symbols = sorted(
            {node.symbol_key for node in graph.nodes if node.symbol_key not in symbol_keys}
        )
        if unknown_symbols:
            raise ValueError(f"unknown symbol_key values: {unknown_symbols}")
        node_ids = {node.id for node in graph.nodes}
        junction_ids = {junction.id for junction in graph.junctions}
        connectable_ids = node_ids | junction_ids
        broken_connections = [
            connection.id
            for connection in graph.connections
            if connection.source_id not in connectable_ids
            or connection.target_id not in connectable_ids
            or connection.source_id == connection.target_id
        ]
        if broken_connections:
            raise ValueError(
                f"connections reference missing or identical endpoints: {broken_connections}"
            )
        observed_connections = evidence.get("connections")
        if isinstance(observed_connections, list) and observed_connections and not graph.connections:
            raise ValueError("visual evidence contains connections but compact graph contains none")

        fidelity_issues: list[str] = []
        observed_equipment = evidence.get("equipment")
        if isinstance(observed_equipment, list) and observed_equipment:
            minimum_elements = max(1, round(len(observed_equipment) * 0.7))
            represented = len(graph.nodes) + len(graph.groups)
            if represented < minimum_elements:
                fidelity_issues.append(
                    f"only {represented}/{len(observed_equipment)} observed equipment/groups represented"
                )
        if isinstance(observed_connections, list) and observed_connections:
            minimum_connections = max(1, round(len(observed_connections) * 0.75))
            if len(graph.connections) < minimum_connections:
                fidelity_issues.append(
                    f"only {len(graph.connections)}/{len(observed_connections)} observed topology links represented"
                )

        def normalized(value: Any) -> str:
            return "".join(str(value).casefold().split())

        graph_labels = [
            *(node.label for node in graph.nodes if node.label.strip()),
            *(junction.label for junction in graph.junctions if junction.label.strip()),
            *(group.label for group in graph.groups if group.label.strip()),
            *(text.text for text in graph.texts if text.text.strip()),
            *(connection.tag for connection in graph.connections if connection.tag.strip()),
            *(connection.medium for connection in graph.connections if connection.medium.strip()),
        ]
        normalized_graph_labels = [normalized(value) for value in graph_labels]

        observed_labels = evidence.get("labels")
        if isinstance(observed_labels, list) and observed_labels:
            unique_observed = sorted(
                {normalized(value) for value in observed_labels if normalized(value)}
            )
            covered = [
                label
                for label in unique_observed
                if any(label in candidate or candidate in label for candidate in normalized_graph_labels)
            ]
            coverage = len(covered) / max(1, len(unique_observed))
            if coverage < 0.85:
                fidelity_issues.append(
                    f"critical label coverage is {coverage:.0%}; required at least 85%"
                )
            individually_covered = [
                label
                for label in unique_observed
                if any(
                    (label in candidate or candidate in label)
                    and max(len(label), len(candidate))
                    <= max(4, round(min(len(label), len(candidate)) * 1.6))
                    for candidate in normalized_graph_labels
                )
            ]
            individual_coverage = len(individually_covered) / max(1, len(unique_observed))
            if individual_coverage < 0.75:
                fidelity_issues.append(
                    "individual label coverage is "
                    f"{individual_coverage:.0%}; required at least 75% (merged labels do not count)"
                )
            merged_labels = [
                candidate
                for candidate in normalized_graph_labels
                if any(separator in candidate for separator in ("/", "／", "|", "、"))
                and sum(label in candidate for label in unique_observed) >= 2
            ]
            if merged_labels:
                fidelity_issues.append(
                    f"{len(merged_labels)} graph labels merge distinct visible destinations"
                )

        cabinet_labels = {
            normalized(f"供气柜 {index}")
            for index in range(1, 9)
        }
        evidence_mentions_eight_cabinets = all(
            any(label in normalized(str(item)) for item in (observed_equipment or []))
            for label in cabinet_labels
        )
        if evidence_mentions_eight_cabinets:
            missing_cabinets = sorted(
                label
                for label in cabinet_labels
                if not any(label in candidate for candidate in normalized_graph_labels)
            )
            if missing_cabinets:
                fidelity_issues.append(
                    "missing required cabinet labels: " + ", ".join(missing_cabinets)
                )
            if len(graph.groups) < 8:
                fidelity_issues.append(
                    f"only {len(graph.groups)} cabinet/skid groups; expected at least 8"
                )

        cabinet_branches = self._evidence_cabinet_branches(evidence)
        if cabinet_branches:
            off_page_outputs = [
                node
                for node in graph.nodes
                if node.symbol_key == "off_page_connector_out" and node.label.strip()
            ]
            for cabinet, branches in cabinet_branches.items():
                expected_counts = Counter(normalized(branch) for branch in branches)
                represented_counts = Counter(
                    {
                        branch: sum(
                            self._labels_match_individually(branch, node.label)
                            for node in off_page_outputs
                        )
                        for branch in expected_counts
                    }
                )
                missing_branches = [
                    branch
                    for branch, expected_count in expected_counts.items()
                    for _ in range(max(0, expected_count - represented_counts[branch]))
                ]
                if missing_branches:
                    fidelity_issues.append(
                        f"{cabinet} missing individual outlet nodes: "
                        + ", ".join(missing_branches[:8])
                    )

        evidence_text = normalized(json.dumps(evidence, ensure_ascii=False))
        graph_colors = {normalized(connection.color) for connection in graph.connections}
        if "blue" in evidence_text and not any(
            value in {"blue", "#0877bd", "#0070c0", "#0077c8"}
            for value in graph_colors
        ):
            fidelity_issues.append("missing blue highlighted process header")
        if "orange" in evidence_text and not any(
            value in {"orange", "#e66b00", "#ed6c02", "#e86f00"}
            for value in graph_colors
        ):
            fidelity_issues.append("missing orange highlighted argon header")

        if fidelity_issues:
            raise ValueError("reference fidelity failed: " + "; ".join(fidelity_issues))

    @staticmethod
    def _labels_match_individually(expected: Any, candidate: Any) -> bool:
        def normalize(value: Any) -> str:
            return "".join(str(value).casefold().split())

        expected_label = normalize(expected)
        candidate_label = normalize(candidate)
        if not expected_label or not candidate_label:
            return False
        if not (expected_label in candidate_label or candidate_label in expected_label):
            return False
        return max(len(expected_label), len(candidate_label)) <= max(
            4,
            round(min(len(expected_label), len(candidate_label)) * 1.35),
        )

    @staticmethod
    def _evidence_cabinet_branches(evidence: dict[str, Any]) -> dict[str, list[str]]:
        raw = evidence.get("cabinet_branches")
        result: dict[str, list[str]] = {}
        if isinstance(raw, dict):
            items = raw.items()
        elif isinstance(raw, list):
            items = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                cabinet = next(
                    (
                        item.get(key)
                        for key in ("cabinet", "name", "label", "id")
                        if item.get(key)
                    ),
                    None,
                )
                branches = next(
                    (
                        item.get(key)
                        for key in ("branches", "outlets", "users", "destinations")
                        if isinstance(item.get(key), list)
                    ),
                    None,
                )
                if cabinet is not None and branches is not None:
                    items.append((cabinet, branches))
        else:
            return result
        for cabinet, branches in items:
            if not isinstance(branches, list):
                continue
            labels = [str(branch).strip() for branch in branches if str(branch).strip()]
            if labels:
                result[str(cabinet).strip()] = labels
        return result

    def _expand_compact_cabinet_branches(
        self,
        graph: _CompactVisualGraph,
        evidence: dict[str, Any],
        canvas_width: float,
        canvas_height: float,
    ) -> _CompactVisualGraph:
        cabinet_branches = self._evidence_cabinet_branches(evidence)
        if not cabinet_branches:
            return graph

        def normalized(value: Any) -> str:
            return "".join(str(value).casefold().split())

        used_ids = {
            *(node.id for node in graph.nodes),
            *(junction.id for junction in graph.junctions),
            *(group.id for group in graph.groups),
            *(text.id for text in graph.texts),
            *(connection.id for connection in graph.connections),
        }

        def generated_id(base: str) -> str:
            candidate = base
            suffix = 2
            while candidate in used_ids:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used_ids.add(candidate)
            return candidate

        nodes = list(graph.nodes)
        junctions = list(graph.junctions)
        groups = list(graph.groups)
        connections = list(graph.connections)
        for cabinet, branches in cabinet_branches.items():
            cabinet_label = normalized(cabinet)
            group_index = next(
                (
                    index
                    for index, group in enumerate(groups)
                    if normalized(group.label) == cabinet_label
                ),
                None,
            )
            if group_index is None:
                continue
            group = groups[group_index]
            minimum_height = 50.0 + max(1, len(branches)) * 42.0
            group_width = min(group.width, 80.0)
            group_height = max(group.height, minimum_height)
            available_below = canvas_height - group.y - 20.0
            update: dict[str, Any] = {"width": group_width, "height": group_height}
            if group_height > available_below:
                # 底部空间不足：整体上移组（组内 junction 均以 group.y 为基准，
                # 会跟随），而不是压缩高度导致密集分支相互重叠。
                update["y"] = max(10.0, canvas_height - 20.0 - group_height)
            group = group.model_copy(update=update, deep=True)
            groups[group_index] = group

            existing_outputs = [
                node
                for node in nodes
                if node.symbol_key == "off_page_connector_out"
                and any(
                    self._labels_match_individually(branch, node.label)
                    for branch in branches
                )
            ]
            if len(existing_outputs) >= len(branches):
                continue

            inside_junctions = [
                junction
                for junction in junctions
                if group.x <= junction.x <= group.x + group.width
                and group.y <= junction.y <= group.y + group.height
            ]
            if inside_junctions:
                inlet = min(
                    inside_junctions,
                    key=lambda item: (item.y, item.x),
                )
            else:
                inlet = _CompactVisualJunction(
                    id=generated_id(f"{group.id}_in"),
                    x=group.x + group.width * 0.35,
                    y=group.y + 24.0,
                    label="in",
                )
                junctions.append(inlet)

            branch_x = group.x + group.width - 20.0
            top_y = group.y + 42.0
            bottom_y = group.y + group.height - 34.0
            if len(branches) == 1:
                branch_y_values = [(top_y + bottom_y) / 2]
            else:
                step = (bottom_y - top_y) / (len(branches) - 1)
                branch_y_values = [top_y + index * step for index in range(len(branches))]

            previous_spine_id = inlet.id
            for branch_index, (branch, branch_y) in enumerate(
                zip(branches, branch_y_values, strict=True),
                start=1,
            ):
                matching_output = next(
                    (
                        node
                        for node in existing_outputs
                        if self._labels_match_individually(branch, node.label)
                    ),
                    None,
                )
                if matching_output is not None:
                    continue
                spine = _CompactVisualJunction(
                    id=generated_id(f"{group.id}_b{branch_index}"),
                    x=branch_x,
                    y=branch_y,
                    label="DN50",
                )
                junctions.append(spine)
                if previous_spine_id != spine.id:
                    connections.append(
                        _CompactVisualConnection(
                            id=generated_id(f"{group.id}_sp{branch_index}"),
                            source_id=previous_spine_id,
                            source_port="node",
                            target_id=spine.id,
                            target_port="node",
                            flow="none",
                            color="black",
                            stroke_width=1.5,
                        )
                    )
                valve = _CompactVisualNode(
                    id=generated_id(f"{group.id}_branch_valve{branch_index}"),
                    symbol_key="gate_valve",
                    label="",
                    x=group.x + 90.0,
                    y=max(10.0, branch_y - 10.0),
                    rotation=0,
                )
                tap = _CompactVisualJunction(
                    id=generated_id(f"{group.id}_tap{branch_index}"),
                    x=group.x + 150.0,
                    y=branch_y,
                    label="",
                )
                pressure = _CompactVisualNode(
                    id=generated_id(f"{group.id}_branch_pt{branch_index}"),
                    symbol_key="pressure_transmitter",
                    label="",
                    x=group.x + 140.0,
                    y=max(10.0, branch_y - 40.0),
                    rotation=0,
                )
                nodes.extend([valve, pressure])
                junctions.append(tap)
                connections.extend(
                    [
                        _CompactVisualConnection(
                            id=generated_id(f"{group.id}_valvec{branch_index}"),
                            source_id=spine.id,
                            source_port="node",
                            target_id=valve.id,
                            target_port="in",
                            flow="none",
                            color="black",
                            stroke_width=1.5,
                        ),
                        _CompactVisualConnection(
                            id=generated_id(f"{group.id}_tapc{branch_index}"),
                            source_id=valve.id,
                            source_port="out",
                            target_id=tap.id,
                            target_port="node",
                            flow="none",
                            color="black",
                            stroke_width=1.5,
                        ),
                        _CompactVisualConnection(
                            id=generated_id(f"{group.id}_ptc{branch_index}"),
                            source_id=tap.id,
                            source_port="node",
                            target_id=pressure.id,
                            target_port="process",
                            flow="none",
                            color="black",
                            stroke_width=1.2,
                        ),
                    ]
                )
                output_x = min(
                    canvas_width - 100.0,
                    max(group.x + group.width + 110.0, group.x + 200.0),
                )
                output = _CompactVisualNode(
                    id=generated_id(f"{group.id}_out{branch_index}"),
                    symbol_key="off_page_connector_out",
                    label=branch,
                    x=output_x,
                    y=max(20.0, branch_y - 20.0),
                    rotation=0,
                )
                nodes.append(output)
                connections.append(
                    _CompactVisualConnection(
                        id=generated_id(f"{group.id}_outc{branch_index}"),
                        source_id=tap.id,
                        source_port="node",
                        target_id=output.id,
                        target_port="process",
                        flow="none",
                        color="black",
                        stroke_width=1.5,
                    )
                )
                previous_spine_id = spine.id

        return graph.model_copy(
            update={
                "nodes": nodes,
                "junctions": junctions,
                "groups": groups,
                "connections": connections,
            },
            deep=True,
        )

    @staticmethod
    def _compact_graph_error(exc: Exception) -> str:
        if isinstance(exc, ValidationError):
            errors = exc.errors(
                include_url=False,
                include_context=False,
                include_input=False,
            )[:12]
            return "; ".join(
                f"{'.'.join(str(part) for part in item['loc'])}: {item['msg']}"
                for item in errors
            )
        return str(exc)

    def _compact_visual_graph_to_plan(
        self,
        graph: _CompactVisualGraph,
        revision: int,
        canvas_width: float,
        canvas_height: float,
    ) -> SemanticAgentPlan:
        graph = self._normalize_compact_visual_geometry(graph, canvas_width)
        operations: list[Any] = []
        used_ids = {
            *(node.id for node in graph.nodes),
            *(junction.id for junction in graph.junctions),
            *(group.id for group in graph.groups),
            *(text.id for text in graph.texts),
            *(connection.id for connection in graph.connections),
        }

        def generated_id(base: str) -> str:
            candidate = base
            suffix = 2
            while candidate in used_ids:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used_ids.add(candidate)
            return candidate

        explicit_text_labels = {
            "".join(text_item.text.casefold().split())
            for text_item in graph.texts
        }
        for group in graph.groups:
            x = self._snap_and_clamp(group.x, 10, max(10, canvas_width - 40))
            y = self._snap_and_clamp(group.y, 30, max(30, canvas_height - 40))
            width = min(group.width, max(40, canvas_width - x - 10))
            height = min(group.height, max(40, canvas_height - y - 10))
            operations.append(
                AddElementOperation(
                    element=RectangleElement(
                        id=group.id,
                        x=x,
                        y=y,
                        width=width,
                        height=height,
                        style=Style(
                            stroke="#111827",
                            fill="none",
                            stroke_width=1.2,
                            dash=[8, 5] if group.border == "dashed" else [],
                        ),
                        name=group.label,
                        metadata={"reference_group": True, "group_label": group.label},
                    )
                )
            )
            if "".join(group.label.casefold().split()) not in explicit_text_labels:
                operations.append(
                    AddElementOperation(
                        element=TextElement(
                            id=generated_id(f"{group.id}__label"),
                            position=Point(x=x + 8, y=y + height - 8),
                            text=group.label,
                            font_size=12,
                            metadata={"reference_group_id": group.id},
                        )
                    )
                )

        node_symbols = {node.id: self.symbols.get(node.symbol_key) for node in graph.nodes}
        node_sizes = {
            node.id: self._compact_node_size(node, node_symbols[node.id])
            for node in graph.nodes
        }
        positions = self._place_compact_nodes(
            graph.nodes,
            node_symbols,
            node_sizes,
            canvas_width,
            canvas_height,
        )
        for node in graph.nodes:
            if (
                node_symbols[node.id].category == "仪表"
                and "_branch_pt" not in node.id
            ):
                width, height = node_sizes[node.id]
                positions[node.id] = (
                    min(max(0.0, node.x), max(0.0, canvas_width - width)),
                    min(max(0.0, node.y), max(0.0, canvas_height - height)),
                )
        node_elements: dict[str, SymbolElement | JunctionElement] = {}

        for node in graph.nodes:
            symbol = node_symbols[node.id]
            x, y = positions[node.id]
            width, height = node_sizes[node.id]
            rotation = (round(node.rotation / 90) * 90) % 360
            embedded_off_page_label = (
                node.label
                if node.label.strip()
                and node.symbol_key in {"off_page_connector_in", "off_page_connector_out"}
                else ""
            )
            element = SymbolElement(
                id=node.id,
                symbol_key=symbol.key,
                position=Point(x=x, y=y),
                width=width,
                height=height,
                rotation=rotation,
                label="" if embedded_off_page_label else node.label,
                metadata=(
                    {"embedded_off_page_label": embedded_off_page_label}
                    if embedded_off_page_label
                    else {}
                ),
            )
            node_elements[node.id] = element
            operations.append(AddElementOperation(element=element))

        junction_positions = {
            junction.id: Point(
                x=self._snap_and_clamp(junction.x, 10, max(10, canvas_width - 10)),
                y=self._snap_and_clamp(junction.y, 20, max(20, canvas_height - 10)),
            )
            for junction in graph.junctions
        }
        graph_positions: dict[str, Point] = {
            node_id: Point(
                x=element.position.x + element.width / 2,
                y=element.position.y + element.height / 2,
            )
            for node_id, element in node_elements.items()
            if element.type == "symbol"
        }
        graph_positions.update(junction_positions)
        for junction_id, point in list(junction_positions.items()):
            for symbol_element in (
                element
                for element in node_elements.values()
                if element.type == "symbol"
            ):
                if not (
                    symbol_element.position.x - 3 <= point.x <= symbol_element.position.x + symbol_element.width + 3
                    and symbol_element.position.y - 3 <= point.y <= symbol_element.position.y + symbol_element.height + 3
                ):
                    continue
                neighbours: list[Point] = []
                for connection in graph.connections:
                    other_id = None
                    if connection.source_id == junction_id:
                        other_id = connection.target_id
                    elif connection.target_id == junction_id:
                        other_id = connection.source_id
                    if other_id is not None and other_id in graph_positions:
                        neighbours.append(graph_positions[other_id])
                dx = sum(neighbour.x - point.x for neighbour in neighbours)
                dy = sum(neighbour.y - point.y for neighbour in neighbours)
                clearance = 20.0
                if abs(dx) >= abs(dy):
                    moved = Point(
                        x=(
                            symbol_element.position.x + symbol_element.width + clearance
                            if dx >= 0
                            else symbol_element.position.x - clearance
                        ),
                        y=point.y,
                    )
                else:
                    moved = Point(
                        x=point.x,
                        y=(
                            symbol_element.position.y + symbol_element.height + clearance
                            if dy >= 0
                            else symbol_element.position.y - clearance
                        ),
                    )
                junction_positions[junction_id] = Point(
                    x=self._snap_and_clamp(moved.x, 10, max(10, canvas_width - 10)),
                    y=self._snap_and_clamp(moved.y, 20, max(20, canvas_height - 10)),
                )
                graph_positions[junction_id] = junction_positions[junction_id]

        for junction in graph.junctions:
            element = JunctionElement(
                id=junction.id,
                position=junction_positions[junction.id],
                radius=3,
                label=junction.label,
                metadata={"reference_junction": True},
            )
            node_elements[junction.id] = element
            operations.append(AddElementOperation(element=element))

        for text_item in graph.texts:
            operations.append(
                AddElementOperation(
                    element=TextElement(
                        id=text_item.id,
                        position=Point(
                            x=self._snap_and_clamp(
                                text_item.x,
                                10,
                                max(10, canvas_width - 10),
                            ),
                            y=self._snap_and_clamp(
                                text_item.y,
                                20,
                                max(20, canvas_height - 10),
                            ),
                        ),
                        text=text_item.text,
                        font_size=text_item.font_size,
                        metadata={"reference_label": True},
                    )
                )
            )

        for connection in graph.connections:
            flow = connection.flow if connection.flow in {"forward", "reverse", "none"} else "forward"
            instrument_branch = any(
                node_symbols[element_id].category == "仪表"
                for element_id in (connection.source_id, connection.target_id)
                if element_id in node_symbols
            )
            if instrument_branch:
                flow = "none"
            suppress_flow_arrow = any(
                marker in connection.id
                for marker in ("_valvec", "_tapc", "_ptc", "_outc")
            )
            reference_branch_unit = connection.id.startswith("g_c") and any(
                marker in connection.id
                for marker in ("_sp", "_valvec", "_tapc", "_ptc", "_outc")
            )
            if suppress_flow_arrow:
                flow = "none"
            source_port = (
                self._resolve_compact_port(
                    node_symbols[connection.source_id],
                    connection.source_port,
                    prefer="in" if flow == "reverse" else "out",
                )
                if connection.source_id in node_symbols
                else "node"
            )
            target_port = (
                self._resolve_compact_port(
                    node_symbols[connection.target_id],
                    connection.target_port,
                    prefer="out" if flow == "reverse" else "in",
                )
                if connection.target_id in node_symbols
                else "node"
            )
            if (
                not instrument_branch
                and connection.source_id in node_symbols
                and connection.target_id in node_symbols
            ):
                source_element = node_elements[connection.source_id]
                target_element = node_elements[connection.target_id]
                source_center = (
                    source_element.position.x + source_element.width / 2,
                    source_element.position.y + source_element.height / 2,
                )
                target_center = (
                    target_element.position.x + target_element.width / 2,
                    target_element.position.y + target_element.height / 2,
                )
                dx = target_center[0] - source_center[0]
                dy = target_center[1] - source_center[1]
                if abs(dx) >= abs(dy) * 1.5 and abs(dx) >= 40:
                    direction_x = 1 if dx > 0 else -1
                    source_port = self._spatially_compatible_port(
                        source_element,
                        node_symbols[connection.source_id],
                        source_port,
                        prefer="in" if flow == "reverse" else "out",
                        desired_normal=(direction_x, 0),
                    )
                    target_port = self._spatially_compatible_port(
                        target_element,
                        node_symbols[connection.target_id],
                        target_port,
                        prefer="out" if flow == "reverse" else "in",
                        desired_normal=(-direction_x, 0),
                    )
            operations.append(
                ConnectPortsOperation(
                    connector_id=connection.id,
                    source_element_id=connection.source_id,
                    source_port_id=source_port,
                    target_element_id=connection.target_id,
                    target_port_id=target_port,
                    routing="orthogonal",
                    process_tag=connection.tag,
                    medium=connection.medium,
                    flow_direction=flow,
                    arrow_position="middle",
                    crossing_style="jump",
                    style={
                        "stroke": self._compact_connection_color(connection.color),
                        "fill": "none",
                        "stroke_width": connection.stroke_width,
                    },
                    metadata=(
                        {
                            "connection_role": "instrument_branch",
                            "reference_color": connection.color,
                            "reference_reconstruction": True,
                            "reference_branch_unit": reference_branch_unit,
                            "suppress_flow_arrow": suppress_flow_arrow,
                        }
                        if instrument_branch
                        else {
                            "reference_color": connection.color,
                            "reference_reconstruction": True,
                            "reference_branch_unit": reference_branch_unit,
                            "suppress_flow_arrow": suppress_flow_arrow,
                        }
                    ),
                )
            )

        return SemanticAgentPlan(
            explanation=graph.explanation or "Reconstructed from the supplied P&ID reference image.",
            transaction=SemanticTransaction(
                operations=operations,
                expected_revision=revision,
                label="Reconstruct P&ID from reference image",
            ),
        )

    def _normalize_compact_visual_geometry(
        self,
        graph: _CompactVisualGraph,
        canvas_width: float,
    ) -> _CompactVisualGraph:
        """Straighten the dense condenser/off-gas header before symbol placement."""
        nodes = {node.id: node for node in graph.nodes}
        junctions = {junction.id: junction for junction in graph.junctions}
        connections = {connection.id: connection for connection in graph.connections}
        groups = {group.id: group for group in graph.groups}
        texts = {text.id: text for text in graph.texts}

        # Compact skeletons occasionally preserve purifier labels but omit the
        # visible module boxes. Restore those boxes deterministically so the
        # purification skids are not rendered as misleading empty cabinets.
        purifier_groups = [
            group
            for group in graph.groups
            if "纯化柜" in "".join(group.label.split())
        ]
        for purifier_group in purifier_groups:
            purifier_texts = sorted(
                (
                    text
                    for text in graph.texts
                    if "纯化器" in "".join(text.text.split())
                    and purifier_group.x <= text.x <= purifier_group.x + purifier_group.width
                    and purifier_group.y <= text.y <= purifier_group.y + purifier_group.height
                ),
                key=lambda item: item.y,
            )
            if not purifier_texts:
                continue
            is_top_skid = purifier_group.y < 400.0
            unit_x = purifier_group.x + 20.0
            unit_width = min(
                105.0 if is_top_skid else 70.0,
                max(50.0, purifier_group.width - (40.0 if is_top_skid else 90.0)),
            )
            first_y = purifier_group.y + (45.0 if is_top_skid else 15.0)
            for index, text_item in enumerate(purifier_texts, start=1):
                unit_y = first_y + (index - 1) * 40.0
                unit_id = f"{purifier_group.id}_unit{index}"
                if unit_id not in groups:
                    groups[unit_id] = _CompactVisualGroup(
                        id=unit_id,
                        label=text_item.text,
                        x=unit_x,
                        y=unit_y,
                        width=unit_width,
                        height=30.0,
                        border="solid",
                    )
                texts[text_item.id] = text_item.model_copy(
                    update={
                        "x": unit_x + 10.0,
                        "y": unit_y + 20.0,
                        "font_size": 10.0,
                    },
                    deep=True,
                )

        exact_instrument_keys = {
            ("pressure_indicator", "pt"): "pressure_transmitter",
            ("temperature_indicator", "te"): "temperature_element",
            ("flow_indicator", "ai"): "analyzer_indicator",
        }
        for node_id, node in list(nodes.items()):
            label = "".join(node.label.casefold().split())
            replacement = exact_instrument_keys.get((node.symbol_key, label))
            if replacement is not None:
                nodes[node_id] = node.model_copy(
                    update={"symbol_key": replacement},
                    deep=True,
                )

        orange_connections = [
            connection
            for connection in graph.connections
            if self._compact_connection_color(connection.color) == "#e66b00"
        ]
        orange_junction_ids = {
            endpoint_id
            for connection in orange_connections
            for endpoint_id in (connection.source_id, connection.target_id)
            if endpoint_id in junctions
        }
        orange_header_ids = [
            junction_id
            for junction_id in orange_junction_ids
            if "".join(junctions[junction_id].label.casefold().split()).startswith("dn")
        ]
        numbered_cabinet_groups: list[tuple[int, _CompactVisualGroup]] = []
        for group in graph.groups:
            normalized_label = "".join(group.label.casefold().split())
            digits = "".join(character for character in normalized_label if character.isdigit())
            if "供气柜" in normalized_label and digits:
                numbered_cabinet_groups.append((int(digits), group))
        odd_bottoms = [
            group.y + group.height
            for number, group in numbered_cabinet_groups
            if number % 2 == 1
        ]
        even_tops = [
            group.y
            for number, group in numbered_cabinet_groups
            if number % 2 == 0
        ]
        if orange_header_ids and odd_bottoms and even_tops:
            orange_header_y = round(
                ((max(odd_bottoms) + min(even_tops)) / 2.0) / 10.0
            ) * 10.0
            for junction_id in orange_header_ids:
                junctions[junction_id] = junctions[junction_id].model_copy(
                    update={"y": orange_header_y},
                    deep=True,
                )

            purifier_valve_x: float | None = None
            source_pair = next(
                (
                    (nodes[connection.source_id], nodes[connection.target_id])
                    for connection in orange_connections
                    if connection.source_id in nodes
                    and connection.target_id in nodes
                    and nodes[connection.source_id].symbol_key == "off_page_connector_in"
                ),
                None,
            )
            if source_pair is not None:
                source_node, source_valve = source_pair
                source_valve_x = source_node.x + 150.0
                purifier_valve_x = source_node.x + 90.0
                nodes[source_node.id] = source_node.model_copy(
                    update={"y": orange_header_y - 20.0},
                    deep=True,
                )
                nodes[source_valve.id] = source_valve.model_copy(
                    update={
                        "x": source_valve_x,
                        "y": orange_header_y - 20.0,
                    },
                    deep=True,
                )
                first_header_id = min(
                    orange_header_ids,
                    key=lambda item: junctions[item].x,
                )
                source_valve_width = self.symbols.get(source_valve.symbol_key).width
                junctions[first_header_id] = junctions[first_header_id].model_copy(
                    update={"x": source_valve_x + source_valve_width + 20.0},
                    deep=True,
                )

            for node_id, valve in list(nodes.items()):
                if valve.symbol_key != "ball_valve" or valve.rotation % 180 == 0:
                    continue
                outgoing_header = next(
                    (
                        connection
                        for connection in orange_connections
                        if connection.source_id == node_id
                        and connection.target_id in orange_header_ids
                    ),
                    None,
                )
                if outgoing_header is None:
                    continue
                nodes[node_id] = valve.model_copy(
                    update={
                        "x": purifier_valve_x if purifier_valve_x is not None else valve.x,
                        "y": orange_header_y + 10.0,
                        "rotation": 270.0,
                    },
                    deep=True,
                )
                upstream_junction_id = next(
                    (
                        connection.source_id
                        for connection in graph.connections
                        if connection.target_id == node_id
                        and connection.source_id in junctions
                    ),
                    None,
                )
                if upstream_junction_id is not None:
                    junctions[upstream_junction_id] = junctions[
                        upstream_junction_id
                    ].model_copy(
                        update={
                            "x": (
                                purifier_valve_x + 30.0
                                if purifier_valve_x is not None
                                else valve.x + 30.0
                            ),
                            "y": orange_header_y + 80.0,
                        },
                        deep=True,
                    )

        def junction_predecessors(junction_id: str) -> list[str]:
            return [
                connection.source_id
                for connection in graph.connections
                if connection.target_id == junction_id
                and connection.source_id in junctions
                and self._compact_connection_color(connection.color) == "#111827"
            ]

        def junction_successors(junction_id: str) -> list[str]:
            return [
                connection.target_id
                for connection in graph.connections
                if connection.source_id == junction_id
                and connection.target_id in junctions
                and self._compact_connection_color(connection.color) == "#111827"
            ]

        for condenser in (
            node for node in graph.nodes if node.symbol_key == "condenser"
        ):
            upstream_id = next(
                (
                    connection.source_id
                    for connection in graph.connections
                    if connection.target_id == condenser.id
                    and connection.source_id in junctions
                    and "process" in connection.target_port.casefold()
                ),
                None,
            )
            downstream_id = next(
                (
                    connection.target_id
                    for connection in graph.connections
                    if connection.source_id == condenser.id
                    and connection.target_id in junctions
                    and "process" in connection.source_port.casefold()
                ),
                None,
            )
            if upstream_id is None or downstream_id is None:
                continue

            upstream_chain = [upstream_id]
            while len(upstream_chain) < 6:
                candidates = [
                    item
                    for item in junction_predecessors(upstream_chain[-1])
                    if item not in upstream_chain
                ]
                if not candidates:
                    break
                upstream_chain.append(candidates[0])
            upstream_chain.reverse()

            downstream_chain = [downstream_id]
            while len(downstream_chain) < 6:
                candidates = [
                    item
                    for item in junction_successors(downstream_chain[-1])
                    if item not in downstream_chain
                ]
                if not candidates:
                    break
                downstream_chain.append(candidates[0])

            header_ids = [*upstream_chain, *downstream_chain]
            header_y = max(
                80.0,
                round(median(junctions[item].y for item in header_ids) / 10) * 10,
            )
            definition = self.symbols.get(condenser.symbol_key)
            condenser_x = min(
                condenser.x,
                max(200.0, canvas_width - definition.width - 200.0),
            )
            nodes[condenser.id] = condenser.model_copy(
                update={"x": condenser_x, "y": header_y - 34.0},
                deep=True,
            )
            for index, junction_id in enumerate(upstream_chain):
                distance = (len(upstream_chain) - index) * 40.0
                junctions[junction_id] = junctions[junction_id].model_copy(
                    update={"x": condenser_x - distance, "y": header_y},
                    deep=True,
                )
            condenser_right = condenser_x + definition.width
            for index, junction_id in enumerate(downstream_chain):
                junctions[junction_id] = junctions[junction_id].model_copy(
                    update={
                        "x": condenser_right + 40.0 + index * 40.0,
                        "y": header_y,
                    },
                    deep=True,
                )

            last_downstream = downstream_chain[-1]
            last_position = junctions[last_downstream]
            output_id = next(
                (
                    connection.target_id
                    for connection in graph.connections
                    if connection.source_id == last_downstream
                    and connection.target_id in nodes
                    and nodes[connection.target_id].symbol_key == "off_page_connector_out"
                ),
                None,
            )
            if output_id is not None:
                output_x = min(canvas_width - 100.0, last_position.x + 20.0)
                if output_x <= last_position.x:
                    last_position = last_position.model_copy(
                        update={"x": output_x - 20.0},
                        deep=True,
                    )
                    junctions[last_downstream] = last_position
                nodes[output_id] = nodes[output_id].model_copy(
                    update={"x": output_x, "y": header_y - 20.0},
                    deep=True,
                )

            for junction_id in header_ids:
                position = junctions[junction_id]
                instrument_ids = [
                    other_id
                    for connection in graph.connections
                    for other_id in (
                        [connection.target_id]
                        if connection.source_id == junction_id
                        else [connection.source_id]
                        if connection.target_id == junction_id
                        else []
                    )
                    if other_id in nodes
                    and self.symbols.get(nodes[other_id].symbol_key).category == "仪表"
                ]
                for instrument_id in instrument_ids:
                    instrument = nodes[instrument_id]
                    nodes[instrument_id] = instrument.model_copy(
                        update={
                            "x": position.x - 10.0,
                            "y": header_y - 50.0,
                        },
                        deep=True,
                    )

            for connection in graph.connections:
                if (
                    connection.target_id == condenser.id
                    and "utility" in connection.target_port.casefold()
                    and connection.source_id in nodes
                    and nodes[connection.source_id].symbol_key == "off_page_connector_in"
                ):
                    nodes[connection.source_id] = nodes[connection.source_id].model_copy(
                        update={
                            "x": condenser_right + 40.0,
                            "y": header_y + 80.0,
                            "rotation": 180.0,
                        },
                        deep=True,
                    )
                if (
                    connection.source_id == condenser.id
                    and "utility" in connection.source_port.casefold()
                    and connection.target_id in nodes
                    and nodes[connection.target_id].symbol_key == "off_page_connector_out"
                ):
                    nodes[connection.target_id] = nodes[connection.target_id].model_copy(
                        update={
                            "x": condenser_x - 110.0,
                            "y": header_y + 80.0,
                            "rotation": 180.0,
                        },
                        deep=True,
                    )

        for connection in graph.connections:
            if connection.source_id not in nodes or connection.target_id not in nodes:
                continue
            source = nodes[connection.source_id]
            target = nodes[connection.target_id]
            if (
                source.symbol_key == "horizontal_vessel"
                and target.symbol_key == "pressure_transmitter"
                and connection.source_port == "top"
            ):
                source_definition = self.symbols.get(source.symbol_key)
                source_port = next(
                    port for port in source_definition.ports if port.id == "top"
                )
                if source.y <= 100.0:
                    target_position = {
                        "x": source.x + source_port.x - 10.0,
                        "y": source.y - 50.0,
                    }
                else:
                    target_position = {
                        "x": source.x + source_definition.width + 10.0,
                        "y": source.y - 10.0,
                    }
                    connections[connection.id] = connection.model_copy(
                        update={"source_port": "out"},
                        deep=True,
                    )
                nodes[target.id] = target.model_copy(
                    update=target_position,
                    deep=True,
                )

        return graph.model_copy(
            update={
                "nodes": [nodes[node.id] for node in graph.nodes],
                "junctions": [junctions[junction.id] for junction in graph.junctions],
                "connections": [
                    connections[connection.id] for connection in graph.connections
                ],
                "groups": list(groups.values()),
                "texts": [texts[text.id] for text in graph.texts],
            },
            deep=True,
        )

    def _place_compact_nodes(
        self,
        nodes: list[_CompactVisualNode],
        node_symbols: dict[str, Any],
        node_sizes: dict[str, tuple[float, float]],
        canvas_width: float,
        canvas_height: float,
    ) -> dict[str, tuple[float, float]]:
        margin = 10.0
        clearance = 0.0
        placed: list[tuple[float, float, float, float]] = []
        positions: dict[str, tuple[float, float]] = {}

        for node in nodes:
            width, height = node_sizes[node.id]
            max_x = max(margin, canvas_width - width - margin)
            max_y = max(margin, canvas_height - height - margin)
            desired_x = self._snap_and_clamp(node.x, margin, max_x)
            desired_y = self._snap_and_clamp(node.y, margin, max_y)

            candidates: list[tuple[float, float]] = [(desired_x, desired_y)]
            # 超过到任一画布边界的距离后，所有方向 clamp 都会收敛到边界点，
            # 不会产生新位置；以此为上限可避免在大画布上枚举数百圈无效候选。
            max_distance = max(
                desired_x - margin,
                max_x - desired_x,
                desired_y - margin,
                max_y - desired_y,
            )
            max_radius = int(max_distance) + 20
            for distance in range(20, max_radius + 20, 20):
                candidates.extend(
                    [
                        (desired_x, desired_y - distance),
                        (desired_x, desired_y + distance),
                        (desired_x - distance, desired_y),
                        (desired_x + distance, desired_y),
                        (desired_x - distance, desired_y - distance),
                        (desired_x + distance, desired_y - distance),
                        (desired_x - distance, desired_y + distance),
                        (desired_x + distance, desired_y + distance),
                    ]
                )

            selected = (desired_x, desired_y)
            seen: set[tuple[float, float]] = set()
            for raw_x, raw_y in candidates:
                x = self._snap_and_clamp(raw_x, margin, max_x)
                y = self._snap_and_clamp(raw_y, margin, max_y)
                if (x, y) in seen:
                    continue
                seen.add((x, y))
                candidate = (x, y, x + width, y + height)
                if any(
                    not (
                        candidate[2] + clearance <= other[0]
                        or other[2] + clearance <= candidate[0]
                        or candidate[3] + clearance <= other[1]
                        or other[3] + clearance <= candidate[1]
                    )
                    for other in placed
                ):
                    continue
                selected = (x, y)
                break

            x, y = selected
            placed.append((x, y, x + width, y + height))
            positions[node.id] = selected
        return positions

    @staticmethod
    def _compact_node_size(node: _CompactVisualNode, symbol: Any) -> tuple[float, float]:
        if "_branch_valve" in node.id:
            return 30.0, 50.0 / 3.0
        if "_branch_pt" in node.id:
            return 70.0 / 3.0, 20.0
        if node.id.startswith("g_c") and "_out" in node.id:
            return 90.0, 40.0
        if node.symbol_key in {"off_page_connector_in", "off_page_connector_out"}:
            return min(symbol.width, 90.0), min(symbol.height, 40.0)
        if node.symbol_key == "pressure_transmitter":
            return 70.0 / 3.0, 30.0
        if node.symbol_key in {"temperature_element", "analyzer_indicator"}:
            return 20.0, 30.0
        if symbol.category == "仪表":
            return min(symbol.width, 36.0), min(symbol.height, 44.0)
        return symbol.width, symbol.height

    @staticmethod
    def _snap_and_clamp(value: float, lower: float, upper: float) -> float:
        return min(upper, max(lower, round(value / 10) * 10))

    @staticmethod
    def _compact_connection_color(value: str) -> str:
        normalized = value.strip().casefold()
        if normalized in {"blue", "#0877bd", "#0070c0", "#0077c8"}:
            return "#0877bd"
        if normalized in {"orange", "#e66b00", "#ed6c02", "#e86f00"}:
            return "#e66b00"
        if normalized.startswith("#") and len(normalized) in {4, 7}:
            return normalized
        return "#111827"

    @staticmethod
    def _resolve_compact_port(symbol: Any, requested: str, *, prefer: str) -> str:
        ports = list(symbol.ports)
        if not ports:
            raise ValueError(f"symbol {symbol.key!r} has no connectable ports")
        requested_port = next((port for port in ports if port.id == requested), None)
        compatible = {prefer, "bidirectional", "none"}
        if requested_port is not None and requested_port.direction in compatible:
            return requested_port.id
        preferred = next((port for port in ports if port.direction == prefer), None)
        if preferred is not None:
            return preferred.id
        bidirectional = next(
            (port for port in ports if port.direction in {"bidirectional", "none"}),
            None,
        )
        if bidirectional is not None:
            return bidirectional.id
        if requested_port is not None:
            return requested_port.id
        return ports[0].id

    def _spatially_compatible_port(
        self,
        element: SymbolElement,
        symbol: Any,
        current_port_id: str,
        *,
        prefer: str,
        desired_normal: tuple[int, int],
    ) -> str:
        compatible = [
            port
            for port in symbol.ports
            if port.direction in {prefer, "bidirectional", "none"}
            and port_outward_normal(element, port.id, self.symbols) == desired_normal
        ]
        if not compatible:
            return current_port_id
        return next(
            (port.id for port in compatible if port.id == current_port_id),
            compatible[0].id,
        )

    def _prepare_k3_vision_request(
        self,
        request: VisionAgentGenerateRequest | VisionSemanticAgentReplanRequest,
    ) -> VisionAgentGenerateRequest | VisionSemanticAgentReplanRequest:
        if not request.images:
            return request
        provider = self.provider_transport._resolve_provider(
            request.provider,
            self.provider_transport.provider_policy,
            self.provider_transport.max_timeout_seconds,
        )
        if not is_kimi_k3_provider(provider):
            return request
        evidence = self._extract_k3_visual_evidence(
            provider,
            tuple(request.images),
            request.prompt,
        )
        evidence_context = (
            "K3 visual evidence extracted from the attached P&ID reference image(s). "
            "Treat this as observed engineering evidence, preserve its topology and relative layout, "
            "and reconstruct it using only available catalog symbols and semantic operations:\n"
            + json.dumps(evidence, ensure_ascii=False, separators=(",", ":"))
        )
        context = "\n\n".join(
            part for part in (request.context.strip(), evidence_context) if part
        )
        planning_provider = provider.model_copy(
            update={"thinking_enabled": True, "thinking_level": "low"}
        )
        return request.model_copy(
            update={
                "context": context,
                "provider": planning_provider,
                "images": [],
            }
        )

    def _extract_k3_visual_evidence(
        self,
        provider: ProviderConfig,
        images: tuple[AgentImageInput, ...],
        user_prompt: str,
    ) -> dict[str, Any]:
        evidence_provider = provider.model_copy(
            update={"thinking_enabled": True, "thinking_level": "low"}
        )
        system_prompt = (
            "You are a P&ID visual evidence extractor. Inspect the attached image and return one "
            "complete JSON object only. Extract visible title, equipment, valves, instruments, process "
            "connections in flow order, utilities and off-page connections, labels, and approximate "
            "relative layout. Repeated modules and repeated labels are evidence, not noise. Never merge "
            "several outlet destinations into one slash-separated label. Do not create drawing operations "
            "and do not explain your reasoning. Use arrays named equipment, valves, instruments, "
            "connections, utilities, labels, layout_notes, and major_paths. Also return cabinet_branches "
            "as an object whose keys are exact cabinet labels and whose values are arrays containing every "
            "visible outlet destination label for that cabinet, in top-to-bottom order. In major_paths, "
            "describe each continuous colored/header route, its DN, color, source, destination, branches, "
            "and risers. Record explicit module counts and per-module outlet counts in layout_notes. Keep "
            "the complete response under 8000 output tokens."
        )
        extraction_prompt = (
            "Extract the visible engineering evidence needed to faithfully reconstruct this P&ID. "
            f"The user's reconstruction instruction is: {user_prompt}"
        )
        started = perf_counter()
        if self.diagnostics is not None:
            self.diagnostics.emit(
                "llm.vision_evidence.started",
                model=provider.model,
                base_url=provider.base_url,
                reference_image_count=len(images),
            )
        try:
            evidence = self._request_model_json_once(
                evidence_provider,
                system_prompt=system_prompt,
                user_prompt=extraction_prompt,
                temperature=0.0,
                images=images,
                max_completion_tokens=8_192,
            )
        except (LLMPlanValidationError, LLMResponseError) as exc:
            if isinstance(exc, LLMResponseError) and "finish_reason=length" not in str(exc):
                raise
            evidence = self._request_model_json_once(
                evidence_provider,
                system_prompt=system_prompt,
                user_prompt=(
                    extraction_prompt
                    + "\nThe previous extraction was incomplete. Return a shorter but complete JSON object."
                ),
                temperature=0.0,
                images=images,
                max_completion_tokens=16_384,
            )
        evidence_keys = (
            "equipment",
            "valves",
            "instruments",
            "connections",
            "utilities",
        )
        if not any(isinstance(evidence.get(key), list) and evidence[key] for key in evidence_keys):
            raise LLMPlanValidationError(
                "K3 visual extraction returned no usable P&ID equipment or connections",
                provider=provider,
            )
        if self.diagnostics is not None:
            self.diagnostics.emit(
                "llm.vision_evidence.completed",
                model=provider.model,
                base_url=provider.base_url,
                reference_image_count=len(images),
                duration_ms=round((perf_counter() - started) * 1000, 2),
                evidence_counts={
                    key: len(evidence.get(key, []))
                    for key in evidence_keys
                    if isinstance(evidence.get(key), list)
                },
            )
        return evidence

    def _request_model_json(
        self,
        provider: ProviderConfig,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        repair: bool = False,
    ) -> dict[str, Any]:
        attached_images = self._request_images.get()
        schema_repair = repair
        request_images = () if schema_repair else attached_images
        request_provider = provider
        if attached_images and is_kimi_k3_provider(provider):
            request_provider = provider.model_copy(
                update={"thinking_enabled": True, "thinking_level": "low"}
            )
            if self.diagnostics is not None:
                self.diagnostics.emit(
                    (
                        "llm.vision_schema_repair.optimized"
                        if schema_repair
                        else "llm.vision_reasoning.optimized"
                    ),
                    model=provider.model,
                    base_url=provider.base_url,
                    omitted_reference_image_count=(
                        len(attached_images) if schema_repair else 0
                    ),
                    requested_thinking_level=provider.thinking_level,
                    effective_thinking_level="low",
                )
        try:
            return self._request_model_json_once(
                request_provider,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
                images=request_images,
            )
        except (LLMPlanValidationError, LLMResponseError) as exc:
            if isinstance(exc, LLMResponseError) and "finish_reason=length" not in str(exc):
                raise
            if not is_kimi_k3_provider(provider):
                raise
            recovery_provider = provider.model_copy(
                update={"thinking_enabled": True, "thinking_level": "low"}
            )
            if self.diagnostics is not None:
                self.diagnostics.emit(
                    "llm.vision_json_recovery.started",
                    model=provider.model,
                    base_url=provider.base_url,
                    reference_image_count=len(attached_images),
                    requested_thinking_level=provider.thinking_level,
                    recovery_thinking_level="low",
                )
            try:
                recovered = self._request_model_json_once(
                    recovery_provider,
                    system_prompt=system_prompt,
                    user_prompt=(
                        user_prompt
                        + "\n\nRecovery requirement: the previous response contained malformed or "
                        "truncated JSON. Produce a complete, compact transaction. Use concise IDs and "
                        "labels, omit optional prose, and close every JSON object and array."
                    ),
                    temperature=0.0,
                    images=request_images,
                    max_completion_tokens=32_768,
                )
            except (LLMPlanValidationError, LLMResponseError):
                if self.diagnostics is not None:
                    self.diagnostics.emit(
                        "llm.vision_json_recovery.failed",
                        model=provider.model,
                        base_url=provider.base_url,
                        reference_image_count=len(attached_images),
                    )
                raise
            if self.diagnostics is not None:
                self.diagnostics.emit(
                    "llm.vision_json_recovery.completed",
                    model=provider.model,
                    base_url=provider.base_url,
                    reference_image_count=len(attached_images),
                )
            return recovered

    def _request_model_json_once(
        self,
        provider: ProviderConfig,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        images: tuple[AgentImageInput, ...],
        max_completion_tokens: int | None = None,
    ) -> dict[str, Any]:
        user_content = multimodal_user_content(
            reference_image_prompt(images) + user_prompt,
            images,
        )
        payload: dict[str, Any] = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "temperature": completion_temperature(provider, temperature),
            "response_format": {"type": "json_object"},
        }
        payload.update(completion_budget_fields(provider, vision=bool(images)))
        if max_completion_tokens is not None:
            payload["max_completion_tokens"] = max_completion_tokens
        payload.update(thinking_request_fields(provider))
        headers = OpenAICompatiblePlanner._headers(provider)
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(
                timeout=provider.timeout_seconds,
                follow_redirects=False,
                transport=provider_http_transport(self.provider_transport.provider_policy),
            ) as client:
                response = request_with_response_limit(
                    client,
                    "POST",
                    endpoint,
                    self.provider_transport.max_response_bytes,
                    json=payload,
                    headers=headers,
                )
                self.provider_transport._inspect_response(response, provider, endpoint)
                if _response_format_rejected(response):
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    fallback_payload.pop("thinking", None)
                    fallback_payload.pop("reasoning_effort", None)
                    fallback_payload.pop("max_completion_tokens", None)
                    response = request_with_response_limit(
                        client,
                        "POST",
                        endpoint,
                        self.provider_transport.max_response_bytes,
                        json=fallback_payload,
                        headers=headers,
                    )
                    self.provider_transport._inspect_response(response, provider, endpoint)
        except ProviderURLPolicyError as exc:
            if exc.category == "response size":
                raise ProviderResponseTooLargeError(str(exc), provider=provider) from exc
            raise ProviderNetworkPolicyError(
                str(exc), category=exc.category, provider=provider
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"model did not finish within {provider.timeout_seconds:g} seconds",
                provider=provider,
                timeout_seconds=provider.timeout_seconds,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                "could not connect to model provider",
                provider=provider,
            ) from exc

        if images and _vision_input_rejected(response):
            provider_message = _provider_error_text(response)
            raise ProviderVisionUnsupportedError(
                "模型或 OpenAI 兼容接口明确拒绝了图片输入。"
                f" Provider 返回：{provider_message}",
                provider=provider,
                provider_status=response.status_code,
            )
        OpenAICompatiblePlanner._raise_for_response(response, provider)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMResponseError(
                "model response was not valid JSON",
                provider=provider,
            ) from exc
        try:
            content = extract_chat_content(data)
        except ValueError as exc:
            raise LLMResponseError(str(exc), provider=provider) from exc
        return OpenAICompatiblePlanner._parse_json(content, provider)
