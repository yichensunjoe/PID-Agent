import assert from "node:assert/strict";
import test from "node:test";
import { parseImportJson } from "../src/projectImport.ts";

test("document import accepts raw documents and the versioned envelope", () => {
  assert.deepEqual(parseImportJson('{"id":"doc_raw"}', "document"), { id: "doc_raw" });
  assert.deepEqual(
    parseImportJson('{"format":"pid-agent.document","version":1,"document":{}}', "document"),
    { format: "pid-agent.document", version: 1, document: {} },
  );
});

test("project import rejects wrong formats before sending a request", () => {
  assert.throws(() => parseImportJson('{"format":"pid-agent.document"}', "project"), /不是 P&ID-Agent 项目包/);
  assert.throws(() => parseImportJson('{"format":"pid-agent.project-package"}', "document"), /导入项目包/);
  assert.throws(() => parseImportJson('[1,2,3]', "document"), /JSON 对象/);
  assert.throws(() => parseImportJson('{broken', "document"), /JSON 解析失败/);
});
