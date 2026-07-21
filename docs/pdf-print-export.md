# PDF、打印图幅与标题栏

P&ID-Agent 的 PDF 导出复用网页、SVG 和 PNG 使用的同一结构化 SVG 渲染器。设备、端口、管线、分支、流向、跨线、图层和系统显隐不会在 PDF 路径中重新实现。PDF 页面由确定性的图幅计划生成，不调用浏览器打印对话框。

## 支持的图幅

支持 ISO A 系列图幅：A4、A3、A2、A1、A0。每种图幅均支持：

- 横向 `landscape`；
- 纵向 `portrait`；
- 5–50 mm 图幅边距；
- 可选图框；
- 可选标题栏；
- 单页适配 `fit`；
- 固定比例分页 `tile`。

默认配置为 A3 横向、10 mm 边距、图框和标题栏开启、单页适配。

## 浏览器操作

1. 打开文档并切换到右侧 **图层/系统** 面板。
2. 在 **导出与打印** 中选择 `PDF`。
3. 选择内容范围、图幅、方向、分页方式和边距。
4. 可选填写项目名、图号、版本和日期。留空时使用项目设置和文档 metadata。
5. 点击 **预览打印图幅** 查看第一页及总页数。
6. 点击 **导出 PDF** 下载文件。

预览使用服务端生成的最终图幅 SVG，因此图框、标题栏、页码和工程内容的位置与 PDF 一致。预览不会修改文档 revision。

## 内容范围

PDF 与现有 SVG/PNG 使用相同范围规则：

- `canvas`：完整文档画布；
- `content`：可见图层和系统中的元素包围范围；
- `viewport`：调用方提供的当前视口 `x/y/width/height`。

隐藏图层或隐藏系统中的元素不会进入 SVG、PNG、PDF 或打印预览。

## 单页适配与分页

`fit` 把所选范围等比例放入一个图幅的绘图区，不拉伸图形。

`tile` 按 `tile_scale` 固定缩放并以从左到右、从上到下的顺序分页。每页标题栏包含 `当前页/总页数`。最后一行或最后一列可以只使用部分绘图区，不会拉伸剩余内容。

服务端环境变量 `PID_AGENT_MAX_PDF_PAGES` 控制普通请求允许生成的最大页数，默认 100。超过限制返回 HTTP 413，并且不会生成部分 PDF。减小 `tile_scale`、改用 `fit`，或缩小导出范围后可以重试。

## 标题栏 metadata

标题栏字段按以下顺序解析：

- 项目名：请求覆盖值 → 项目设置 `project.name`；
- 图名：文档 `name`；
- 图号：请求覆盖值 → `metadata.drawing_number` → `drawing_no` → `document_number`；
- 版本：请求覆盖值 → `metadata.drawing_revision` → `drawing_version` → 文档 revision；
- 日期：请求覆盖值 → `metadata.drawing_date` → `date` → 文档更新时间日期。

超长字段会在各自单元格内确定性截断并显示省略号，不会越过标题栏边界。服务端使用 Noto Sans CJK 和 DejaVu Sans 回退，避免中文工程文字在 PDF 中显示为方框。

## REST API

打印预览：

```text
GET /api/v2/documents/{document_id}/print-preview.svg
```

PDF 下载：

```text
GET /api/v2/documents/{document_id}/export-v2.pdf
```

通用查询参数：

```text
range=content|canvas|viewport
padding=24
paper_size=A4|A3|A2|A1|A0
orientation=portrait|landscape
layout=fit|tile
margin_mm=10
frame=true|false
title_block=true|false
tile_scale=1
project_name=...
drawing_number=...
revision=...
drawing_date=...
```

`viewport` 还需要 `x`、`y`、`width` 和 `height`。预览额外接受从 1 开始的 `page`。

响应头包括：

```text
X-PID-Agent-PDF-Page-Count
X-PID-Agent-PDF-Page-Number   # 仅预览
X-PID-Agent-PDF-Paper-Size
X-PID-Agent-PDF-Orientation
X-PID-Agent-PDF-Layout
```

无效图幅、方向、边距或页号返回 HTTP 422；页数超限返回 HTTP 413；渲染依赖或生成失败返回 HTTP 500。失败响应包含稳定错误代码和可重试标记。

## Python Client

```python
from agentcad.client import AgentCADClient

with AgentCADClient("http://127.0.0.1:8000/api/v2") as client:
    client.export_pdf(
        "doc_123",
        "drawing.pdf",
        export_range="content",
        paper_size="A3",
        orientation="landscape",
        layout="fit",
        margin_mm=10,
        drawing_number="P-100-001",
        revision="B",
    )
```

`client.export(document_id, "pdf", destination)` 使用默认 A3 横向单页配置。

## 验证生成结果

自动测试验证全部图幅和方向的页面尺寸、分页顺序、页数上限、标题栏 metadata、隐藏元素过滤、REST 响应、Python Client 和浏览器下载。

审查有意的版式变化时，还应把 PDF 光栅化为 PNG，逐页确认：

- 图框和标题栏没有被裁切；
- 中文和英文文字没有黑方块；
- 标题栏字段没有越过单元格；
- 设备、管线、箭头和颜色与 SVG/PNG 一致；
- 分页没有遗漏或重复工程区域。

仓库的普通 CI 不提交生成的 PDF 或光栅化 PNG。它们仅用于本地或 CI 临时检查，完成后必须删除。

工程 DXF 交换导出已经作为独立切片实现，详见 [`dxf-export.md`](dxf-export.md)。
