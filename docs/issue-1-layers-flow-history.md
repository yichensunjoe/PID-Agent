# Issue #1 切片：图层、系统、流向、跨线和历史

本切片补齐中等复杂度 P&ID 中最常用的组织与表达能力，并让 Web、网页 LLM 和 MCP 的修改来源可以被用户识别。

## 图层

- 文档继续保留默认图层 `layer_default`；
- 可新增、重命名、显示、隐藏、锁定和删除图层；
- 删除图层时，其中元素原子迁移至指定图层；
- 选中一个或多个元素后，可批量分配到图层；
- 锁定图层中的元素不能移动、修改属性、编辑管线路径或删除；
- 隐藏图层不会出现在网页画布、SVG 或 PNG 导出中。

## 工艺系统

- 每个元素新增 `system_id`；
- 旧文档载入时自动使用 `system_default`，无需手工迁移 JSON；
- 可新增、重命名、显示、隐藏和删除工艺系统；
- 选中元素可批量分配到系统；
- 系统显隐与图层显隐共同决定画布和导出结果；
- Agent scene summary 包含图层、系统及每个设备、junction、connector 的归属。

## 管线工程属性

connector 新增：

```json
{
  "medium": "CW",
  "nominal_diameter": "DN50",
  "flow_direction": "forward",
  "arrow_position": "middle",
  "crossing_style": "jump",
  "jump_radius": 7
}
```

属性检查器中可修改：

- 介质；
- 公称管径；
- Source → Target、Target → Source 或无流向箭头；
- 箭头位于起点附近、中部或终点附近；
- 普通交叉或跨线桥；
- 跨线桥半径。

流向箭头沿实际折线路径计算方向。调整折线后，箭头仍附着在管线上。

跨线桥只表示视觉上的“不连接”。真实分支和汇合仍必须使用 junction。两条 connector 共享同一语义端点时不会绘制跨线桥。

## Revision 历史

SQLite 新增 `document_history` 表，文档写入与历史记录位于同一数据库事务中。历史字段包括：

- revision；
- 时间；
- 来源：`web`、`llm`、`mcp` 或 `system`；
- 动作：创建、事务、撤销或重做；
- transaction label；
- operation 数量。

REST：

```http
GET /api/v2/documents/{document_id}/history?limit=100
```

MCP：

```text
get_document_history(document_id, limit=100)
```

网页右侧“历史”面板会在 revision 变化后重新读取记录。升级前已存在的 SQLite 文档不会伪造旧历史；从升级后的首次操作开始记录。

## 验收步骤

1. 新建 `Cooling Water` 系统，把一组设备和管线分配到该系统；
2. 隐藏该系统，确认画布和 SVG 导出均不包含这些元素；
3. 锁定设备图层，确认拖动、删除和属性修改被拒绝；
4. 给一条 connector 设置 `CW`、`DN50` 和正向中部箭头；
5. 让该 connector 与另一条正交管线交叉并启用跨线桥；
6. 通过 MCP 修改文档，确认历史面板显示来源 `MCP`；
7. 在网页撤销，确认产生新的 `undo` revision 历史。
