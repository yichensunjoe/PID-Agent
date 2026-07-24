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

function SymbolCard({ symbol }: { symbol: SymbolDefinition }) {
  const chooseSymbol = useWorkspace((state) => state.chooseSymbol);
  const selected = useWorkspace((state) => state.selectedSymbolKey === symbol.key);
  return (
    <button
      className={`symbol-card ${selected ? "is-selected" : ""}`}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.setData(SYMBOL_DRAG_MIME, symbol.key);
        event.dataTransfer.effectAllowed = "copy";
      }}
      onClick={() => chooseSymbol(symbol.key)}
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

export function SymbolPalette() {
  const symbols = useWorkspace((state) => state.symbols);
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("");
  const categoryOptions = useMemo(() => orderedSymbolCategories(symbols), [symbols]);
  const filtered = useMemo(
    () => filterSymbolCatalog(symbols, query, category),
    [category, query, symbols],
  );
  const categories = useMemo(() => {
    const result = new Map<string, SymbolDefinition[]>();
    for (const categoryName of orderedSymbolCategories(filtered)) result.set(categoryName, []);
    for (const symbol of filtered) result.get(symbol.category)?.push(symbol);
    return result;
  }, [filtered]);

  return (
    <div className="symbol-palette">
      <div className="symbol-catalog-tools">
        <input
          type="search"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="搜索名称、类别或 key"
          aria-label="搜索单位图例"
        />
        <select
          value={category}
          onChange={(event) => setCategory(event.target.value)}
          aria-label="筛选图例分类"
        >
          <option value="">全部分类</option>
          {categoryOptions.map((item) => <option key={item} value={item}>{item}</option>)}
        </select>
        <span>{filtered.length} / {symbols.length} 个标准图例</span>
      </div>
      {[...categories.entries()].map(([category, items]) => (
        <section key={category}>
          <h3><span>{category}</span><small>{items.length}</small></h3>
          <div className="symbol-grid">
            {items.map((symbol) => (
              <SymbolCard key={symbol.key} symbol={symbol} />
            ))}
          </div>
        </section>
      ))}
      {!filtered.length ? <div className="symbol-empty">没有匹配的图例</div> : null}
    </div>
  );
}
