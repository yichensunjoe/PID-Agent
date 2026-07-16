# AgentCAD 2 架构

## 设计原则

### 单一文档真相源

网页、REST、MCP 和内部 LLM 规划器不能分别维护一份状态。所有修改最终都必须转成 `TransactionRequest` 并由 `DocumentService` 执行。

这样可以保证：

- 浏览器移动设备后，Agent 读取到的是同一份最新文档；
- Agent 生成期间有人修改文档时，旧 revision 会被拒绝；
- 撤销、重做和审计可以覆盖所有修改渠道；
- 后续增加插件或 Python SDK 时不需要重写状态逻辑。

## 分层

```text
┌─────────────────────────────────────────────┐
│ React 编辑器 / REST 客户端 / MCP 客户端     │
└──────────────────────┬──────────────────────┘
                       │ TransactionRequest
┌──────────────────────▼──────────────────────┐
│ FastAPI / MCP adapters                      │
│ 参数转换、HTTP 错误、工具描述               │
└──────────────────────┬──────────────────────┘
                       │
┌──────────────────────▼──────────────────────┐
│ DocumentService                             │
│ 原子事务、revision、撤销重做、场景摘要       │
└───────────────┬─────────────────┬───────────┘
                │                 │
┌───────────────▼────────┐ ┌──────▼───────────┐
│ SQLiteDocumentStore    │ │ SymbolRegistry   │
│ 文档与历史快照          │ │ 单位图例与连接口  │
└────────────────────────┘ └──────────────────┘
```

## 文档模型

`Document` 包含：

- `revision`：单调增加的并发版本；
- `canvas`：图幅、网格和背景；
- `layers`：可见性和锁定；
- `elements`：基础图元、设备符号和语义连接线；
- `metadata`：项目级扩展信息。

### SymbolElement

设备实例只保存：

- `symbol_key`
- 位置、宽高和旋转
- 位号/标签
- 工艺属性

具体形状和端口由 `SymbolRegistry` 提供。更换单位图例不会导致已有文档结构失效，只要保持 `symbol_key` 稳定。

### ConnectorElement

工艺管线不是普通直线。它保存：

- 折线点；
- 可选 source/target 设备和端口；
- 管线或工艺标签。

这使 Agent 能理解“V-101 的出口连接 P-101 的入口”，而不只是看到两条靠得很近的线。

## 事务

事务包含一个或多个操作：

- `add_element`
- `update_element`
- `delete_element`
- `add_layer`
- `update_layer`
- `delete_layer`
- `clear_document`

执行过程：

1. 加载当前文档；
2. 检查 `expected_revision`；
3. 在内存副本上执行全部操作；
4. 重新进行 Pydantic 文档级验证；
5. 写入新的 revision，并把旧快照压入 undo stack；
6. 任一操作失败则不保存任何变化。

## 历史

Alpha 阶段使用完整文档快照，优点是正确性高、实现简单，适合当前文档规模。后续文档变大后可以迁移为事件日志或增量 patch，而不改变 API 事务语义。

## LLM 规划器

LLM 不直接写数据库，也不生成任意代码。它只负责输出 `TransactionRequest`：

- 系统提示包含图例目录；
- 系统提示包含 Pydantic 生成的 JSON Schema；
- 输出再次由 Pydantic 验证；
- 图例 key、图层和 revision 由服务层再次检查；
- 写入失败不会留下半张图。

## 扩展方向

- 文件知识库应作为独立的 project context 层加入；
- 自动布局应生成事务，而不是绕过服务层；
- DXF/PDF 应作为 document exporter；
- 单位规则检查应读取同一语义文档并返回可定位到 element id 的问题。
