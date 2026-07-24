import assert from "node:assert/strict";
import test from "node:test";
import type { SymbolDefinition } from "../src/types.ts";
import {
  filterSymbolCatalog,
  orderedSymbolCategories,
  symbolMatchesQuery,
} from "../src/editor/symbolCatalog.ts";

function symbol(key: string, name: string, category: string, description = ""): SymbolDefinition {
  return {
    key,
    name,
    category,
    description,
    width: 60,
    height: 40,
    ports: [],
    shapes: [],
  };
}

const symbols = [
  symbol("centrifugal_pump", "离心泵", "泵", "工艺流体输送"),
  symbol("safety_relief_valve", "安全泄放阀", "阀门", "超压保护"),
  symbol("basket_strainer", "篮式过滤器", "过滤设备", "入口粗过滤"),
];

test("symbol catalog searches Chinese names, stable keys, categories and descriptions", () => {
  assert.equal(symbolMatchesQuery(symbols[0], "离心"), true);
  assert.equal(symbolMatchesQuery(symbols[0], "centrifugal pump"), true);
  assert.equal(symbolMatchesQuery(symbols[1], "超压 阀门"), true);
  assert.equal(filterSymbolCatalog(symbols, "过滤", "过滤设备")[0]?.key, "basket_strainer");
});

test("symbol categories use engineering workflow order before unknown categories", () => {
  assert.deepEqual(orderedSymbolCategories(symbols), ["阀门", "泵", "过滤设备"]);
  assert.deepEqual(
    orderedSymbolCategories([...symbols, symbol("custom", "自定义", "企业专用")]),
    ["阀门", "泵", "过滤设备", "企业专用"],
  );
});
