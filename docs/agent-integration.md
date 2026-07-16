# P&ID-Agent 的 Agent 接入

## 目标

P&ID-Agent 支持两类 Agent 使用方式：

1. Agent 自己决定何时调用 P&ID 工具：使用 MCP、REST 或 Python Client；
2. 用户在 P&ID-Agent 网页内输入自然语言：由内置 OpenAI-compatible 规划器生成事务。

两者最终都调用同一个 `DocumentService.apply_transaction`，因此人工编辑和 Agent 修改不会形成两份状态。

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

## 连接语义

Agent 绘制管线时应优先使用 `connector`：

- 连接设备时，source/target 使用设备 `element_id` 和符号定义中的 `port_id`；
- 分支或汇合时，先创建 `junction`，其端口固定为 `node`；
- 多条管线应连接到同一 junction，而不是仅让线段视觉交叉；
- `routing: orthogonal` 由服务端生成基础正交路径；
- `routing: manual` 用于保存人工调整后的正交折线路径；
- 手工路径中的每一段仍必须水平或垂直。

连接节点示例：

```json
{
  "expected_revision": 4,
  "label": "Add a semantic process branch",
  "operations": [
    {
      "op": "add_element",
      "element": {
        "id": "junction_feed_1",
        "type": "junction",
        "position": {"x": 420, "y": 260}
      }
    },
    {
      "op": "add_element",
      "element": {
        "type": "connector",
        "points": [{"x": 420, "y": 260}, {"x": 620, "y": 260}],
        "source": {
          "element_id": "junction_feed_1",
          "port_id": "node",
          "point": {"x": 420, "y": 260}
        },
        "target": {"point": {"x": 620, "y": 260}},
        "routing": "manual",
        "process_tag": "L-101-BR"
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

规划器调用：

```text
{base_url}/chat/completions
```

并支持无 `response_format` 的回退请求，以兼容实现程度不同的本地服务。

```bash
export PID_AGENT_LLM_BASE_URL=http://localhost:11434/v1
export PID_AGENT_LLM_MODEL=your-model
export PID_AGENT_LLM_API_KEY=optional
```

API key 只用于当前请求或环境变量，不写入数据库。旧 `AGENTCAD_LLM_*` 变量暂时兼容。

## MCP

```bash
pid-agent-mcp
```

数据库路径和网页服务应指向同一 SQLite 文件：

```bash
export PID_AGENT_DATABASE_PATH=/absolute/path/pid-agent.db
```

## 后续知识库

设计理念、工艺说明和单位标准文件不应直接无限拼接进 prompt。后续将加入：

- 项目文件上传；
- 文本和表格提取；
- 分段与元数据；
- 基于当前任务的检索；
- 对引用段落的可追溯记录；
- 单位规则与图纸元素的关联检查。
