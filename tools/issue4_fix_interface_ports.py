from pathlib import Path


def replace(path_name: str, old: str, new: str) -> None:
    path = Path(path_name)
    content = path.read_text()
    if new in content:
        return
    if old not in content:
        raise SystemExit(f"marker not found in {path_name}: {old!r}")
    path.write_text(content.replace(old, new))


replace(
    "backend/tests/test_complex_diagram_matrix.py",
    'source_element_id="waste_in",\n            source_port_id="out",',
    'source_element_id="waste_in",\n            source_port_id="right",',
)
replace(
    "backend/tests/test_complex_diagram_matrix.py",
    'target_element_id="waste_out",\n            target_port_id="in",',
    'target_element_id="waste_out",\n            target_port_id="left",',
)
replace(
    "backend/tests/test_complex_diagram_matrix.py",
    'source_element_id="air_in",\n            source_port_id="out",',
    'source_element_id="air_in",\n            source_port_id="left",',
)
replace(
    "backend/tests/test_complex_diagram_matrix.py",
    'target_element_id="air_out",\n            target_port_id="in",',
    'target_element_id="air_out",\n            target_port_id="right",',
)
replace(
    "backend/agentcad/model_acceptance.py",
    '("air_in", "out", "e101", "shell_out"),',
    '("air_in", "left", "e101", "shell_out"),',
)
replace(
    "backend/agentcad/model_acceptance.py",
    '("e101", "shell_in", "air_out", "in"),',
    '("e101", "shell_in", "air_out", "right"),',
)
