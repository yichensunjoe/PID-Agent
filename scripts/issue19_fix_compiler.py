from pathlib import Path

path = Path("backend/agentcad/semantic_compiler_engine.py")
text = path.read_text(encoding="utf-8")
old_normalize = '''    def _normalize_waypoint_connector(
        cls,
        compiled: list[Operation],
        operation: ConnectPortsOperation,
    ) -> list[Operation]:
'''
new_normalize = '''    def _normalize_waypoint_connector(
        cls,
        compiled: list[Operation],
        operation: ConnectPortsOperation,
        grid_size: float,
    ) -> list[Operation]:
'''
old_semantics = '''    def _apply_connector_semantics(
        compiled: list[Operation],
        operation: ConnectPortsOperation,
        grid_size: float,
    ) -> list[Operation]:
'''
new_semantics = '''    def _apply_connector_semantics(
        compiled: list[Operation],
        operation: ConnectPortsOperation,
    ) -> list[Operation]:
'''
for old, new in ((old_normalize, new_normalize), (old_semantics, new_semantics)):
    if text.count(old) != 1:
        raise RuntimeError(f"expected one compiler signature match, found {text.count(old)}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
