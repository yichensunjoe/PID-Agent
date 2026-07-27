import pytest
from pydantic import ValidationError

from agentcad.agent_semantic_models import FullDiagramTransaction


def _instrument_symbol(label: str) -> dict[str, object]:
    return {
        "op": "add_element",
        "element": {
            "id": "standalone_pt",
            "type": "symbol",
            "symbol_key": "pressure_indicator",
            "position": {"x": 420, "y": 230},
            "width": 56,
            "height": 56,
            "label": label,
        },
    }


def _instrument_tap(label: str) -> dict[str, object]:
    return {
        "op": "instrument_tap",
        "main_connector_id": "main_pipe",
        "junction_point": {"x": 420, "y": 400},
        "measurement": "pressure",
        "instrument_label": label,
    }


def test_full_diagram_rejects_a_standalone_instrument_duplicated_by_instrument_tap():
    with pytest.raises(ValidationError, match="instrument_tap already creates"):
        FullDiagramTransaction.model_validate(
            {
                "operations": [
                    _instrument_symbol("PT-101"),
                    _instrument_tap("PT-101"),
                ]
            }
        )


def test_full_diagram_allows_distinct_instrument_labels():
    transaction = FullDiagramTransaction.model_validate(
        {
            "operations": [
                _instrument_symbol("PT-101A"),
                _instrument_tap("PT-101"),
            ]
        }
    )

    assert len(transaction.operations) == 2
