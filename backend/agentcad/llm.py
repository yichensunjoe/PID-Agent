from __future__ import annotations

import json
import os
import re
from time import perf_counter
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import httpx
from pydantic import ValidationError

from .diagram_quality import drafting_prompt_contract
from .models import AgentGenerateRequest, AgentPlan, ProviderConfig, TransactionRequest
from .provider_compat import (
    completion_budget_fields,
    completion_temperature,
    extract_chat_content,
    thinking_request_fields,
)
from .provider_security import (
    ProviderNetworkPolicy,
    ProviderURLPolicyError,
    ensure_response_within_limit,
    provider_http_transport,
    request_with_response_limit,
)
from .service import DocumentService
from .symbols import SymbolRegistry


def _safe_provider_url(value: str | None) -> str | None:
    if not value:
        return value
    parsed = urlsplit(value)
    host = parsed.hostname or ""
    try:
        port = parsed.port
    except ValueError:
        port = None
    if port:
        host = f"{host}:{port}"
    return urlunsplit((parsed.scheme, host, parsed.path, "", ""))


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
                "base_url": _safe_provider_url(self.provider.base_url),
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


class ProviderNetworkPolicyError(PlannerError):
    code = "provider_url_blocked"
    status_code = 403

    def __init__(self, message: str, *, category: str, provider: ProviderConfig | None = None):
        super().__init__(message, provider=provider)
        self.category = category

    def detail(self) -> dict[str, Any]:
        payload = super().detail()
        payload["blocked_category"] = self.category
        return payload


class ProviderResponseTooLargeError(PlannerError):
    code = "provider_response_too_large"
    status_code = 502


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
    def __init__(
        self,
        service: DocumentService,
        symbols: SymbolRegistry,
        *,
        provider_policy: ProviderNetworkPolicy | None = None,
        max_response_bytes: int = 4 * 1024 * 1024,
        max_timeout_seconds: float | None = None,
    ):
        self.service = service
        self.symbols = symbols
        self.provider_policy = provider_policy or ProviderNetworkPolicy()
        self.max_response_bytes = max_response_bytes
        self.max_timeout_seconds = max_timeout_seconds

    def test_provider(self, override: ProviderConfig | None) -> dict[str, Any]:
        """Verify model discovery and one real completion without persisting credentials."""
        provider = self._resolve_provider(override, self.provider_policy, self.max_timeout_seconds)
        headers = self._headers(provider)
        started = perf_counter()
        models_endpoint = provider.base_url.rstrip("/") + "/models"
        model_ids: list[str] = []
        model_available: bool | None = None

        try:
            with httpx.Client(
                timeout=provider.timeout_seconds,
                follow_redirects=False,
                transport=provider_http_transport(self.provider_policy),
            ) as client:
                response = request_with_response_limit(
                    client,
                    "GET",
                    models_endpoint,
                    self.max_response_bytes,
                    headers=headers,
                )
                self._inspect_response(response, provider, models_endpoint)
                if response.status_code in {404, 405}:
                    result = self._test_with_minimal_completion(client, provider, headers)
                    result["latency_ms"] = round((perf_counter() - started) * 1000)
                    return result
                self._raise_for_response(response, provider)
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

                # A successful /models response proves discovery access only. Some
                # providers list cloud models that the current account cannot run,
                # so the test must exercise the same completion path as generation.
                result = self._test_with_minimal_completion(client, provider, headers)
        except ProviderURLPolicyError as exc:
            if exc.category == "response size":
                raise ProviderResponseTooLargeError(str(exc), provider=provider) from exc
            raise ProviderNetworkPolicyError(
                str(exc), category=exc.category, provider=provider
            ) from exc
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                f"model provider did not respond within {provider.timeout_seconds:g} seconds",
                provider=provider,
                timeout_seconds=provider.timeout_seconds,
            ) from exc
        except httpx.RequestError as exc:
            raise ProviderConnectionError(
                "could not connect to model provider",
                provider=provider,
            ) from exc

        result.update(
            {
                "latency_ms": round((perf_counter() - started) * 1000),
                "model_available": model_available,
                "available_model_count": len(model_ids),
                "message": (
                    "连接成功，指定模型完成了最小生成测试"
                    if model_available is True
                    else "模型列表中未找到指定名称，但该模型完成了最小生成测试"
                    if model_available is False
                    else "连接成功，模型完成了最小生成测试"
                ),
            }
        )
        return result

    def plan(self, document_id: str, request: AgentGenerateRequest) -> AgentPlan:
        provider = self._resolve_provider(request.provider, self.provider_policy, self.max_timeout_seconds)
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
            "temperature": completion_temperature(provider, 0.1),
            "response_format": {"type": "json_object"},
        }
        payload.update(completion_budget_fields(provider))
        payload.update(thinking_request_fields(provider))
        headers = self._headers(provider)
        endpoint = provider.base_url.rstrip("/") + "/chat/completions"

        try:
            with httpx.Client(
                timeout=provider.timeout_seconds,
                follow_redirects=False,
                transport=provider_http_transport(self.provider_policy),
            ) as client:
                response = request_with_response_limit(
                    client,
                    "POST",
                    endpoint,
                    self.max_response_bytes,
                    json=payload,
                    headers=headers,
                )
                self._inspect_response(response, provider, endpoint)
                if response.status_code in {400, 404, 422} and any(
                    key in payload for key in (
                        "response_format",
                        "thinking",
                        "reasoning_effort",
                        "max_completion_tokens",
                    )
                ):
                    fallback_payload = dict(payload)
                    fallback_payload.pop("response_format", None)
                    fallback_payload.pop("thinking", None)
                    fallback_payload.pop("reasoning_effort", None)
                    fallback_payload.pop("max_completion_tokens", None)
                    response = request_with_response_limit(
                        client,
                        "POST",
                        endpoint,
                        self.max_response_bytes,
                        json=fallback_payload,
                        headers=headers,
                    )
                    self._inspect_response(response, provider, endpoint)
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

        self._raise_for_response(response, provider)
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
        plan.transaction.expected_revision = (
            request.expected_revision
            if request.expected_revision is not None
            else document.revision
        )
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
        payload = {
            "model": provider.model,
            "messages": [{"role": "user", "content": "Reply with OK."}],
            "temperature": completion_temperature(provider, 0),
            "max_tokens": 1,
            "stream": False,
            **thinking_request_fields(provider),
        }
        response = request_with_response_limit(
            client,
            "POST",
            endpoint,
            self.max_response_bytes,
            headers=headers,
            json=payload,
        )
        self._inspect_response(response, provider, endpoint)
        if response.status_code in {400, 404, 422} and any(
            key in payload for key in ("thinking", "reasoning_effort")
        ):
            fallback_payload = dict(payload)
            fallback_payload.pop("thinking", None)
            fallback_payload.pop("reasoning_effort", None)
            response = request_with_response_limit(
                client,
                "POST",
                endpoint,
                self.max_response_bytes,
                headers=headers,
                json=fallback_payload,
            )
            self._inspect_response(response, provider, endpoint)
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

    def _inspect_response(
        self, response: httpx.Response, provider: ProviderConfig, request_url: str
    ) -> None:
        try:
            self.provider_policy.validate_redirect(request_url, response)
            ensure_response_within_limit(response, self.max_response_bytes)
        except ProviderURLPolicyError as exc:
            if exc.category == "response size":
                raise ProviderResponseTooLargeError(str(exc), provider=provider) from exc
            raise ProviderNetworkPolicyError(
                str(exc), category=exc.category, provider=provider
            ) from exc

    @staticmethod
    def _raise_for_response(response: httpx.Response, provider: ProviderConfig) -> None:
        if response.status_code in {401, 403}:
            raise ProviderAuthenticationError(
                "API Key 无效或没有访问该模型的权限",
                provider=provider,
                provider_status=response.status_code,
            )
        if response.is_error:
            body = response.text[:1000]
            if response.status_code in {408, 504, 524, 529}:
                raise LLMResponseError(
                    "model provider timed out before returning a completion; "
                    "try a lower thinking level or a smaller reference image",
                    provider=provider,
                    provider_status=response.status_code,
                )
            if response.status_code == 400 and "invalid temperature" in body.lower():
                raise LLMResponseError(
                    "模型拒绝了 temperature 参数。部分推理模型要求固定采样温度或不支持显式 temperature；"
                    "请在提供商配置中检查模型与端点设置。",
                    provider=provider,
                    provider_status=response.status_code,
                )
            raise LLMResponseError(
                f"model provider returned HTTP {response.status_code}",
                provider=provider,
                provider_status=response.status_code,
            )

    def _system_prompt(self, schema: dict[str, Any]) -> str:
        return (
            "You are P&ID-Agent's deterministic engineering planning engine. Convert the user's "
            "process intent into one valid atomic drawing transaction. Engineering topology and drafting "
            "quality are equally mandatory. Preserve unrelated elements and use only catalog symbols, "
            "real ports, junctions for real topology, and connector elements for process pipes. Never "
            "invent operation types, symbol keys, ports, decorative pipes, or arrow text. Return JSON only "
            "with keys 'explanation' and 'transaction'.\n\n"
            f"{drafting_prompt_contract()}\n\n"
            f"Available symbol catalog:\n{self.symbols.as_prompt_catalog()}\n\n"
            f"Transaction JSON Schema:\n{json.dumps(schema, ensure_ascii=False)}"
        )

    @staticmethod
    def _resolve_provider(
        override: ProviderConfig | None,
        policy: ProviderNetworkPolicy | None = None,
        max_timeout_seconds: float | None = None,
    ) -> ProviderConfig:
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
        active_policy = policy or ProviderNetworkPolicy()
        timeout = provider.timeout_seconds
        if max_timeout_seconds is not None:
            timeout = min(timeout, max_timeout_seconds) if timeout is not None else max_timeout_seconds
        try:
            normalized = active_policy.normalize_and_validate(base_url)
        except ProviderURLPolicyError as exc:
            unsafe_provider = ProviderConfig(
                base_url=_safe_provider_url(base_url),
                model=model,
                thinking_enabled=provider.thinking_enabled,
                thinking_level=provider.thinking_level,
                timeout_seconds=timeout,
            )
            raise ProviderNetworkPolicyError(
                str(exc), category=exc.category, provider=unsafe_provider
            ) from exc
        return ProviderConfig(
            base_url=normalized,
            model=model,
            api_key=api_key,
            thinking_enabled=provider.thinking_enabled,
            thinking_level=provider.thinking_level,
            timeout_seconds=timeout,
        )

    @staticmethod
    def _parse_json(content: str, provider: ProviderConfig) -> dict[str, Any]:
        text = content.strip()
        fence = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL)
        if fence:
            text = fence.group(1)
        else:
            # some models wrap JSON in prose without a fence; take the outermost object
            first = text.find("{")
            last = text.rfind("}")
            if first != -1 and last != -1 and last > first:
                text = text[first : last + 1]
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
