# Issue #1 切片：图层、系统、流向、跨线和历史

本切片补齐中等复杂度 P&ID 中最常用的组织与表达能力，并让 Web、网页 LLM 和 MCP 的修改来源可以被用户识别。

## 图层和工艺系统

- 文档保留默认图层 `layer_default` 和默认系统 `system_default`；
- 旧文档载入时自动获得默认系统，无需手工迁移 JSON；
- 可新增、重命名、显示、隐藏和删除图层或系统；
- 图层还支持锁定；
- 选中一个或多个元素后，可批量分配到图层或系统；
- 锁定图层中的元素不能移动、修改属性、编辑管线路径或删除；
- 图层与系统显隐同时影响网页画布、SVG 和 PNG 导出；
- Agent scene summary 包含图层、系统及元素归属。

## 属性检查器和管线工程属性

单元素属性检查器可编辑内部名称、工程备注、图层和系统归属。工程备注保存在元素 `metadata.notes` 中。

connector 新增介质、公称管径、流向、箭头位置、跨线样式和跨线桥半径。流向箭头沿实际折线路径计算方向，调整折线后仍附着在管线上。

跨线桥只表示视觉上的“不连接”。真实分支和汇合仍必须使用 junction；共享同一 junction 或设备端口的管线依靠语义绑定表示连接。

## Revision 历史

SQLite 新增 `document_history` 表，文档写入与历史记录位于同一数据库事务中。历史字段包括 revision、时间、来源、动作、transaction label 和 operation 数量。

来源包括 `web`、`llm`、`mcp` 和 `system`；动作包括创建、事务、撤销和重做。

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
