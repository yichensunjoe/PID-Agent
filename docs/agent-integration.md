# Agent 接入

## 目标

AgentCAD 支持两类 Agent 使用方式：

1. Agent 自己决定何时调用 CAD 工具：使用 MCP 或 REST；
2. 用户在 AgentCAD 网页内输入自然语言：由内置 OpenAI-compatible 规划器生成事务。

两者最终都调用同一个 `DocumentService.apply_transaction`。

## 推荐调用顺序

修改已有图纸时：

1. `list_documents`
2. `get_scene_summary(document_id)`
3. 必要时 `get_document(document_id)`
4. `list_symbols()`
5. 生成一个事务
6. `apply_transaction(document_id, transaction_json)`
7. 再次读取 scene summary 确认结果

不要在未读取 revision 的情况下根据旧上下文持续修改。REST 请求应传 `expected_revision`；revision 冲突时重新读取文档并重新规划。

## 事务示例

```json
{
  "expected_revision": 4,
  "label": "Add feed pump and discharge pressure indication",
  "operations": [
    {
      "op": "add_element",
      "element": {
        "type": "symbol",
        "symbol_key": "centrifugal_pump",
        "position": {"x": 420, "y": 260},
        "width": 80,
        "height": 70,
        "label": "P-101A"
      }
    },
    {
      "op": "add_element",
      "element": {
        "type": "symbol",
        "symbol_key": "pressure_indicator",
        "position": {"x": 570, "y": 190},
        "width": 50,
        "height": 60,
        "label": "PI-101"
      }
    }
  ]
}
```

## 网页内生成

```http
POST /api/v2/documents/{document_id}/agent/generate
Content-Type: application/json
```

```json
{
  "prompt": "在 V-101 出口增加两台并联离心泵，并在总管设置压力表。",
  "context": "泵位号使用 P-xxxA/B；仪表位号使用 PI-xxx。",
  "expected_revision": 3,
  "provider": {
    "base_url": "http://localhost:11434/v1",
    "model": "your-model"
  }
}
```

`dry_run: true` 可以只返回规划事务，不写入文档。

## OpenAI-compatible 供应商

规划器直接调用：

```text
{base_url}/chat/completions
```

并支持无 `response_format` 的回退请求，以兼容实现程度不同的本地服务。

API key 只用于当前请求或环境变量，不写入 AgentCAD 数据库。

## MCP

MCP server 通过 stdio 运行：

```bash
agentcad-mcp
```

数据库路径和网页服务应指向同一 SQLite 文件，才能让命令行 Agent 和网页编辑器实时看到同一批文档：

```bash
export AGENTCAD_DATABASE_PATH=/absolute/path/agentcad.db
```

## 后续知识库

设计理念、工艺说明和单位标准文件不应直接无限拼接进 prompt。后续将加入：

- 项目文件上传；
- 文本和表格提取；
- 分段与元数据；
- 基于当前任务的检索；
- 对引用段落的可追溯记录；
- 单位规则与图纸元素的关联检查。
