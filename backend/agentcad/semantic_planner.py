from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

import httpx
from pydantic import ValidationError

from .agent_semantic_models import (
    AgentTransactionAssessment,
    SemanticAgentPlan,
    SemanticAgentReplanRequest,
    SemanticTransaction,
)
from .diagnostics import DiagnosticLogger
from .llm import (
    LLMPlanValidationError,
    LLMResponseError,
    OpenAICompatiblePlanner,
    ProviderConnectionError,
    ProviderTimeoutError,
)
from .models import AgentGenerateRequest, Document, ProviderConfig
from .service import DocumentService
from .symbols import SymbolRegistry

MAX_SCHEMA_REPAIRS = 2


class SemanticPlanValidationError(LLMPlanValidationError):
    def __init__(
        self,
        message: str,
        *,
        provider: ProviderConfig,
        validation_errors: list[dict[str, str]],
        schema_repair_attempts: int,
        normalized_field_count: int,
    ):
        super().__init__(message, provider=provider)
        self.validation_errors = validation_errors
        self.schema_repair_attempts = schema_repair_attempts
        self.normalized_field_count = normalized_field_count

    def detail(self) -> dict[str, Any]:
        payload = super().detail()
        payload.update(
            {
                "validation_errors": self.validation_errors,
                "schema_repair_attempts": self.schema_repair_attempts,
                "normalized_field_count": self.normalized_field_count,
            }
        )
        return payload


class SemanticAgentPlanner:
    def __init__(
        self,
        service: DocumentService,
        symbols: SymbolRegistry,
        diagnostics: DiagnosticLogger | None = None,
    ):
        self.service = service
        self.symbols = symbols
        self.diagnostics = diagnostics

    def plan(self, document_id: str, request: AgentGenerateRequest) -> SemanticAgentPlan:
        provider = OpenAICompatiblePlanner._resolve_provider(request.provider)
        document = self.service.get_document(document_id)
        scene = self.service.scene_summary(document_id)
        user_prompt = (
            f"Current document JSON:\n{document.model_dump_json(indent=2)}\n\n"
            f"Scene summary:\n{json.dumps(scene, ensure_ascii=False, indent=2)}\n\n"
            f"Additional process/design context:\n{request.context or '(none)'}\n\n"
            f"User request:\n{request.prompt}"
        )
        plan = self._request_plan(
            provider,
            user_prompt,
            repair=False,
            document_id=document_id,
            document=document,
        )
        if plan.transaction.expected_revision is None:
            plan.transaction.expected_revision = request.expected_revision
        return plan

    def replan(
        self,
        document_id: str,
        request: SemanticAgentReplanRequest,
        failure: AgentTransactionAssessment,
    ) -> SemanticAgentPlan:
        provider = OpenAICompatiblePlanner._resolve_provider(request.provider)
        document = self.service.get_document(document_id)
        scene = self.service.scene_summary(document_id)
        user_prompt = (
            f"Current document JSON:\n{document.model_dump_json(indent=2)}\n\n"
            f"Scene summary:\n{json.dumps(scene, ensure_ascii=False, indent=2)}\n\n"
            f"Original process/design context:\n{request.context or '(none)'}\n\n"
            f"Original user request:\n{request.prompt}\n\n"
            f"Failed semantic plan:\n{request.failed_plan.model_dump_json(indent=2)}\n\n"
            f"Structured failure analysis:\n{failure.model_dump_json(indent=2)}\n\n"
            f"Repair attempt: {request.attempt}. Return a complete replacement plan, not a patch to the failed JSON."
        )
        plan = self._request_plan(
            provider,
            user_prompt,
            repair=True,
            document_id=document_id,
            document=document,
        )
        plan.transaction.expected_revision = (
            request.expected_revision
            if request.expected_revision is not None
            else document.revision
        )
        return plan

    def _request_plan(
        self,
        provider: ProviderConfig,
        user_prompt: str,
        *,
        repair: bool,
        document_id: str,
        document: Document,
    ) -> SemanticAgentPlan:
        schema = SemanticTransaction.model_json_schema()
        raw_plan = self._request_model_json(
            provider,
            system_prompt=self._system_prompt(schema, repair=repair),
            user_prompt=user_prompt,
            temperature=0.05 if repair else 0.1,
        )
        total_normalized = 0
        last_errors: list[dict[str, str]] = []

        for schema_attempt in range(MAX_SCHEMA_REPAIRS + 1):
            shaped = self._coerce_plan_shape(raw_plan)
            normalized, normalized_count, normalized_paths = self._normalize_raw_plan(
                shaped,
                document,
            )
            total_normalized += normalized_count
            if normalized_count and self.diagnostics is not None:
                self.diagnostics.emit(
                    "llm.semantic_schema_repair.normalized",
                    document_id=document_id,
                    schema_attempt=schema_attempt,
                    normalized_field_count=normalized_count,
                    normalized_field_paths=normalized_paths,
                    model=provider.model,
                    base_url=provider.base_url,
                )

            try:
                plan = SemanticAgentPlan.model_validate(normalized)
            except ValidationError as exc:
                last_errors = self._compact_validation_errors(exc)
                if schema_attempt >= MAX_SCHEMA_REPAIRS:
                    if self.diagnostics is not None:
                        self.diagnostics.emit(
                            "llm.semantic_schema_repair.failed",
                            document_id=document_id,
                            schema_repair_attempts=schema_attempt,
                            normalized_field_count=total_normalized,
                            validation_error_count=len(last_errors),
                            validation_error_paths=[item["path"] for item in last_errors],
                            model=provider.model,
                            base_url=provider.base_url,
                        )
                    summary = "; ".join(
                        f"{item['path']}: {item['message']}" for item in last_errors[:5]
                    )
                    if len(last_errors) > 5:
                        summary += f"; and {len(last_errors) - 5} more"
                    raise SemanticPlanValidationError(
                        "model returned an invalid semantic transaction after "
                        f"{schema_attempt} schema repair attempt(s): {summary}",
                        provider=provider,
                        validation_errors=last_errors,
                        schema_repair_attempts=schema_attempt,
                        normalized_field_count=total_normalized,
                    ) from exc

                repair_attempt = schema_attempt + 1
                if self.diagnostics is not None:
                    self.diagnostics.emit(
                        "llm.semantic_schema_repair.started",
                        document_id=document_id,
                        schema_repair_attempt=repair_attempt,
                        normalized_field_count=total_normalized,
                        validation_error_count=len(last_errors),
                        validation_error_paths=[item["path"] for item in last_errors],
                        model=provider.model,
                        base_url=provider.base_url,
                    )
                raw_plan = self._request_model_json(
                    provider,
                    system_prompt=self._schema_repair_system_prompt(),
                    user_prompt=self._schema_repair_user_prompt(
                        normalized,
                        last_errors,
                        schema,
                        repair_attempt,
                    ),
                    temperature=0.0,
                )
                continue

            if schema_attempt and self.diagnostics is not None:
                self.diagnostics.emit(
                    "llm.semantic_schema_repair.completed",
                    document_id=document_id,
                    schema_repair_attempts=schema_attempt,
                    normalized_field_count=total_normalized,
                    model=provider.model,
                    base_url=provider.base_url,
                )
            return plan

        raise AssertionError(f"unreachable schema repair state: {last_errors}")

    def _request_model_json(
        self,
        provider: ProviderConfig,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
    ) -> dict[str, Any]:
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        headers = OpenAICompatiblePlanner._headers(provider)
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        try:
            with httpx.Client(timeout=provider.timeout_seconds) as client:
                response = client.post(endpoint, json=payload, headers=headers)
                if response.status_code in {400, 404, 422} and "response_format" in payload:
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    response = client.post(endpoint, json=fallback_payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"model did not finish within {provider.timeout_seconds:g} seconds",
                provider=provider,
                timeout_seconds=provider.timeout_seconds,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"could not connect to model provider: {exc}",
                provider=provider,
            ) from exc

        OpenAICompatiblePlanner._raise_for_response(response, provider)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "model response did not contain choices[0].message.content",
                provider=provider,
            ) from exc
        return OpenAICompatiblePlanner._parse_json(content, provider)

    @staticmethod
    def _coerce_plan_shape(raw_plan: dict[str, Any]) -> dict[str, Any]:
        if "transaction" in raw_plan or "operations" not in raw_plan:
            return deepcopy(raw_plan)
        return {
            "explanation": raw_plan.get("explanation", ""),
            "transaction": {
                "operations": deepcopy(raw_plan["operations"]),
                "label": raw_plan.get("label", "Agent semantic modification"),
            },
        }

    @staticmethod
    def _normalize_raw_plan(
        raw_plan: dict[str, Any],
        document: Document,
    ) -> tuple[dict[str, Any], int, list[str]]:
        normalized = deepcopy(raw_plan)
        transaction = normalized.get("transaction")
        operations = transaction.get("operations") if isinstance(transaction, dict) else None
        if not isinstance(operations, list):
            return normalized, 0, []

        junction_ids = {
            element.id for element in document.elements if element.type == "junction"
        }
        for operation in operations:
            if not isinstance(operation, dict) or operation.get("op") != "add_element":
                continue
            element = operation.get("element")
            if (
                isinstance(element, dict)
                and element.get("type") == "junction"
                and isinstance(element.get("id"), str)
            ):
                junction_ids.add(element["id"])

        changed_paths: list[str] = []

        def normalize_endpoint(endpoint: Any, path: str) -> None:
            if not isinstance(endpoint, dict):
                return
            element_id = endpoint.get("element_id")
            if element_id in junction_ids and not endpoint.get("port_id"):
                endpoint["port_id"] = "node"
                changed_paths.append(f"{path}.port_id")

        for index, operation in enumerate(operations):
            if not isinstance(operation, dict):
                continue
            op = operation.get("op")
            if op == "add_element":
                element = operation.get("element")
                if isinstance(element, dict) and element.get("type") == "connector":
                    normalize_endpoint(
                        element.get("source"),
                        f"transaction.operations.{index}.add_element.element.connector.source",
                    )
                    normalize_endpoint(
                        element.get("target"),
                        f"transaction.operations.{index}.add_element.element.connector.target",
                    )
            elif op == "reconnect_connector":
                element_id = operation.get("element_id")
                if element_id in junction_ids and not operation.get("port_id"):
                    operation["port_id"] = "node"
                    changed_paths.append(
                        f"transaction.operations.{index}.reconnect_connector.port_id"
                    )
            elif op == "connect_ports":
                if (
                    operation.get("source_element_id") in junction_ids
                    and not operation.get("source_port_id")
                ):
                    operation["source_port_id"] = "node"
                    changed_paths.append(
                        f"transaction.operations.{index}.connect_ports.source_port_id"
                    )
                if (
                    operation.get("target_element_id") in junction_ids
                    and not operation.get("target_port_id")
                ):
                    operation["target_port_id"] = "node"
                    changed_paths.append(
                        f"transaction.operations.{index}.connect_ports.target_port_id"
                    )

        return normalized, len(changed_paths), changed_paths

    @staticmethod
    def _compact_validation_errors(exc: ValidationError) -> list[dict[str, str]]:
        compact: list[dict[str, str]] = []
        for error in exc.errors(
            include_url=False,
            include_context=False,
            include_input=False,
        )[:50]:
            compact.append(
                {
                    "path": ".".join(str(part) for part in error.get("loc", ())),
                    "type": str(error.get("type", "validation_error")),
                    "message": str(error.get("msg", "invalid value")),
                }
            )
        return compact

    @staticmethod
    def _schema_repair_system_prompt() -> str:
        return (
            "You repair P&ID-Agent semantic transaction JSON. Return one complete corrected JSON object only. "
            "Preserve the original engineering intent, IDs, coordinates, labels and operation order unless a "
            "validation error requires a change. Do not add unrelated elements. Every bound connector endpoint "
            "must provide both element_id and port_id. A junction endpoint always uses port_id 'node'. A free "
            "endpoint has no element_id or port_id and must provide point."
        )

    @staticmethod
    def _schema_repair_user_prompt(
        raw_plan: dict[str, Any],
        errors: list[dict[str, str]],
        schema: dict[str, Any],
        attempt: int,
    ) -> str:
        return (
            f"Schema repair attempt: {attempt}\n\n"
            f"Invalid semantic plan JSON:\n{json.dumps(raw_plan, ensure_ascii=False)}\n\n"
            f"Validation errors:\n{json.dumps(errors, ensure_ascii=False)}\n\n"
            f"Semantic transaction JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    def _system_prompt(self, schema: dict, *, repair: bool) -> str:
        mode = (
            "The previous plan failed. Use the structured issue code, available values and suggestions "
            "to produce the smallest complete corrected plan. Do not repeat the same invalid IDs, ports, "
            "symbol keys or endpoint edits."
            if repair
            else "Plan the smallest atomic change that satisfies the user request."
        )
        return (
            "You are P&ID-Agent's semantic planning engine. Return JSON only with keys "
            "'explanation' and 'transaction'. Preserve unrelated elements. Use only real element IDs, "
            "symbol keys and port IDs from the supplied document and catalog. "
            "When a later operation references an element or connector added earlier in the same transaction, "
            "assign an explicit unique id in the add operation and reuse that exact id. "
            "Use connect_ports to create a semantic pipe between two real ports. "
            "Use reconnect_connector to move one existing connector endpoint; never edit source or target "
            "through update_element. Use replace_symbol to replace equipment while preserving connector IDs; "
            "provide port_mapping whenever old connected port IDs do not exist on the replacement. "
            "Use delete_element with an explicit connection_policy. Prefer reject_if_connected unless the user "
            "clearly asked to leave detached pipes or delete the connected pipes. "
            "Never change symbol_key through update_element. Use junction ports only as 'node'. "
            "For add_element connector endpoints: element_id and port_id are an inseparable pair; a free endpoint "
            "must omit both and provide point. Keep connector routes orthogonal. Include expected_revision and a "
            f"concise transaction label. {mode}\n\n"
            f"Available symbol catalog:\n{self.symbols.as_prompt_catalog()}\n\n"
            f"Semantic transaction JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )
