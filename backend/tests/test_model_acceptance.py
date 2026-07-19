from pathlib import Path

from fastapi.testclient import TestClient

from agentcad.agent_semantic_models import (
    ConnectPortsOperation,
    ReconnectConnectorOperation,
    ReplaceSymbolOperation,
    SafeDeleteElementOperation,
    SemanticAgentPlan,
    SemanticTransaction,
)
from agentcad.config import Settings
from agentcad.llm import ProviderConnectionError
from agentcad.main import create_app
from agentcad.model_acceptance import ModelMatrixRequest, run_model_matrix
from agentcad.models import (
    AddElementOperation,
    Point,
    ProviderConfig,
    SymbolElement,
    UpdateElementOperation,
)
from agentcad.semantic_planner import SemanticAgentPlanner
from agentcad.symbols import SymbolRegistry


def provider():
    return ProviderConfig(base_url="http://model.test/v1", model="matrix-model", api_key="secret")


def valid_plan(self, document_id, request):
    revision = self.service.get_document(document_id).revision
    prompt = request.prompt
    if "added_valve" in prompt:
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
        explanation="deterministic acceptance plan",
        transaction=SemanticTransaction(
            expected_revision=revision,
            label="Acceptance scenario",
            operations=operations,
        ),
    )


def test_model_matrix_passes_only_after_repeated_topology_assertions(monkeypatch):
    monkeypatch.setattr(SemanticAgentPlanner, "plan", valid_plan)
    report = run_model_matrix(
        ModelMatrixRequest(provider=provider(), repetitions=3, max_replans=2),
        SymbolRegistry(),
    )

    assert report.accepted is True
    assert report.total_cases == 15
    assert report.passed_cases == 15
    assert report.failed_cases == 0
    assert report.blocked_cases == 0
    assert report.pass_rate == 1


def test_single_repetition_is_a_trial_not_an_acceptance(monkeypatch):
    monkeypatch.setattr(SemanticAgentPlanner, "plan", valid_plan)
    report = run_model_matrix(
        ModelMatrixRequest(provider=provider(), repetitions=1, max_replans=2),
        SymbolRegistry(),
    )

    assert report.passed_cases == 5
    assert report.accepted is False
    assert report.minimum_acceptance_repetitions == 3


def test_model_matrix_uses_structured_replan_until_valid(monkeypatch):
    def invalid_initial(self, document_id, request):
        revision = self.service.get_document(document_id).revision
        return SemanticAgentPlan(
            explanation="invalid first attempt",
            transaction=SemanticTransaction(
                expected_revision=revision,
                label="Invalid first attempt",
                operations=[
                    UpdateElementOperation(
                        element_id="missing_element",
                        patch={"position": {"x": 10, "y": 10}},
                    )
                ],
            ),
        )

    def repaired(self, document_id, request, failure):
        assert failure.valid is False
        assert failure.issues[0].code == "element_not_found"
        generated = type("GenerateRequest", (), {"prompt": request.prompt})()
        return valid_plan(self, document_id, generated)

    monkeypatch.setattr(SemanticAgentPlanner, "plan", invalid_initial)
    monkeypatch.setattr(SemanticAgentPlanner, "replan", repaired)
    report = run_model_matrix(
        ModelMatrixRequest(provider=provider(), repetitions=1, max_replans=2),
        SymbolRegistry(),
    )

    assert report.passed_cases == 5
    assert all(case.attempts == 1 for case in report.cases)
    assert all("element_not_found" in case.issue_codes for case in report.cases)
    assert report.convergence_rate == 1
    assert report.accepted is False


def test_model_matrix_marks_retryable_provider_failure_blocked(monkeypatch):
    def blocked(self, document_id, request):
        raise ProviderConnectionError("offline", provider=request.provider)

    monkeypatch.setattr(SemanticAgentPlanner, "plan", blocked)
    report = run_model_matrix(
        ModelMatrixRequest(provider=provider(), repetitions=1, max_replans=0),
        SymbolRegistry(),
    )

    assert report.accepted is False
    assert report.blocked_cases == 5
    assert report.failed_cases == 0


def settings(tmp_path: Path):
    return Settings(
        database_path=tmp_path / "acceptance.db",
        cors_origins=["http://localhost:5173"],
        frontend_dist=tmp_path / "missing",
        diagnostics_path=tmp_path / "diagnostics.jsonl",
    )


def test_acceptance_endpoint_never_echoes_api_key(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(SemanticAgentPlanner, "plan", valid_plan)
    client = TestClient(create_app(settings(tmp_path)))
    response = client.post(
        "/api/v2/acceptance/model-matrix",
        json={
            "provider": {
                "base_url": "http://model.test/v1",
                "model": "matrix-model",
                "api_key": "secret-provider-key",
                "timeout_seconds": 30,
            },
            "repetitions": 3,
            "max_replans": 2,
        },
    )

    assert response.status_code == 200
    assert response.json()["accepted"] is True
    assert "secret-provider-key" not in response.text


def test_acceptance_browser_ui_is_available(tmp_path: Path):
    client = TestClient(create_app(settings(tmp_path)))
    response = client.get("/api/v2/acceptance/model-matrix/ui")

    assert response.status_code == 200
    assert "真实模型验收矩阵" in response.text
    assert "localStorage" in response.text
