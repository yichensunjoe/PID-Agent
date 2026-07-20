import { useEffect, useState } from "react";
import type { CanvasView, NamedCanvasView, NavigationZone } from "./navigationViews";

type ViewNavigatorProps = {
  open: boolean;
  zones: NavigationZone[];
  currentZoneId?: string;
  namedViews: NamedCanvasView[];
  currentView: CanvasView | null;
  onClose: () => void;
  onOpenZone: (zone: NavigationZone) => void;
  onOpenNamedView: (view: NamedCanvasView) => void;
  onSaveNamedView: (name: string, view: CanvasView) => void;
  onRenameNamedView: (id: string, name: string) => void;
  onDeleteNamedView: (id: string) => void;
};

export function ViewNavigator({
  open,
  zones,
  currentZoneId,
  namedViews,
  currentView,
  onClose,
  onOpenZone,
  onOpenNamedView,
  onSaveNamedView,
  onRenameNamedView,
  onDeleteNamedView,
}: ViewNavigatorProps) {
  const [name, setName] = useState("");
  useEffect(() => {
    if (open) setName(`视图 ${namedViews.length + 1}`);
  }, [open, namedViews.length]);
  if (!open) return null;
  return <div className="view-navigator-backdrop" role="presentation" onPointerDown={onClose}>
    <section className="view-navigator" role="dialog" aria-modal="true" aria-label="大图视图导航" onPointerDown={(event) => event.stopPropagation()}>
      <header><div><strong>大图视图导航</strong><span>分区自动计算；命名视图仅保存在当前浏览器</span></div><button type="button" onClick={onClose}>关闭</button></header>
      <div className="view-navigator-body">
        <section><h3>自动分区</h3>{zones.length ? <div className="zone-grid">{zones.map((zone) => <button key={zone.id} type="button" className={currentZoneId === zone.id ? "active" : ""} onClick={() => onOpenZone(zone)}><strong>{zone.label}</strong><span>{zone.elementCount} 个元素</span></button>)}</div> : <p className="navigator-empty">当前文档没有可导航的可见元素。</p>}</section>
        <section><h3>命名视图</h3><div className="save-view-row"><input value={name} maxLength={80} onChange={(event) => setName(event.target.value)} placeholder="视图名称" /><button type="button" disabled={!currentView || !name.trim()} onClick={() => { if (currentView && name.trim()) onSaveNamedView(name.trim(), currentView); }}>保存当前视口</button></div>
          {namedViews.length ? <div className="named-view-list">{namedViews.map((view) => <article key={view.id}><button type="button" className="named-view-open" onClick={() => onOpenNamedView(view)}><strong>{view.name}</strong><span>{Math.round(view.view.width)} × {Math.round(view.view.height)}</span></button><button type="button" onClick={() => { const next = window.prompt("重命名视图", view.name)?.trim(); if (next) onRenameNamedView(view.id, next); }}>改名</button><button type="button" className="danger" onClick={() => onDeleteNamedView(view.id)}>删除</button></article>)}</div> : <p className="navigator-empty">尚未保存命名视图。</p>}
        </section>
      </div>
    </section>
  </div>;
}
