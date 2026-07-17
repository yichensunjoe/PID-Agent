# P&ID-Agent 的 Agent 接入

## 目标

P&ID-Agent 支持两类 Agent 使用方式：

1. Agent 自己决定何时调用 P&ID 工具：使用 MCP、REST 或 Python Client；
2. 用户在 P&ID-Agent 网页内输入自然语言：由内置 OpenAI-compatible 规划器生成事务。

两者最终都调用同一个 `DocumentService.apply_transaction`，因此人工编辑和 Agent 修改不会形成两份状态。

## 推荐调用顺序

修改已有图纸时，新 Agent 优先使用语义事务闭环：

1. `get_server_info()`，确认数据库实例和版本；
2. `list_documents()`；
3. `get_scene_summary(document_id)`；
4. 必要时 `get_document(document_id)`；
5. `list_symbols()`；
6. `get_agent_transaction_schema()`；
7. 生成 semantic transaction；
8. `compile_agent_transaction(document_id, transaction)`；
9. 检查 `assessment.valid`、issue code、可用 ID/端口和修复建议；
10. `apply_agent_transaction(document_id, transaction)`；
11. 再次读取 scene summary 和 history 确认结果。

语义事务提供以下高频工程动作：

- `connect_ports`：连接两个真实端口；
- `replace_symbol`：替换设备并显式映射原有连接端口；
- `reconnect_connector`：修改一个 connector endpoint；
- 带 `connection_policy` 的 `delete_element`。

对于高级或已有低层 transaction 的客户端，原闭环仍然可用：

1. 生成低层 transaction；
2. `analyze_transaction(document_id, transaction)` 获取结构化分析；
3. 或调用 `validate_transaction(document_id, transaction)`；
4. `apply_transaction_v2(document_id, transaction)`；
5. 再次读取 scene summary。

旧的 `apply_transaction(document_id, transaction_json)` 字符串接口仍保留兼容。

不要在未读取 revision 的情况下根据旧上下文持续修改。transaction 应传 `expected_revision`；revision 冲突时重新读取文档并重新规划。

## 连接语义

Agent 绘制管线时应优先使用语义操作 `connect_ports`。它只接收真实 element/port ID，并由服务端计算端口坐标和基础路径。

使用低层 connector 时：

- 连接设备时，source/target 使用设备 `element_id` 和符号定义中的 `port_id`；
- 分支或汇合时，先创建 `junction`，其端口固定为 `node`；
- 多条管线应连接到同一 junction，而不是仅让线段视觉交叉；
- `routing: orthogonal` 由服务端生成基础正交路径；
- `routing: manual` 用于保存人工调整后的正交折线路径；
- 手工路径中的每一段仍必须水平或垂直。

连接节点低层示例：

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

设备替换语义示例：

```json
{
  "expected_revision": 8,
  "label": "Replace V-101 while preserving connections",
  "operations": [
    {
      "op": "replace_symbol",
      "element_id": "valve_101",
      "symbol_key": "control_valve",
      "port_mapping": {
        "in": "in",
        "out": "out"
      }
    }
  ]
}
```

删除已连接设备默认使用 `reject_if_connected`。只有用户明确要求保留悬空管线或一起删除管线时，才使用 `detach` 或 `delete_connectors`。

## 网页与 MCP 自动同步

网页使用轻量状态接口检查当前文档 revision：

```http
GET /api/v2/documents/{document_id}/status
```

MCP、REST 或其他客户端提交新 revision 后，已打开的网页会自动重新读取文档。默认检查周期为约 1.5 秒，并保留画布缩放、平移以及仍然存在的选中元素。

用户正在拖拽或绘制时，网页不会直接覆盖当前预览，而是显示“检测到外部更新”，由用户点击载入或在操作结束后自动载入。

页面顶部的同步状态包括：

- `已同步至 rN`；
- `正在检查外部修改`；
- `检测到外部更新 rN`；
- `已载入外部更新 rN`；
- 自动同步失败。

## 网页内语义规划

网页初次规划：

```http
POST /api/v2/documents/{document_id}/agent/plan-v2
Content-Type: application/json
```

```json
{
  "prompt": "把选中的阀门替换成调节阀，并保持原有入口和出口管线。",
  "context": "阀门位号和工艺管线标签保持不变。",
  "expected_revision": 3,
  "provider": {
    "base_url": "http://localhost:11434/v1",
    "model": "your-model",
    "timeout_seconds": 180
  }
}
```

响应包含：

- 模型生成的 semantic plan 和 plan ID；
- 编译后的低层事务，仅在有效时返回；
- compile/validate assessment；
- issue code、字段路径、真实可用值和修复建议；
- 受影响元素。

无效计划不会写入文档。网页可调用：

```http
POST /api/v2/documents/{document_id}/agent/replan
```

重规划请求携带原指令、当前文档、失败计划和结构化 assessment。模型必须返回完整替代计划，不是文本补丁。网页最多允许显式重规划 5 次。

有效计划由用户确认后调用：

```http
POST /api/v2/documents/{document_id}/agent/apply-v2
```

确认请求携带 `plan_id`、`parent_plan_id`、`attempt` 和编译后的低层 transaction，使诊断日志能够串联初始计划、失败、重规划和最终 revision。

旧网页接口 `/agent/generate` 和 `/agent/apply` 继续保留兼容。

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

模型连接失败、读取超时、非法 JSON 和事务 schema 校验失败会返回结构化错误。典型超时响应为 HTTP 504：

```json
{
  "detail": {
    "error": "provider_timeout",
    "message": "model did not finish within 120 seconds",
    "retryable": true,
    "provider": {
      "base_url": "http://127.0.0.1:11434/v1",
      "model": "qwen3.6:35b"
    },
    "timeout_seconds": 120
  }
}
```

超时发生在 transaction 应用之前，因此不会留下部分图纸修改。

## MCP

```bash
pid-agent-mcp
```

数据库路径和网页服务应指向同一 SQLite 文件：

```bash
export PID_AGENT_DATABASE_PATH=/absolute/path/pid-agent.db
```

当前 MCP 工具包括：

- `get_server_info`：返回版本、transport、数据库和诊断实例信息；
- `get_diagnostics`：读取脱敏诊断事件；
- `list_documents`；
- `create_document`；
- `get_scene_summary`；
- `get_document`；
- `get_document_history`；
- `list_symbols`；
- `get_agent_transaction_schema`；
- `compile_agent_transaction`；
- `apply_agent_transaction`；
- `get_transaction_schema`；
- `analyze_transaction`；
- `validate_transaction`；
- `apply_transaction_v2`；
- `apply_transaction`：旧字符串接口。

修改 MCP Server 配置或升级版本后，应重新连接 Agent 客户端，使客户端重新发现工具 schema。

## 诊断与最终体验反馈

语义规划日志记录：

- plan ID 和 parent plan ID；
- repair attempt；
- semantic 和 compiled operation 类型；
- compile/validate stage；
- issue code；
- 受影响元素；
- 模型、Base URL、超时和阶段耗时；
- 最终 apply revision。

API Key、Authorization、完整 Prompt、完整 context 和原始异常正文不会写入日志。

最终体验反馈建议包含：

- 页面显示的 request ID；
- 历史面板下载的诊断日志包；
- 使用的模型名称、任务说明和主观结果；
- 失败时看到的 issue code；
- 是否通过重规划收敛以及使用了几次 attempt。

## 后续知识库

设计理念、工艺说明和单位标准文件不应直接无限拼接进 prompt。后续将加入：

- 项目文件上传；
- 文本和表格提取；
- 分段与元数据；
- 基于当前任务的检索；
- 对引用段落的可追溯记录；
- 单位规则与图纸元素的关联检查。
