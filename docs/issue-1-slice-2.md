# Issue #1 第二切片

本切片完成：

- P&ID-Agent 产品、发行包、CLI、API、MCP、Docker 和文档品牌统一；
- 单选、Shift 多选、框选和全选；
- 多元素移动、删除和复制；
- `Ctrl/Cmd+D` 复制选择；
- 复制设备、连接节点和内部管线时重映射连接关系；
- 正交管线内部线段拖动；
- 语义连接节点；
- 在主管线上放置节点时原子拆分管线；
- 支路和汇合连接到同一节点；
- 移动节点后所有关联管线同步；
- 场景摘要和 SVG 导出保留连接节点拓扑；
- 修复 wheel 中图例数据重复包含的问题。

验证：

- 后端专项测试：8 passed；
- Ruff：通过；
- React/TypeScript/Vite 生产构建：通过；
- `pid-agent` wheel：构建通过，并包含 `agentcad/data/symbols.json`。
