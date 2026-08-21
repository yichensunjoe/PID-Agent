import { useMemo, useState } from "react";
import type { SymbolDefinition, SymbolShape } from "../types";
import { useWorkspace } from "../store";
import { SYMBOL_DRAG_MIME } from "./shapeVarieties";
import { filterSymbolCatalog, orderedSymbolCategories } from "./symbolCatalog";

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
    <text x={shape.x} y={shape.y} fontSize={shape.font_size ?? 12} textAnchor="middle">
      {shape.text}
    </text>
  );
}

function SymbolCard({
  symbol,
  onHover,
}: {
  symbol: SymbolDefinition;
  onHover: (symbol: SymbolDefinition | null, targetRect: DOMRect | null) => void;
}) {
  const chooseSymbol = useWorkspace((state) => state.chooseSymbol);
  const selected = useWorkspace((state) => state.selectedSymbolKey === symbol.key);
  return (
    <button
      className={`symbol-card ${selected ? "is-selected" : ""}`}
      draggable
      onDragStart={(event) => {
        onHover(null, null);
        event.dataTransfer.setData(SYMBOL_DRAG_MIME, symbol.key);
        event.dataTransfer.effectAllowed = "copy";
      }}
      onClick={() => chooseSymbol(symbol.key)}
      onMouseEnter={(event) => onHover(symbol, event.currentTarget.getBoundingClientRect())}
      onMouseLeave={() => onHover(null, null)}
      title={`${symbol.description}（点击选择或拖到画布）`}
    >
      <svg viewBox={`0 0 ${symbol.width} ${symbol.height}`} aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth="1.5">
          {symbol.shapes.map((shape, index) => (
            <Shape key={index} shape={shape} />
          ))}
        </g>
      </svg>
      <span>{symbol.name}</span>
      <small>{symbol.key}</small>
    </button>
  );
}

function SymbolDetailPopover({
  symbol,
  targetRect,
}: {
  symbol: SymbolDefinition;
  targetRect: DOMRect;
}) {
  const top = Math.max(12, Math.min(window.innerHeight - 340, targetRect.top - 20));
  const left = Math.min(window.innerWidth - 300, targetRect.right + 12);

  return (
    <div
      className="symbol-detail-popover"
      style={{ top: `${top}px`, left: `${left}px` }}
      role="tooltip"
    >
      <div className="symbol-popover-header">
        <div className="symbol-popover-title-row">
          <strong>{symbol.name}</strong>
          <span className="symbol-popover-badge">{symbol.category}</span>
        </div>
        <code>{symbol.key}</code>
      </div>
      <div className="symbol-popover-preview">
        <svg viewBox={`0 0 ${symbol.width} ${symbol.height}`} aria-hidden="true">
          <g fill="none" stroke="currentColor" strokeWidth="1.75">
            {symbol.shapes.map((shape, index) => (
              <Shape key={index} shape={shape} />
            ))}
          </g>
          {symbol.ports.map((port) => (
            <circle
              key={port.id}
              cx={port.x}
              cy={port.y}
              r={3}
              fill={port.direction === "in" ? "#2563eb" : port.direction === "out" ? "#16a34a" : "#ea580c"}
              stroke="#ffffff"
              strokeWidth={1}
            />
          ))}
        </svg>
      </div>
      <div className="symbol-popover-meta">
        <div><span>尺寸</span><strong>{symbol.width} × {symbol.height} px</strong></div>
        <div><span>端口数</span><strong>{symbol.ports.length} 个</strong></div>
      </div>
      {symbol.description ? <p className="symbol-popover-desc">{symbol.description}</p> : null}
      {symbol.ports.length ? (
        <div className="symbol-popover-ports">
          <span className="ports-title">引脚端口定义：</span>
          <div className="ports-list">
            {symbol.ports.map((port) => (
              <div key={port.id} className="port-item">
                <span className={`port-dir ${port.direction}`}>{port.direction === "in" ? "进" : port.direction === "out" ? "出" : "双向"}</span>
                <code>{port.id}</code>
                <span>{port.name || port.id}</span>
                {port.medium ? <small>({port.medium})</small> : null}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      <div className="symbol-popover-footer">
        <span>💡 点击选择插入，或直接拖拽至画布放置</span>
      </div>
    </div>
  );
}

export function SymbolPalette() {
  const symbols = useWorkspace((state) => state.symbols);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const [hovered, setHovered] = useState<{ symbol: SymbolDefinition; rect: DOMRect } | null>(null);

  // Exclude "基础图元" from bottom-left palette as they are placed in the top toolbar
  const paletteSymbols = useMemo(
    () => symbols.filter((s) => s.category !== "基础图元"),
    [symbols],
  );

  const categoryOptions = useMemo(() => orderedSymbolCategories(paletteSymbols), [paletteSymbols]);
  const filtered = useMemo(
    () => filterSymbolCatalog(paletteSymbols, query, category),
    [category, paletteSymbols, query],
  );
  const categories = useMemo(() => {
    const result = new Map<string, SymbolDefinition[]>();
    for (const categoryName of orderedSymbolCategories(filtered)) result.set(categoryName, []);
    for (const symbol of filtered) result.get(symbol.category)?.push(symbol);
    return result;
  }, [filtered]);

  const handleHover = (symbol: SymbolDefinition | null, rect: DOMRect | null) => {
    if (symbol && rect) {
      setHovered({ symbol, rect });
    } else {
      setHovered(null);
    }
  };

  return (
    <div className="symbol-palette">
      <div className="symbol-catalog-tools">
        <div className="symbol-search-container">
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="搜索名称、类别或 key"
            aria-label="搜索单位图例"
          />
          {query ? (
            <button
              type="button"
              className="symbol-search-clear"
              onClick={() => setQuery("")}
              aria-label="清空搜索"
            >
              ✕
            </button>
          ) : null}
        </div>
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="筛选图例分类"
        >
          <option value="">全部分类</option>
          {categoryOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <span>{filtered.length} / {paletteSymbols.length} 个标准图例</span>
      </div>
      {[...categories.entries()].map(([category, items]) => (
        <section key={category}>
          <h3><span>{category}</span><small>{items.length}</small></h3>
          <div className="symbol-grid">
            {items.map((symbol) => (
              <SymbolCard key={symbol.key} symbol={symbol} onHover={handleHover} />
            ))}
          </div>
        </section>
      ))}
      {!filtered.length ? <div className="symbol-empty">没有匹配的图例</div> : null}
      {hovered ? <SymbolDetailPopover symbol={hovered.symbol} targetRect={hovered.rect} /> : null}
    </div>
  );
}
