export type ImportPayloadKind = "document" | "project";

export function parseImportJson(text: string, expectedKind: ImportPayloadKind): unknown {
  let payload: unknown;
  try {
    payload = JSON.parse(text) as unknown;
  } catch (error) {
    throw new Error(`JSON 解析失败：${error instanceof Error ? error.message : String(error)}`);
  }
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    throw new Error("导入文件必须包含一个 JSON 对象。");
  }
  const format = (payload as Record<string, unknown>).format;
  if (expectedKind === "project") {
    if (format !== "pid-agent.project-package") {
      throw new Error("该文件不是 P&ID-Agent 项目包。");
    }
    return payload;
  }
  if (format === "pid-agent.project-package") {
    throw new Error("项目包请使用“导入项目包”。");
  }
  if (format !== undefined && format !== "pid-agent.document") {
    throw new Error(`不支持的文档格式：${String(format)}`);
  }
  return payload;
}
