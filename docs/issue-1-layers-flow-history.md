# Issue #1 切片：图层、系统、流向、跨线和历史

本切片补齐中等复杂度 P&ID 中常用的组织与表达能力，并让 Web、网页 LLM 和 MCP 的修改来源可以被用户识别。

## 已实现

- 默认图层 `layer_default` 和默认系统 `system_default`；
- 旧文档自动获得默认系统；
- 图层/系统新增、重命名、显隐、删除和元素批量归属；
- 图层锁定，以及对移动、属性修改、路径编辑和删除的服务端保护；
- 工程备注 `metadata.notes`；
- connector 介质、公称管径、流向箭头、箭头位置和跨线桥；
- 网页画布与 SVG/PNG 使用相同的显隐、箭头和跨线表达；
- SQLite revision 历史，记录 `web`、`llm`、`mcp` 和 `system` 来源；
- 网页历史面板、REST 历史接口和 MCP `get_document_history` 工具。

跨线桥只表示视觉上的“不连接”。真实分支和汇合仍必须使用 junction；共享同一 junction 或设备端口的管线依靠语义绑定表示连接。

## 接口

```http
GET /api/v2/documents/{document_id}/history?limit=100
```

```text
get_document_history(document_id, limit=100)
```

升级前已存在的 SQLite 文档不会伪造旧历史；从升级后的首次操作开始记录。

## 验收步骤

1. 新建 `Cooling Water` 系统，把一组设备和管线分配到该系统；
2. 隐藏该系统，确认画布和 SVG 导出均不包含这些元素；
3. 锁定设备图层，确认拖动、删除和属性修改被拒绝；
4. 给 connector 设置 `CW`、`DN50` 和正向中部箭头；
5. 与另一条正交管线交叉并启用跨线桥；
6. 通过 MCP 修改文档，确认历史面板显示来源 `MCP`；
7. 在网页撤销，确认产生新的 `undo` revision 历史。
