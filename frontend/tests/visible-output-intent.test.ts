import assert from "node:assert/strict";
import test from "node:test";
import { shouldRequireVisibleOutput } from "../src/agent/visibleOutputIntent.ts";

test("visible output requirement is conservative and only applies to empty drawings", () => {
  assert.equal(shouldRequireVisibleOutput("生成一张泵和储罐连接的 P&ID", 0), true);
  assert.equal(shouldRequireVisibleOutput("只新增一个公用工程图层", 0), false);
  assert.equal(shouldRequireVisibleOutput("新增系统", 0), false);
  assert.equal(shouldRequireVisibleOutput("生成一张完整流程图", 3), false);
});
