# 工艺流向、阀门状态、OPC 与 Agent Harness

## 动态流道

工艺管线继续使用原有 `ConnectorElement`，不新增与工程主线脱节的装饰对象：

- `medium` 选择 `water` 或 `gas` 后，画布在原管线上叠加绿色动态流道；其他项目介质仍可使用自定义字符串。
- `flow_direction=forward` 表示 Source → Target，`reverse` 表示 Target → Source，`none` 表示未指定方向且不显示动态流道。
- 水与气体使用略有区别的绿色虚线节奏、线宽和透明度，普通缩放下也能辨认；动画不进入 SVG/PDF/DXF/PNG 工程导出。
- 浏览器启用“减少动态效果”时，流道自动停止移动并保留静态区别。

## 阀门状态

所有阀门符号使用 `SymbolElement.properties.valve_state`：

- `open`：打开；
- `closed`：关闭；
- 字段缺失时按 **normally open / 常开** 处理，以兼容旧项目。

阀门状态只表达图纸中的工艺或运行状态，不生成阻断错误，不进入规则报错，也不会让 Agent 事务失败或触发重规划。关闭阀门仍会在画布上显示 `C` 状态徽标，打开阀门显示 `O`。

该状态表达不代替流体力学计算、压降计算或动态过程模拟。

## OPC / Off-page connector

内置图例库提供：

- `off_page_connector_in`：介质从关联 P&ID 进入当前图，当前图侧端口方向为 `out`；
- `off_page_connector_out`：介质从当前图离开，当前图侧端口方向为 `in`。

两个符号统一采用标准跨图连接符外形并镜像显示。旧的 `off_page_connector` 与 `system_interface` 保留为历史文档兼容定义，但不再显示在图例面板或 Agent 可选图例目录中。

关联目标保存在：

```json
{
  "properties": {
    "opc_direction": "in",
    "target_document_id": "doc_target"
  }
}
```

选中 OPC 后可从项目文档列表选择目标。画布双击 OPC 直接打开关联 P&ID；页面同时保存当前标签页内的上一张图入口。要形成正式双向跨图关系，应在目标 P&ID 放置相反方向的 OPC 并链接回源 P&ID。

## Agent Harness

语义 Agent 每次规划与重规划都会自动附加 `pid-agent.agent-harness-context` v1。上下文包含：

- 当前 document ID 与 revision；
- 符号 ID、真实端口、端口方向和介质；
- connector 的介质类别、方向、上下游元素和 `main_route_id`；
- 阀门状态，且明确缺省为常开，但不生成阻断 finding；
- OPC 方向与目标 document ID；
- 约束模型必须使用语义操作、真实端口和 revision 保护，不得用装饰线或文字箭头伪造连接。

调试或集成外部模型时可读取：

```text
GET /api/v2/documents/{document_id}/agent/harness-context
```

语义工具 schema 仍由 `/api/v2/agent/semantic-tool-schema` 提供。Harness 增强上下文；模型绘图采用宽容编译：混合计划中的有效操作可以继续落图，无效绘图操作会被跳过。revision 冲突、鉴权、数据库完整性和共享部署安全边界仍然保留。

## P&ID 重命名与 PNG 导出

- 当前图纸可通过文档标题旁的“重命名”按钮修改名称；接口使用 `expected_revision` 防止覆盖并发修改，并进入撤销历史。
- 顶部工具栏提供“导出 PNG”，直接下载当前 P&ID 的确定性 PNG 图片。

## 左侧工作区

左侧工作区增加独立的 `P&ID` 与 `图例` 折叠控制。文档列表和图例库分别滚动，文档数量较多时无需滚动到最底部才能查找图例。

## 共享部署访问令牌

“共享部署访问令牌”是 **P&ID-Agent 自身 HTTP API 的 Bearer token**，不是 OpenAI、Kimi、DeepSeek 或其他模型服务的 API Key。

- `local` 部署模式通常无需填写。
- `shared` 模式由部署者配置服务 token；浏览器在请求 P&ID-Agent 后端时发送 `Authorization: Bearer <token>`。
- token 只保存在当前浏览器标签页的 `sessionStorage`，不会写入 URL 或长期 `localStorage`；关闭标签页后失效。
- Provider API Key 仍在 Agent 的“模型服务与高级设置”中单独输入，两类凭据不可互换。
- 只向获准访问该共享 P&ID-Agent 实例的人员发放；泄露后应在部署端轮换。
