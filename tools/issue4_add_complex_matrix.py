from pathlib import Path


def replace(path_name: str, old: str, new: str) -> None:
    path = Path(path_name)
    content = path.read_text()
    if new in content:
        return
    if old not in content:
        raise SystemExit(f"marker not found in {path_name}: {old[:120]!r}")
    path.write_text(content.replace(old, new, 1))


replace(
    "backend/agentcad/model_acceptance.py",
    "from .agent_semantic_models import SemanticAgentReplanRequest\n",
    "from .agent_semantic_models import SemanticAgentReplanRequest\n"
    "from .annotation_layout import measure_annotation_quality, normalize_annotation_text\n",
)
replace(
    "backend/agentcad/model_acceptance.py",
    "    max_replans: int = Field(default=3, ge=0, le=5)\n",
    "    max_replans: int = Field(default=3, ge=0, le=5)\n"
    "    include_complex_diagram: bool = False\n",
)
replace(
    "backend/agentcad/model_acceptance.py",
    "def _scenario(name: str, primary, replacement) -> tuple[str, Any]:\n",
    '''def _complex_diagram_check(document, symbols: SymbolRegistry) -> bool:
    elements = {element.id: element for element in document.elements}
    required = {
        "waste_in",
        "v101",
        "e101",
        "v102",
        "waste_out",
        "air_in",
        "air_out",
        "j_pt101",
        "j_te101",
        "j_pt102",
        "j_te102",
        "pt101",
        "te101",
        "pt102",
        "te102",
    }
    if not required.issubset(elements):
        return False
    if not 30 <= len(document.elements) <= 50:
        return False
    for instrument_id, label in {
        "pt101": "PT-101",
        "te101": "TE-101",
        "pt102": "PT-102",
        "te102": "TE-102",
    }.items():
        element = elements[instrument_id]
        if element.type != "symbol" or element.label:
            return False
        labels = [
            item
            for item in document.elements
            if item.type == "text"
            and item.metadata.get("parent_element_id") == instrument_id
            and item.text == label
        ]
        if len(labels) != 1:
            return False

    connectors = [element for element in document.elements if element.type == "connector"]
    junction_ids = {"j_pt101", "j_te101", "j_pt102", "j_te102"}
    for junction_id in junction_ids:
        bound = sum(
            1
            for connector in connectors
            for endpoint in (connector.source, connector.target)
            if endpoint
            and endpoint.element_id == junction_id
            and endpoint.port_id == "node"
        )
        if bound < 3:
            return False

    expected_pairs = {
        ("waste_in", "out", "v101", "in"),
        ("v101", "out", "e101", "tube_in"),
        ("e101", "tube_out", "v102", "in"),
        ("v102", "out", "waste_out", "in"),
        ("air_in", "out", "e101", "shell_out"),
        ("e101", "shell_in", "air_out", "in"),
    }
    actual_pairs = {
        (
            connector.source.element_id,
            connector.source.port_id,
            connector.target.element_id,
            connector.target.port_id,
        )
        for connector in connectors
        if connector.source
        and connector.target
        and connector.source.element_id
        and connector.target.element_id
    }
    if not expected_pairs.issubset(actual_pairs):
        return False

    quality = measure_annotation_quality(document, symbols)
    if any(
        (
            quality.duplicate_label_count,
            quality.text_text_overlaps,
            quality.text_symbol_overlaps,
            quality.text_connector_intersections,
        )
    ):
        return False
    normalized_labels = [
        normalize_annotation_text(item.text)
        for item in document.elements
        if item.type == "text" and item.text.strip()
    ]
    return len(normalized_labels) == len(set(normalized_labels))


def _scenario(name: str, primary, replacement, symbols: SymbolRegistry) -> tuple[str, Any]:
    if name == "complex_full_diagram":
        prompt = (
            "生成复杂冷凝流程图：上游废气接口经 V-101、E-101、V-102 到尾气处理接口；"
            "E-101 上下游分别建立 PT 和 TE instrument_tap，共四个真实 junction；"
            "增加使用 E-101 shell_in/shell_out 的冷却空气线路；添加工艺说明文字。"
            "使用给定固定 element id，保持正交连接并避免重复标签。"
        )
        return prompt, lambda document: _complex_diagram_check(document, symbols)
''',
)
replace(
    "backend/agentcad/model_acceptance.py",
    "            document, primary, replacement = _seed(service, symbols)\n",
    '''            if scenario == "complex_full_diagram":
                primary, replacement = _symbol_choices(symbols)
                document = service.create_document(
                    CreateDocumentRequest(name="Complex full diagram acceptance"),
                    source="system",
                )
            else:
                document, primary, replacement = _seed(service, symbols)
''',
)
replace(
    "backend/agentcad/model_acceptance.py",
    "            prompt, check = _scenario(scenario, primary, replacement)\n",
    "            prompt, check = _scenario(scenario, primary, replacement, symbols)\n",
)
replace(
    "backend/agentcad/model_acceptance.py",
    '    scenarios = ["add_connect", "move", "replace", "reconnect", "delete"]\n',
    '''    scenarios = ["add_connect", "move", "replace", "reconnect", "delete"]
    if request.include_complex_diagram:
        scenarios.append("complex_full_diagram")
''',
)
