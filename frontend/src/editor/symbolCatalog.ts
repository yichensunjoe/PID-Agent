import type { SymbolDefinition } from "../types";

const CATEGORY_ORDER = [
  "阀门",
  "安全附件",
  "泵",
  "风机",
  "换热设备",
  "容器",
  "过滤设备",
  "混合设备",
  "工艺设备",
  "仪表",
  "管件",
  "管道附件",
  "排放与边界",
  "排放与安全",
  "边界",
];

function normalized(value: string): string {
  return value.trim().toLocaleLowerCase();
}

export function symbolMatchesQuery(symbol: SymbolDefinition, query: string): boolean {
  const search = normalized(query);
  if (!search) return true;
  const searchable = normalized([
    symbol.name,
    symbol.key,
    symbol.category,
    symbol.description,
  ].join(" "));
  return search.split(/\s+/).every((token) => searchable.includes(token));
}

export function filterSymbolCatalog(
  symbols: SymbolDefinition[],
  query: string,
  category: string,
): SymbolDefinition[] {
  return symbols.filter((symbol) => (
    (!category || symbol.category === category)
    && symbolMatchesQuery(symbol, query)
  ));
}

export function orderedSymbolCategories(symbols: SymbolDefinition[]): string[] {
  const categories = [...new Set(symbols.map((symbol) => symbol.category))];
  return categories.sort((left, right) => {
    const leftIndex = CATEGORY_ORDER.indexOf(left);
    const rightIndex = CATEGORY_ORDER.indexOf(right);
    if (leftIndex >= 0 || rightIndex >= 0) {
      if (leftIndex < 0) return 1;
      if (rightIndex < 0) return -1;
      return leftIndex - rightIndex;
    }
    return left.localeCompare(right, "zh-CN");
  });
}
