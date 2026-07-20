from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_editor_workspace_preferences_are_local_and_revision_free():
    preferences = (ROOT / "frontend/src/editorPreferences.ts").read_text(encoding="utf-8")
    controls = (ROOT / "frontend/src/editor/WorkspaceControls.tsx").read_text(encoding="utf-8")

    assert 'pid-agent.editor-preferences.v1' in preferences
    assert 'canvasMode: "infinite"' in preferences
    assert "gridEnabled: true" in preferences
    assert "localStorage.setItem" in preferences
    assert "transact" not in controls
    assert "不增加工程文档 revision" in controls


def test_editor_canvas_separates_workspace_background_from_page_and_grid_snap():
    editor = (ROOT / "frontend/src/editor/EditorCanvas.tsx").read_text(encoding="utf-8")

    assert "useEditorPreferences" in editor
    assert 'canvasMode === "infinite"' in editor
    assert "view.x - view.width" in editor
    assert "view.width * 3" in editor
    assert "gridEnabled ? snapToGrid(point) : point" in editor
    assert "hit ? { point: hit.point, hit } : { point: applyGrid(raw)" in editor
    assert 'data-workspace-mode={canvasMode}' in editor
    assert 'data-grid-enabled={gridEnabled}' in editor
    assert 'canvasMode === "page" ? <rect' in editor
