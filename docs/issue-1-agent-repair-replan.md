# Issue #1 切片：Agent 语义操作、失败分析与局部重规划

本切片把网页 Agent 和外部 MCP Agent 的高风险局部修改从通用 `update_element`/`delete_element` 提升为更明确的工程语义操作，并把失败原因作为结构化数据反馈给下一次规划。

## 1. 新的语义操作

### `connect_ports`

用于在两个真实端口之间创建 connector。Agent 只需要提供：

- connector ID；
- source element/port；
- target element/port；
- routing、介质、管径和可选样式。

服务端负责：

- 验证 element 是否为 symbol 或 junction；
- 验证 port ID；
- 计算真实端口坐标；
- 生成正交或直连路径；
- 继承 source 元素的 layer/system（未显式指定时）。

### `replace_symbol`

用于在原 element ID 上替换设备或仪表：

- 保留 element ID；
- 默认保留位置、尺寸、旋转、标签、图层、系统、样式和属性；
- 原 connector ID 不变；
- 新旧图例端口同名时自动复用；
- 端口不同名时必须通过 `port_mapping` 明确映射；
- 连接管线位于锁定图层时拒绝替换。

语义操作会编译为一个原子低层事务：

```text
删除旧 symbol（connector 暂时转为自由端点）
→ 使用同一 ID 添加新 symbol
→ 按 port_mapping 重新绑定原 connector
```

整个编译结果在写入前重新验证，不会在数据库中留下中间状态。

### `reconnect_connector`

用于只修改一个 connector endpoint：

- `endpoint: source | target`；
- 绑定到真实 `element_id + port_id`；
- 或明确改为带坐标的自由端点；
- 可同时设置 routing。

Agent 不能再通过 `update_element.patch.source/target` 修改端点；编译器会返回 `reconnect_connector_required`。

### 带连接策略的 `delete_element`

Agent 删除 symbol/junction 时必须明确或接受安全默认值：

- `reject_if_connected`：默认；存在连接时拒绝；
- `detach`：删除设备，保留 connector 自由端点；
- `delete_connectors`：同时删除直接相连 connector。

`delete_connectors` 遇到锁定管线时拒绝执行。

## 2. 编译与验证

语义事务不会直接写入 SQLite。处理流程：

```text
Semantic transaction
→ 顺序编译为低层 Operation
→ 在文档副本上模拟执行
→ 低层 TransactionRequest 完整验证
→ 返回预览
→ 用户确认后调用现有原子 apply 接口
```

顺序编译允许同一个事务先新增设备，再通过 `connect_ports` 引用这些新设备。

语义编译失败时返回：

- `stage: compile`；
- operation index；
- issue code；
- field path；
- element/connector ID；
- 当前可用的 symbol key、port ID 或 element ID；
- 修复建议。

低层事务模拟失败时返回 `stage: validate`。

主要 issue code：

```text
revision_conflict
replace_symbol_required
replacement_port_mapping_required
unknown_replacement_port
reconnect_connector_required
connector_not_found
endpoint_element_not_found
unknown_port
element_has_connections
connected_connector_locked
layer_locked
non_orthogonal_route
duplicate_id
unknown_symbol
unknown_layer
unknown_system
```

## 3. 网页局部重规划

网页 Agent 现在调用：

```http
POST /api/v2/documents/{document_id}/agent/plan-v2
POST /api/v2/documents/{document_id}/agent/replan
```

初次规划返回：

- semantic plan 和 plan ID；
- 编译后的低层 plan（仅在有效时存在）；
- compile/validate assessment；
- 受影响元素；
- 语义操作数和编译操作数。

失败时，右侧面板展示真实问题、可用值和建议。用户点击“按失败原因重规划”后，服务端向模型提供：

- 当前最新文档；
- scene summary；
- 原始指令和局部上下文；
- 失败 semantic plan；
- 结构化 assessment；
- repair attempt。

模型必须返回完整替代计划，而不是对旧 JSON 做文本补丁。最多支持 5 次显式重规划。

选中元素时，局部上下文现在包含：

- 选中元素完整 JSON；
- 与选中元素直接相连的 connector 完整 JSON。

## 4. REST 接口

### 获取语义事务 schema

```http
GET /api/v2/agent/semantic-tool-schema
```

### 分析低层事务但不写入

```http
POST /api/v2/documents/{document_id}/transactions/analyze
```

分析接口即使失败也返回 HTTP 200 和 `valid: false`，便于 Agent 读取 issue 后修复。实际 apply 仍使用 409/422 阻止非法写入。

## 5. MCP 工具

新增：

```text
get_agent_transaction_schema
analyze_transaction
compile_agent_transaction
apply_agent_transaction
```

推荐外部 Agent 使用：

```text
get_scene_summary
→ get_agent_transaction_schema
→ compile_agent_transaction
→ 检查 assessment
→ apply_agent_transaction
→ get_scene_summary
```

`apply_agent_transaction` 只有在编译和验证均通过时才写入，并继续记录 MCP 来源的 revision 历史。

原有 `apply_transaction_v2` 和字符串版 `apply_transaction` 保留兼容。

## 6. 诊断日志

新增事件：

```text
llm.semantic_plan.started
llm.semantic_plan.completed
llm.semantic_plan.failed
llm.semantic_replan.started
llm.semantic_replan.completed
llm.semantic_replan.failed
```

记录字段包括：

- plan ID / parent plan ID；
- attempt；
- expected revision；
- compile/validate stage；
- issue code；
- semantic/compiled operation 数；
- 受影响元素；
- 模型、Base URL、超时和耗时。

API Key、完整 Prompt、完整 context 和异常正文继续统一脱敏。

## 7. 验收覆盖

新增回归测试覆盖：

- 替换设备时缺失 port mapping 的结构化错误；
- 正确映射后 connector ID 和端口语义保持；
- 同一语义事务新增设备并连接端口；
- connector endpoint 重新绑定；
- 删除连接设备的默认拒绝；
- 删除设备与连接管线的级联策略；
- 无效计划不增加 revision；
- 基于失败 assessment 的重规划；
- 修复计划确认后 history source 为 `llm`；
- revision conflict 的结构化分析。

## 8. 未完成范围

本切片提供确定性的语义编译和修复闭环，但不会直接宣称所有模型已经稳定。仍需最终体验阶段使用实际模型矩阵验证：

- 不同模型是否持续选择正确的语义 operation；
- 多设备、多 connector 的替换与重连；
- 模糊指令下删除策略是否符合用户意图；
- 连续 2～5 次重规划是否收敛；
- 大型工程图中的 token、延迟和成功率。
