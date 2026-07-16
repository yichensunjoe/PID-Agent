from __future__ import annotations

import json
import os
import re
from time import perf_counter
from typing import Any

import httpx
from pydantic import ValidationError

from .models import AgentGenerateRequest, AgentPlan, ProviderConfig, TransactionRequest
from .service import DocumentService
from .symbols import SymbolRegistry


class PlannerError(RuntimeError):
    code = "planner_error"
    status_code = 502
    retryable = False

    def __init__(
        self,
        message: str,
        *,
        provider: ProviderConfig | None = None,
        timeout_seconds: float | None = None,
        provider_status: int | None = None,
    ):
        super().__init__(message)
        self.provider = provider
        self.timeout_seconds = timeout_seconds
        self.provider_status = provider_status

    def detail(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error": self.code,
            "message": str(self),
            "retryable": self.retryable,
        }
        if self.provider is not None:
            payload["provider"] = {
                "base_url": self.provider.base_url,
                "model": self.provider.model,
            }
        if self.timeout_seconds is not None:
            payload["timeout_seconds"] = self.timeout_seconds
        if self.provider_status is not None:
            payload["provider_status"] = self.provider_status
        return payload


class ProviderNotConfiguredError(PlannerError):
    code = "provider_not_configured"
    status_code = 503


class ProviderTimeoutError(PlannerError):
    code = "provider_timeout"
    status_code = 504
    retryable = True


class ProviderConnectionError(PlannerError):
    code = "provider_connection_failed"
    status_code = 502
    retryable = True


class ProviderAuthenticationError(PlannerError):
    code = "provider_authentication_failed"
    status_code = 401


class LLMResponseError(PlannerError):
    code = "provider_response_error"
    status_code = 502


class LLMPlanValidationError(PlannerError):
    code = "invalid_agent_plan"
    status_code = 422


def _env(primary: str, legacy: str) -> str | None:
    return os.getenv(primary) or os.getenv(legacy)


class OpenAICompatiblePlanner:
    def __init__(self, service: DocumentService, symbols: SymbolRegistry):
        self.service = service
        self.symbols = symbols

    def test_provider(self, override: ProviderConfig | None) -> dict[str, Any]:
        """Verify an OpenAI-compatible provider without persisting credentials."""
        provider = self._resolve_provider(override)
        headers = self._headers(provider)
        started = perf_counter()
        models_endpoint = provider.base_url.rstrip("/") + "/models"

        try:
            with httpx.Client(timeout=provider.timeout_seconds) as client:
                response = client.get(models_endpoint, headers=headers)
                if response.status_code in {404, 405}:
                    result = self._test_with_minimal_completion(client, provider, headers)
                    result["latency_ms"] = round((perf_counter() - started) * 1000)
                    return result
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"model provider did not respond within {provider.timeout_seconds:g} seconds",
                provider=provider,
                timeout_seconds=provider.timeout_seconds,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                f"could not connect to model provider: {exc}",
                provider=provider,
            ) from exc

        self._raise_for_response(response, provider)
        model_ids: list[str] = []
        try:
            payload = response.json()
            entries = payload.get("data", []) if isinstance(payload, dict) else []
            model_ids = [
                item["id"]
                for item in entries
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        except ValueError:
            model_ids = []

        model_available = provider.model in model_ids if model_ids else None
        return {
            "ok": True,
            "base_url": provider.base_url,
            "model": provider.model,
            "method": "models",
            "latency_ms": round((perf_counter() - started) * 1000),
            "model_available": model_available,
            "available_model_count": len(model_ids),
            "message": (
                "连接成功，指定模型可用"
                if model_available is True
                else "连接成功，但模型列表中未找到指定名称"
                if model_available is False
                else "连接成功，服务未返回可解析的模型列表"
            ),
        }

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
        headers = self._headers(provider)
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

        self._raise_for_response(response, provider)
        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "model response did not contain choices[0].message.content",
                provider=provider,
            ) from exc

        raw_plan = self._parse_json(content, provider)
        if "transaction" not in raw_plan and "operations" in raw_plan:
            raw_plan = {
                "explanation": raw_plan.get("explanation", ""),
                "transaction": {
                    "operations": raw_plan["operations"],
                    "label": raw_plan.get("label", "Agent generated drawing"),
                    "expected_revision": request.expected_revision,
                },
            }
        try:
            plan = AgentPlan.model_validate(raw_plan)
        except ValidationError as exc:
            raise LLMPlanValidationError(
                f"model returned a transaction that does not match the schema: {exc}",
                provider=provider,
            ) from exc
        if plan.transaction.expected_revision is None:
            plan.transaction.expected_revision = request.expected_revision
        return plan

    @staticmethod
    def _headers(provider: ProviderConfig) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if provider.api_key:
            headers["Authorization"] = f"Bearer {provider.api_key}"
        return headers

    def _test_with_minimal_completion(
        self,
        client: httpx.Client,
        provider: ProviderConfig,
        headers: dict[str, str],
    ) -> dict[str, Any]:
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"
        response = client.post(
            endpoint,
            headers=headers,
            json={
                "model": provider.model,
                "messages": [{"role": "user", "content": "Reply with OK."}],
                "temperature": 0,
                "max_tokens": 1,
                "stream": False,
            },
        )
        self._raise_for_response(response, provider)
        try:
            payload = response.json()
            payload["choices"][0]["message"]
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            raise LLMResponseError(
                "provider test response did not contain choices[0].message",
                provider=provider,
            ) from exc
        return {
            "ok": True,
            "base_url": provider.base_url,
            "model": provider.model,
            "method": "chat_completion",
            "model_available": True,
            "available_model_count": None,
            "message": "连接成功，模型完成了最小测试请求",
        }

    @staticmethod
    def _raise_for_response(response: httpx.Response, provider: ProviderConfig) -> None:
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "API Key 无效或没有访问该模型的权限",
                provider=provider,
                provider_status=response.status_code,
            )
        if response.is_error:
            raise LLMResponseError(
                f"model provider returned HTTP {response.status_code}: {response.text[:1000]}",
                provider=provider,
                provider_status=response.status_code,
            )

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
        custom_connection = bool(
            override is not None
            and (provider.base_url or provider.model or provider.api_key)
        )
        if custom_connection:
            base_url = provider.base_url
            model = provider.model
            api_key = provider.api_key
        else:
            base_url = _env("PID_AGENT_LLM_BASE_URL", "AGENTCAD_LLM_BASE_URL")
            model = _env("PID_AGENT_LLM_MODEL", "AGENTCAD_LLM_MODEL")
            api_key = _env("PID_AGENT_LLM_API_KEY", "AGENTCAD_LLM_API_KEY")
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
    def _parse_json(content: str, provider: ProviderConfig) -> dict[str, Any]:
        text = content.strip()
        fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        try:
            value = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMPlanValidationError(
                f"model returned invalid JSON: {exc}",
                provider=provider,
            ) from exc
        if not isinstance(value, dict):
            raise LLMPlanValidationError(
                "model plan must be a JSON object",
                provider=provider,
            )
        return value
