from agentcad.api_acceptance import ACCEPTANCE_UI


def test_acceptance_ui_exposes_optional_complex_diagram_case():
    assert 'id="complex"' in ACCEPTANCE_UI
    assert "增加复杂整图场景" in ACCEPTANCE_UI
    assert "include_complex_diagram" in ACCEPTANCE_UI
