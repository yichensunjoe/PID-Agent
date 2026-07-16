import type { SymbolDefinition, SymbolShape } from "../types";
import { useWorkspace } from "../store";

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
      onClick={() => chooseSymbol(symbol.key)}
      title={symbol.description}
    >
      <svg viewBox={`0 0 ${symbol.width} ${symbol.height}`} aria-hidden="true">
        <g fill="none" stroke="currentColor" strokeWidth="1.5">
          {symbol.shapes.map((shape, index) => (
            <Shape key={index} shape={shape} />
          ))}
        </g>
      </svg>
      <span>{symbol.name}</span>
    </button>
  );
}

export function SymbolPalette() {
  const symbols = useWorkspace((state) => state.symbols);
  const categories = symbols.reduce<Map<string, SymbolDefinition[]>>((result, symbol) => {
    const items = result.get(symbol.category) ?? [];
    items.push(symbol);
    result.set(symbol.category, items);
    return result;
  }, new Map());
  return (
    <div className="symbol-palette">
      {[...categories.entries()].map(([category, items]) => (
        <section key={category}>
          <h3>{category}</h3>
          <div className="symbol-grid">
            {items.map((symbol) => (
              <SymbolCard key={symbol.key} symbol={symbol} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
