# 工艺流向、阀门状态、管线连接、OPC 与 Agent Harness

## 动态流道

工艺管线继续使用原有 `ConnectorElement`：

- `medium` 为 `water` 或 `gas` 时，画布叠加绿色动态流道；其他介质仍可使用自定义字符串。
- `flow_direction=forward` 表示 Source → Target，`reverse` 表示 Target → Source，`none` 不显示动态流动。
- 动画只用于浏览器运行状态，不进入 SVG、PDF、DXF 或 PNG 工程导出。

## 阀门状态与流动隔离

阀门状态保存在 `SymbolElement.properties.valve_state`：

- `open`：打开；
- `closed`：关闭；
- 字段缺失时按常开处理。

关闭阀门后，按 `flow_direction` 可确定的下游管线停止播放介质流动动画，并显示为低透明度断续状态。该状态属于运行语义，而不是绘图错误：不会拒绝人工或 Agent 事务，也不会触发重规划。

Harness 使用 `VALVE_CLOSED_FLOW_ISOLATION` 信息 finding，并在受影响 connector 上设置 `flow_blocked=true`。未声明流向的管线无法可靠确定上下游，因此不进行方向性隔离推断。

## 三通吸附与跨线

连接点是具有真实拓扑语义的三通或汇合节点。

- 从端口或既有工艺管线开始拉线时，编辑器会识别附近的管线线段。
- 端点在另一条工艺管线上停留约 `0.32 s` 后显示“已吸附 · 生成三通”。松开鼠标时，主线原子拆分为两段，并在交点创建 `JunctionElement`。
- 停留时间未达到前移开鼠标，不会吸附或创建连接点。
- 两条正交管线只有几何交叉、没有共享连接点时，后绘制管线自动显示跨线桥，拓扑保持互不连通。
- 交叉处已经存在连接点时，不显示跨线桥。

因此，直接经过表示跨线；停留吸附表示三通。

## 精细网格

编辑吸附步长统一为 `5 px`，适用于设备、仪表、文字、连接点和管线。视觉主网格仍保持 `20 px`，避免画布过密。

5 px 网格是浏览器编辑偏好，不修改服务器保存的工程文档网格，不增加 revision，也不在打开图纸时写入撤销历史。真实端口和管线交点优先于网格，使用精确坐标。

## OPC / Off-page connector

内置图例库提供：

- `off_page_connector_in`：介质从关联 P&ID 进入当前图；
- `off_page_connector_out`：介质从当前图离开。

两个符号采用标准跨图连接符外形并镜像显示。旧的 `off_page_connector` 与 `system_interface` 仅保留历史文档兼容，不再显示在图例面板或 Agent 可选目录中。

关联目标保存在 `properties.target_document_id`。选中 OPC 后可选择目标图纸，双击 OPC 可打开关联 P&ID。

## Agent Harness

语义 Agent 每次规划与重规划都会附加 `pid-agent.agent-harness-context` v1，包括：

- 当前 document ID 与 revision；
- 符号真实端口、方向和介质；
- connector 的介质、方向、上下游元素、`main_route_id` 和 `flow_blocked`；
- 阀门状态及关闭阀门造成的下游流动隔离；
- 连接点作为三通、无连接点交叉使用跨线桥，以及 5 单位精细坐标约束；
- OPC 方向与目标 document ID。

调试接口：

```text
GET /api/v2/documents/{document_id}/agent/harness-context
```

模型绘图继续采用宽容编译：有效操作可以落图，无效绘图操作会被跳过；revision 冲突、鉴权、数据库完整性和共享部署安全边界仍然保留。

## 其他运行功能

- 当前图纸可通过文档标题旁的“重命名”按钮修改名称。
- 顶部工具栏提供“导出 PNG”。
- 左侧 P&ID 文档列表和图例库可以独立折叠和滚动。
