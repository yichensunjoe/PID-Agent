import { useState, useRef, useEffect } from "react";
import { useWorkspace } from "../store";
import { SYMBOL_DRAG_MIME } from "./shapeVarieties";
import type { SymbolDefinition, SymbolShape } from "../types";

function Shape({ shape }: { shape: SymbolShape }) {
  if (shape.type === "line") {
    return <line x1={shape.x1} y1={shape.y1} x2={shape.x2} y2={shape.y2} />;
  }
  if (shape.type === "polyline") {
    const points = shape.points.map((point) => point.join(",")).join(" ");
    return shape.closed ? <polygon points={points} /> : <polyline points={points} />;
  }
  if (shape.type === "rect") {
    return <rect x={shape.x} y={shape.y} width={shape.width} height={shape.height} rx={shape.rx ?? 0} />;
  }
  if (shape.type === "circle") {
    return <circle cx={shape.cx} cy={shape.cy} r={shape.r} />;
  }
  if (shape.type === "path") return <path d={shape.d} />;
  return (
    <text x={shape.x} y={shape.y} fontSize={shape.font_size ?? 10} textAnchor="middle">
      {shape.text}
    </text>
  );
}

type BasicGroup = {
  name: string;
  keys: string[];
};

const BASIC_GROUPS: BasicGroup[] = [
  {
    name: "几何逻辑",
    keys: ["revision_cloud", "hexagon_tag", "octagon_box", "diamond_decision", "parallelogram_io"],
  },
  {
    name: "设备容器",
    keys: ["cylinder_vessel", "cube_cabinet", "trapezoid_hopper"],
  },
  {
    name: "标注流向",
    keys: ["callout_bubble", "block_arrow_right"],
  },
  {
    name: "管道附件",
    keys: ["spectacle_blind_open", "spectacle_blind_closed", "flame_arrester", "sight_glass"],
  },
];

export function BasicShapesToolbar() {
  const [open, setOpen] = useState(false);
  const [activeGroup, setActiveGroup] = useState(BASIC_GROUPS[0].name);
  const menuRef = useRef<HTMLDivElement>(null);
  const symbols = useWorkspace((state) => state.symbols);
  const chooseSymbol = useWorkspace((state) => state.chooseSymbol);
  const selectedSymbolKey = useWorkspace((state) => state.selectedSymbolKey);

  const symbolMap = new Map<string, SymbolDefinition>(
    symbols.map((symbol) => [symbol.key, symbol]),
  );

  useEffect(() => {
    if (!open) return;
    const handleClickOutside = (event: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside, true);
    return () => document.removeEventListener("mousedown", handleClickOutside, true);
  }, [open]);

  const currentGroup = BASIC_GROUPS.find((g) => g.name === activeGroup) ?? BASIC_GROUPS[0];
  const groupSymbols = currentGroup.keys
    .map((k) => symbolMap.get(k))
    .filter((s): s is SymbolDefinition => Boolean(s));

  return (
    <div className="basic-shapes-toolbar-wrapper" ref={menuRef}>
      <button
        type="button"
        className={`tool-icon basic-shapes-btn ${open ? "active" : ""}`}
        onClick={() => setOpen(!open)}
        title="基础图元（可直接拖拽至下方画布）"
      >
        <span style={{ fontSize: 13, marginRight: 2 }}>📐</span>
        <span style={{ fontSize: 11, fontWeight: 500 }}>基础图元</span>
        <span style={{ fontSize: 9, marginLeft: 3, opacity: 0.7 }}>{open ? "▲" : "▼"}</span>
      </button>

      {open ? (
        <div className="basic-shapes-dropdown">
          <div className="basic-shapes-tabs">
            {BASIC_GROUPS.map((group) => (
              <button
                key={group.name}
                type="button"
                className={`basic-tab-btn ${activeGroup === group.name ? "active" : ""}`}
                onClick={() => setActiveGroup(group.name)}
              >
                {group.name}
              </button>
            ))}
          </div>

          <div className="basic-shapes-grid">
            {groupSymbols.map((symbol) => {
              const isSelected = selectedSymbolKey === symbol.key;
              return (
                <div
                  key={symbol.key}
                  className={`basic-shape-card ${isSelected ? "selected" : ""}`}
                  draggable
                  onDragStart={(event) => {
                    event.dataTransfer.setData(SYMBOL_DRAG_MIME, symbol.key);
                    event.dataTransfer.effectAllowed = "copy";
                    setOpen(false);
                  }}
                  onClick={() => {
                    chooseSymbol(symbol.key);
                    setOpen(false);
                  }}
                  title={`${symbol.name} - ${symbol.description}（拖拽到画布或点击放置）`}
                >
                  <svg viewBox={`0 0 ${symbol.width} ${symbol.height}`} className="basic-shape-svg">
                    <g fill="none" stroke="currentColor" strokeWidth="1.5">
                      {symbol.shapes.map((shape, idx) => (
                        <Shape key={idx} shape={shape} />
                      ))}
                    </g>
                  </svg>
                  <span className="basic-shape-label">{symbol.name}</span>
                </div>
              );
            })}
          </div>
          <div className="basic-shapes-footer">
            💡 支持直接拖拽至下方画布，免属性录入
          </div>
        </div>
      ) : null}
    </div>
  );
}
