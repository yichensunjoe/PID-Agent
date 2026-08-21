from agentcad.api_acceptance import ACCEPTANCE_UI, get_acceptance_ui


def test_acceptance_ui_exposes_optional_complex_diagram_case():
    assert 'id="complex"' in ACCEPTANCE_UI
    assert "增加复杂整图场景" in ACCEPTANCE_UI
    assert "include_complex_diagram" in ACCEPTANCE_UI


def test_get_acceptance_ui_respects_env_vars(monkeypatch):
    monkeypatch.setenv("PID_AGENT_ACCEPTANCE_BASE_URL", "https://custom-llm.example/v1")
    monkeypatch.setenv("PID_AGENT_ACCEPTANCE_MODEL", "custom-matrix-model")
    html = get_acceptance_ui()
    assert 'value="https://custom-llm.example/v1"' in html
    assert 'value="custom-matrix-model"' in html

