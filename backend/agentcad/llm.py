from __future__ import annotations

import json
import os
import re
from typing import Any

import httpx

from .models import AgentGenerateRequest, AgentPlan, ProviderConfig, TransactionRequest
from .service import DocumentService
from .symbols import SymbolRegistry


class ProviderNotConfiguredError(RuntimeError):
    pass


class LLMResponseError(RuntimeError):
    pass


def _env(primary: str, legacy: str) -> str | None:
    return os.getenv(primary) or os.getenv(legacy)


class OpenAICompatiblePlanner:
    def __init__(self, service: DocumentService, symbols: SymbolRegistry):
        self.service = service
        self.symbols = symbols

    def plan(self, document_id: str, request: AgentGenerateRequest) -> AgentPlan:
        provider = self._resolve_provider(request.provider)
        document = self.service.get_document(document_id)
        schema = TransactionRequest.model_json_schema()
        system_prompt = self._system_prompt(schema)
        scene = self.service.scene_summary(document_id)
        user_prompt = (
            f"Current document JSON:\n{document.model_dump_json(indent=2)}\n\n"
            f"Scene summary:\n{json.dumps(scene, ensure_ascii=False, indent=2)}\n\n"
            f"Additional process/design context:\n{request.context or '(none)'}\n\n"
            f"User request:\n{request.prompt}"
        )
        payload = {
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.1,
            "response_format": {"type": "json_object"},
        }
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        with httpx.Client(timeout=provider.timeout_seconds) as client:
            response = client.post(endpoint, json=payload, headers=headers)
            if response.status_code in {400, 404, 422} and "response_format" in payload:
                fallback_payload = dict(payload)
                fallback_payload.pop("response_format", None)
                response = client.post(endpoint, json=fallback_payload, headers=headers)
        if response.is_error:
            raise LLMResponseError(
                f"LLM request failed with HTTP {response.status_code}: {response.text[:1000]}"
            )
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "LLM response did not contain choices[0].message.content"
            ) from exc
        raw_plan = self._parse_json(content)
        if "transaction" not in raw_plan and "operations" in raw_plan:
            raw_plan = {
                "explanation": raw_plan.get("explanation", ""),
                "transaction": {
                    "operations": raw_plan["operations"],
                    "label": raw_plan.get("label", "Agent generated drawing"),
                    "expected_revision": request.expected_revision,
                },
            }
        plan = AgentPlan.model_validate(raw_plan)
        if plan.transaction.expected_revision is None:
            plan.transaction.expected_revision = request.expected_revision
        return plan

    def _system_prompt(self, schema: dict[str, Any]) -> str:
        return (
            "You are P&ID-Agent's planning engine. Convert the user's process description "
            "into one valid atomic drawing transaction. Use only symbols from the catalog. "
            "Preserve existing elements unless the user explicitly asks to modify or delete them. "
            "Prefer connector elements for process pipes so source/target semantics remain machine-readable. "
            "Use junction elements for real branch and merge topology, not visual overlaps. "
            "Use orthogonal connector point sequences when practical. Return JSON only with keys "
            "'explanation' and 'transaction'. Never invent operation types or symbol keys.\n\n"
            f"Available symbol catalog:\n{self.symbols.as_prompt_catalog()}\n\n"
            f"Transaction JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _resolve_provider(override: ProviderConfig | None) -> ProviderConfig:
        provider = override or ProviderConfig()
        base_url = provider.base_url or _env("PID_AGENT_LLM_BASE_URL", "AGENTCAD_LLM_BASE_URL")
        model = provider.model or _env("PID_AGENT_LLM_MODEL", "AGENTCAD_LLM_MODEL")
        api_key = provider.api_key or _env("PID_AGENT_LLM_API_KEY", "AGENTCAD_LLM_API_KEY")
        if not base_url or not model:
            raise ProviderNotConfiguredError(
                "configure PID_AGENT_LLM_BASE_URL and PID_AGENT_LLM_MODEL, "
                "or pass provider.base_url and provider.model"
            )
        root = base_url.rstrip("/")
        normalized = root if root.endswith("/v1") else root + "/v1"
        return ProviderConfig(
            base_url=normalized,
            model=model,
            api_key=api_key,
            timeout_seconds=provider.timeout_seconds,
        )

    @staticmethod
    def _parse_json(content: str) -> dict[str, Any]:
        text = content.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMResponseError(f"LLM returned invalid JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise LLMResponseError("LLM plan must be a JSON object")
        return value
