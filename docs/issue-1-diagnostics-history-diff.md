# Issue #1 切片：详细诊断日志与 Revision 差异

本切片用于支撑最终统一验收。目标不是仅记录“成功/失败”，而是让一次 Web、网页 LLM 或 MCP 修改能够追溯到具体 revision、operation、元素 ID 和前后状态。

## Revision 详细历史

升级后的每次事务会在 `document_history.details_json` 中保存：

- `base_revision` 与 `result_revision`；
- 修改前后元素数量；
- 新增、修改、删除的元素 ID；
- 因设备移动、端口归一化等原因自动变化的关联 connector；
- operation 摘要；
- 每个元素、图层和系统的 changed fields；
- 最多 100 条 before/after 快照；
- 超出快照上限时的 `diff_truncated` 标记。

旧数据库启动时会自动增加 `details_json` 字段。旧历史不会伪造差异；从升级后的首次操作开始产生详细记录。

详细差异写入失败不会回滚已经成功提交的工程事务，诊断事件会记录 `history_details_persisted: false`。基础 revision 历史仍然保留。

## 网页历史面板

历史面板支持：

- 查看每条 revision 的新增、修改和删除数量；
- 展开 operation 清单；
- 展开元素或分组的 before/after JSON；
- 将本 revision 中当前仍存在的元素设为画布选择，从而高亮修改范围；
- 清除高亮；
- 下载当前文档的诊断日志包。

已删除元素无法在当前画布中高亮，但 before 快照会保留在差异详情中。

## 结构化诊断日志

Web 服务和 stdio MCP 共用本地 JSONL 诊断文件。默认路径由数据库路径派生：

```text
数据库：data/pid-agent.db
日志：  data/pid-agent.diagnostics.jsonl
```

可通过环境变量覆盖：

```bash
export PID_AGENT_DIAGNOSTICS_PATH=/absolute/path/pid-agent.diagnostics.jsonl
```

日志文件达到 5 MiB 后进行定向轮转，保留 3 份备份：

```text
pid-agent.diagnostics.jsonl
pid-agent.diagnostics.jsonl.1
pid-agent.diagnostics.jsonl.2
pid-agent.diagnostics.jsonl.3
```

不会执行目录级递归删除。

## 主要事件

```text
server.runtime.created
mcp.runtime.created
http.request.started
http.request.completed
http.request.failed
document.created
document.deleted
document.revision.created
llm.provider_test.started
llm.provider_test.completed
llm.provider_test.failed
llm.plan.started
llm.plan.completed
llm.plan.failed
llm.plan.rejected
```

典型 revision 事件包含：

```json
{
  "event": "document.revision.created",
  "document_id": "doc_...",
  "base_revision": 12,
  "revision": 13,
  "source": "mcp",
  "action": "transaction",
  "label": "Move selected valve",
  "operation_count": 3,
  "affected_element_ids": ["valve_101", "pipe_101"],
  "added_element_ids": [],
  "updated_element_ids": ["valve_101", "pipe_101"],
  "deleted_element_ids": [],
  "history_details_persisted": true
}
```

LLM 日志记录：

- Base URL；
- 模型名称；
- 超时设置；
- Prompt 和上下文字符数；
- dry-run 状态；
- 规划耗时；
- transaction label；
- operation 数量；
- 结构化错误代码和供应商 HTTP 状态。

## 脱敏规则

诊断日志不记录：

- API Key；
- Authorization header；
- Bearer token；
- 完整 Prompt；
- 完整工艺上下文；
- 未处理的异常消息正文。

包含 `api_key`、`authorization`、`secret`、`token` 或 `password` 的字段会被替换为 `<redacted>`。常见 `Bearer ...`、`sk-...` 和 URL 查询密钥也会进行字符串级清理。

文档快照和 revision before/after 属于用户主动绘制的工程数据，会包含设备标签、文字和工程备注。下载诊断包前应按项目保密要求处理。

## 诊断导出

REST：

```http
GET /api/v2/diagnostics/export?document_id={document_id}&limit=1000
```

导出 JSON 包含：

- 服务版本；
- 数据库绝对路径和实例 ID；
- 文档列表；
- 当前文档完整快照；
- scene summary；
- 最多 500 条详细 revision 历史；
- 最近脱敏诊断事件；
- 明确的隐私声明。

MCP：

```text
get_diagnostics(limit=200)
get_document_history(document_id, limit=100)
```

`get_server_info` 也会返回诊断文件路径、大小和数据库实例 ID。

## 最终验收时建议提供

1. 网页下载的 `pid-agent-diagnostics-{document_id}.json`；
2. 相关 `pid-agent.diagnostics.jsonl` 及必要的轮转文件；
3. 体验记录中的大致操作时间；
4. 失败时页面显示的 request ID；
5. 使用的模型名称、Base URL 和超时设置，不提供 API Key。

## 本切片验收

1. Web 添加并修改一个文字，历史详情显示 before/after；
2. 移动已连接设备，设备和自动变化的 connector 均进入 affected IDs；
3. MCP 提交事务，历史来源为 MCP 且存在 operation 摘要；
4. 撤销后生成新的 undo 差异；
5. 点击“高亮现存项”，画布选择对应元素；
6. 下载诊断包，确认能读取文档、历史和事件；
7. 使用一个可识别的测试 API Key，确认诊断包中不存在该字符串；
8. 旧 SQLite 数据库启动后自动获得 `details_json` 字段。
