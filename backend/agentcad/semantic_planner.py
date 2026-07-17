from __future__ import annotations

import json

import httpx
from pydantic import ValidationError

from .agent_semantic_models import (
    AgentTransactionAssessment,
    SemanticAgentPlan,
    SemanticAgentReplanRequest,
    SemanticTransaction,
)
from .llm import (
    LLMPlanValidationError,
    LLMResponseError,
    OpenAICompatiblePlanner,
    ProviderConnectionError,
    ProviderTimeoutError,
)
from .models import AgentGenerateRequest, ProviderConfig
from .service import DocumentService
from .symbols import SymbolRegistry


class SemanticAgentPlanner:
    def __init__(self, service: DocumentService, symbols: SymbolRegistry):
        self.service = service
        self.symbols = symbols

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
        plan = self._request_plan(provider, user_prompt, repair=False)
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
        plan = self._request_plan(provider, user_prompt, repair=True)
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
    ) -> SemanticAgentPlan:
        schema = SemanticTransaction.model_json_schema()
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": self._system_prompt(schema, repair=repair)},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.05 if repair else 0.1,
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

        raw_plan = OpenAICompatiblePlanner._parse_json(content, provider)
        if "transaction" not in raw_plan and "operations" in raw_plan:
            raw_plan = {
                "explanation": raw_plan.get("explanation", ""),
                "transaction": {
                    "operations": raw_plan["operations"],
                    "label": raw_plan.get("label", "Agent semantic modification"),
                },
            }
        try:
            return SemanticAgentPlan.model_validate(raw_plan)
        except ValidationError as exc:
            raise LLMPlanValidationError(
                f"model returned a semantic transaction that does not match the schema: {exc}",
                provider=provider,
            ) from exc

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
            "Use connect_ports to create a semantic pipe between two real ports. "
            "Use reconnect_connector to move one existing connector endpoint; never edit source or target "
            "through update_element. Use replace_symbol to replace equipment while preserving connector IDs; "
            "provide port_mapping whenever old connected port IDs do not exist on the replacement. "
            "Use delete_element with an explicit connection_policy. Prefer reject_if_connected unless the user "
            "clearly asked to leave detached pipes or delete the connected pipes. "
            "Never change symbol_key through update_element. Use junction ports only as 'node'. "
            "Keep connector routes orthogonal. Include expected_revision and a concise transaction label. "
            f"{mode}\n\n"
            f"Available symbol catalog:\n{self.symbols.as_prompt_catalog()}\n\n"
            f"Semantic transaction JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )
