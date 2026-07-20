import { useWorkspace } from "../store";
import type { Layer, Operation, SystemGroup } from "../types";
import { ExportPanel } from "./ExportPanel";
import { LayoutPanel } from "./LayoutPanel";
import { WorkspaceControls } from "./WorkspaceControls";

const newGroupId = (prefix: "layer" | "system") =>
  `${prefix}_${crypto.randomUUID().replaceAll("-", "").slice(0, 10)}`;

export function LayerSystemPanel() {
  const document = useWorkspace((state) => state.document);
  const selectedElementIds = useWorkspace((state) => state.selectedElementIds);
  const transact = useWorkspace((state) => state.transact);
  const isMutating = useWorkspace((state) => state.isMutating);

  if (!document) return <div className="inspector-empty">没有打开的文档</div>;

  const addLayer = async () => {
    const name = window.prompt("新图层名称", "新图层")?.trim();
    if (!name) return;
    const layer: Layer = { id: newGroupId("layer"), name, visible: true, locked: false };
    await transact([{ op: "add_layer", layer }], `Add layer ${name}`);
  };

  const addSystem = async () => {
    const name = window.prompt("新系统名称", "新系统")?.trim();
    if (!name) return;
    const system: SystemGroup = { id: newGroupId("system"), name, visible: true };
    await transact([{ op: "add_system", system }], `Add system ${name}`);
  };

  const renameLayer = async (layer: Layer) => {
    const name = window.prompt("图层名称", layer.name)?.trim();
    if (!name || name === layer.name) return;
    await transact([{ op: "update_layer", layer_id: layer.id, patch: { name } }], `Rename layer ${layer.id}`);
  };

  const renameSystem = async (system: SystemGroup) => {
    const name = window.prompt("系统名称", system.name)?.trim();
    if (!name || name === system.name) return;
    await transact([{ op: "update_system", system_id: system.id, patch: { name } }], `Rename system ${system.id}`);
  };

  const assignLayer = async (layerId: string) => {
    if (!selectedElementIds.length) return;
    const operations: Operation[] = selectedElementIds.map((element_id) => ({
      op: "update_element",
      element_id,
      patch: { layer_id: layerId },
    }));
    await transact(operations, `Move ${operations.length} element(s) to layer ${layerId}`);
  };

  const assignSystem = async (systemId: string) => {
    if (!selectedElementIds.length) return;
    const operations: Operation[] = selectedElementIds.map((element_id) => ({
      op: "update_element",
      element_id,
      patch: { system_id: systemId },
    }));
    await transact(operations, `Move ${operations.length} element(s) to system ${systemId}`);
  };

  const countLayer = (id: string) => document.elements.filter((item) => item.layer_id === id).length;
  const countSystem = (id: string) => document.elements.filter((item) => item.system_id === id).length;

  return (
    <div className="group-manager">
      <section>
        <div className="group-manager-heading"><h3>图层</h3><button onClick={() => void addLayer()}>新增</button></div>
        <div className="group-list">
          {document.layers.map((layer) => (
            <div className="group-row" key={layer.id}>
              <button
                className={layer.visible ? "visibility-toggle active" : "visibility-toggle"}
                title={layer.visible ? "隐藏图层" : "显示图层"}
                onClick={() => void transact([{ op: "update_layer", layer_id: layer.id, patch: { visible: !layer.visible } }], `${layer.visible ? "Hide" : "Show"} layer ${layer.name}`)}
              >{layer.visible ? "●" : "○"}</button>
              <button className="group-name" onDoubleClick={() => void renameLayer(layer)} onClick={() => void assignLayer(layer.id)} disabled={isMutating}>
                <strong>{layer.name}</strong><span>{countLayer(layer.id)} 个元素</span>
              </button>
              <button
                className={layer.locked ? "lock-toggle active" : "lock-toggle"}
                title={layer.locked ? "解锁" : "锁定"}
                onClick={() => void transact([{ op: "update_layer", layer_id: layer.id, patch: { locked: !layer.locked } }], `${layer.locked ? "Unlock" : "Lock"} layer ${layer.name}`)}
              >{layer.locked ? "锁" : "开"}</button>
              <button
                className="group-delete"
                disabled={layer.id === "layer_default" || isMutating}
                title="删除后元素移入默认图层"
                onClick={() => {
                  if (window.confirm(`删除图层“${layer.name}”？其中元素将移入默认图层。`)) {
                    void transact([{ op: "delete_layer", layer_id: layer.id, move_elements_to: "layer_default" }], `Delete layer ${layer.name}`);
                  }
                }}
              >×</button>
            </div>
          ))}
        </div>
        <p className="group-hint">单击图层名称：把当前选择移入该图层；双击：重命名。</p>
      </section>

      <section>
        <div className="group-manager-heading"><h3>工艺系统</h3><button onClick={() => void addSystem()}>新增</button></div>
        <div className="group-list">
          {document.systems.map((system) => (
            <div className="group-row system-row" key={system.id}>
              <button
                className={system.visible ? "visibility-toggle active" : "visibility-toggle"}
                title={system.visible ? "隐藏系统" : "显示系统"}
                onClick={() => void transact([{ op: "update_system", system_id: system.id, patch: { visible: !system.visible } }], `${system.visible ? "Hide" : "Show"} system ${system.name}`)}
              >{system.visible ? "●" : "○"}</button>
              <button className="group-name" onDoubleClick={() => void renameSystem(system)} onClick={() => void assignSystem(system.id)} disabled={isMutating}>
                <strong>{system.name}</strong><span>{countSystem(system.id)} 个元素</span>
              </button>
              <button
                className="group-delete"
                disabled={system.id === "system_default" || isMutating}
                title="删除后元素移入默认系统"
                onClick={() => {
                  if (window.confirm(`删除系统“${system.name}”？其中元素将移入默认系统。`)) {
                    void transact([{ op: "delete_system", system_id: system.id, move_elements_to: "system_default" }], `Delete system ${system.name}`);
                  }
                }}
              >×</button>
            </div>
          ))}
        </div>
        <p className="group-hint">系统显隐同时影响网页画布和 SVG/PNG 导出。</p>
      </section>

      <section className="layout-manager-section">
        <div className="group-manager-heading"><h3>画布与定位</h3></div>
        <WorkspaceControls />
      </section>

      <section className="layout-manager-section">
        <div className="group-manager-heading"><h3>自动整理</h3></div>
        <LayoutPanel />
      </section>

      <ExportPanel />
    </div>
  );
}
