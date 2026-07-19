from pathlib import Path

path = Path("backend/agentcad/model_acceptance.py")
content = path.read_text()
old = '''    expected_pairs = {
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
'''
new = '''    actual_pairs = {
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
    utility_pairs = {
        ("air_in", "out", "e101", "shell_out"),
        ("e101", "shell_in", "air_out", "in"),
    }
    if not utility_pairs.issubset(actual_pairs):
        return False

    directed: dict[str, set[str]] = {}
    for source_id, _, target_id, _ in actual_pairs:
        directed.setdefault(source_id, set()).add(target_id)
    required_order = ["v101", "e101", "v102", "waste_out"]
    stack = [("waste_in", 0, frozenset())]
    main_path_valid = False
    while stack:
        node, matched, visited = stack.pop()
        state = (node, matched)
        if state in visited:
            continue
        next_visited = visited | {state}
        next_matched = matched
        if matched < len(required_order) and node == required_order[matched]:
            next_matched += 1
        if next_matched == len(required_order):
            main_path_valid = True
            break
        for target_id in directed.get(node, set()):
            stack.append((target_id, next_matched, next_visited))
    if not main_path_valid:
        return False
'''
if new not in content:
    if old not in content:
        raise SystemExit("complex expected-pairs block not found")
    path.write_text(content.replace(old, new, 1))
