from pathlib import Path

root = Path(__file__).resolve().parents[1]
editor = root / "frontend/src/editor/EditorCanvas.tsx"
workflow = root / ".github/workflows/fix-endpoint-release.yml"
text = editor.read_text(encoding="utf-8")

old_move = '''    if (endpointDrag) {
      const excluded = endpointDrag.endpoint === "source" ? endpointDrag.connector.source ?? undefined : endpointDrag.connector.target ?? undefined;
      const snapped = connectorPointFromEvent(event, excluded);
      setEndpointDrag({ ...endpointDrag, current: snapped.point, activeConnection: snapped.hit });
      return;
    }'''
new_move = '''    if (endpointDrag) {
      const snapped = connectorPointFromEvent(event);
      setEndpointDrag({ ...endpointDrag, current: snapped.point, activeConnection: snapped.hit });
      return;
    }'''
old_up = '''    if (endpointDrag) {
      const existing = endpointDrag.endpoint === "source" ? endpointDrag.connector.source ?? undefined : endpointDrag.connector.target ?? undefined;
      const released = connectorPointFromEvent(event, existing);
      const endpoint = released.hit ? endpointFromHit(released.hit) : { point: released.point };'''
new_up = '''    if (endpointDrag) {
      const released = connectorPointFromEvent(event);
      const endpoint = released.hit ? endpointFromHit(released.hit) : { point: released.point };'''
for label, old, new in [("move", old_move, new_move), ("up", old_up, new_up)]:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one match, found {text.count(old)}")
    text = text.replace(old, new, 1)
editor.write_text(text, encoding="utf-8")
Path(__file__).unlink()
workflow.unlink()
