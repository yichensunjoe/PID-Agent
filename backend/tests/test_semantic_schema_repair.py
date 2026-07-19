from __future__ import annotations

import pytest

from agentcad.models import Document, ProviderConfig
from agentcad.semantic_planner import (
    SemanticAgentPlanner,
    SemanticPlanValidationError,
)


class _Symbols:
    @staticmethod
    def as_prompt_catalog() -> str:
        return "[]"


def _planner() -> SemanticAgentPlanner:
    return SemanticAgentPlanner(service=object(), symbols=_Symbols())  # type: ignore[arg-type]


def _connector_operation(index: int, junction_id: str, *, port_id: str | None = None):
    source = {
        "element_id": junction_id,
        "point": {"x": 100 + index * 20, "y": 400},
    }
    if port_id is not None:
        source["port_id"] = port_id
    return {
        "op": "add_element",
        "element": {
            "id": f"pipe_{index}",
            "type": "connector",
            "points": [
                {"x": 100 + index * 20, "y": 400},
                {"x": 100 + index * 20, "y": 300},
            ],
            "source": source,
            "target": {"point": {"x": 100 + index * 20, "y": 300}},
            "routing": "orthogonal",
        },
    }


def test_complex_multi_junction_plan_is_normalized_without_model_repair(monkeypatch):
    planner = _planner()
    junction_ids = ["j_pt101", "j_te101", "j_pt102", "j_te102"]
    operations = [
        {
            "op": "add_element",
            "element": {
                "id": junction_id,
                "type": "junction",
                "position": {"x": 400 + index * 120, "y": 400},
            },
        }
        for index, junction_id in enumerate(junction_ids)
    ]
    operations.extend(
        _connector_operation(index, junction_ids[index % len(junction_ids)])
        for index in range(12)
    )
    responses = [
        {
            "explanation": "Create four instrument taps",
            "transaction": {
                "expected_revision": 0,
                "label": "Complex junction plan",
                "operations": operations,
            },
        }
    ]
    calls = []

    def fake_request(provider, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(planner, "_request_model_json", fake_request)
    plan = planner._request_plan(
        ProviderConfig(base_url="http://provider.test/v1", model="test-model"),
        "prompt",
        repair=False,
        document_id="doc_test",
        document=Document(id="doc_test"),
    )

    assert len(calls) == 1
    connectors = [
        operation.element
        for operation in plan.transaction.operations
        if operation.op == "add_element" and operation.element.type == "connector"
    ]
    assert len(connectors) == 12
    assert all(connector.source and connector.source.port_id == "node" for connector in connectors)


def test_schema_validation_failure_is_repaired_inside_planner(monkeypatch):
    planner = _planner()
    invalid = {
        "explanation": "Add a pipe",
        "transaction": {
            "expected_revision": 0,
            "label": "Add pipe",
            "operations": [_connector_operation(0, "pump")],
        },
    }
    repaired = {
        "explanation": "Add a pipe",
        "transaction": {
            "expected_revision": 0,
            "label": "Add pipe",
            "operations": [_connector_operation(0, "pump", port_id="out")],
        },
    }
    responses = [invalid, repaired]
    calls = []

    def fake_request(provider, **kwargs):
        calls.append(kwargs)
        return responses.pop(0)

    monkeypatch.setattr(planner, "_request_model_json", fake_request)
    plan = planner._request_plan(
        ProviderConfig(base_url="http://provider.test/v1", model="test-model"),
        "prompt",
        repair=False,
        document_id="doc_test",
        document=Document(id="doc_test"),
    )

    assert len(calls) == 2
    assert calls[1]["temperature"] == 0.0
    connector = plan.transaction.operations[0].element
    assert connector.type == "connector"
    assert connector.source and connector.source.port_id == "out"


def test_exhausted_schema_repairs_return_compact_structured_errors(monkeypatch):
    planner = _planner()
    invalid = {
        "explanation": "Add a pipe",
        "transaction": {
            "expected_revision": 0,
            "label": "Add pipe",
            "operations": [_connector_operation(0, "pump")],
        },
    }
    responses = [invalid, invalid, invalid]

    def fake_request(provider, **kwargs):
        return responses.pop(0)

    monkeypatch.setattr(planner, "_request_model_json", fake_request)
    with pytest.raises(SemanticPlanValidationError) as caught:
        planner._request_plan(
            ProviderConfig(base_url="http://provider.test/v1", model="test-model"),
            "prompt",
            repair=False,
            document_id="doc_test",
            document=Document(id="doc_test"),
        )

    detail = caught.value.detail()
    assert detail["error"] == "invalid_agent_plan"
    assert detail["schema_repair_attempts"] == 2
    assert detail["validation_errors"]
    assert all(set(error) == {"path", "type", "message"} for error in detail["validation_errors"])
    assert "pydantic.dev" not in detail["message"]
