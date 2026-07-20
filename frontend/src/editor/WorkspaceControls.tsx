import {
  setCanvasMode,
  setGridEnabled,
  useEditorPreferences,
} from "../editorPreferences";

export function WorkspaceControls() {
  const preferences = useEditorPreferences();

  return (
    <div className="workspace-controls">
      <div className="workspace-control-row">
        <span>工作区</span>
        <div className="workspace-control-buttons">
          <button
            type="button"
            className={preferences.canvasMode === "infinite" ? "active" : ""}
            onClick={() => setCanvasMode("infinite")}
            title="允许图形超出固定页面，并在当前视口持续绘制背景"
          >无限</button>
          <button
            type="button"
            className={preferences.canvasMode === "page" ? "active" : ""}
            onClick={() => setCanvasMode("page")}
            title="显示固定文档页面边界"
          >页面</button>
        </div>
      </div>
      <div className="workspace-control-row">
        <span>定位</span>
        <div className="workspace-control-buttons">
          <button
            type="button"
            className={preferences.gridEnabled ? "active" : ""}
            onClick={() => setGridEnabled(true)}
            title="显示网格并把绘制、拖动和折线调整吸附到网格"
          >网格吸附</button>
          <button
            type="button"
            className={!preferences.gridEnabled ? "active" : ""}
            onClick={() => setGridEnabled(false)}
            title="隐藏网格并使用自由坐标；端口和管线命中仍会吸附"
          >自由</button>
        </div>
      </div>
      <p className="group-hint">编辑器偏好保存在当前浏览器，不增加工程文档 revision。无限模式不改变固定页面导出；超页内容可用“内容范围”导出。</p>
    </div>
  );
}
