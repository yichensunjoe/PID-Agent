# Issue #1：大型图纸视口、导出范围与性能

## 本切片目标

大型图纸不能因为元素总数增加而让每次平移、缩放、框选和导出都扫描或挂载全部元素。本切片将浏览器交互和服务端导出拆成明确的可见范围工作集。

## 浏览器视口裁剪

`EditorCanvas` 对当前可见图层和系统建立均匀网格空间索引。

当前 viewBox 外增加少量预取边距，只把相交候选元素挂载为 SVG DOM。以下操作使用同一索引候选集：

- 视口渲染；
- 设备端口吸附；
- junction 插入时的 connector 线段命中；
- 框选；
- 选中元素和拖动预览的强制保留。

SVG 根节点暴露以下只读诊断属性：

```text
data-visible-elements
data-rendered-elements
data-spatial-cells
```

长管线或大包围盒元素如果跨越超过 256 个索引网格，不逐格展开，而是进入全局候选集合，查询时再做包围盒相交判断。

## 导出范围

新增范围化导出接口：

```http
GET /api/v2/documents/{document_id}/export-info
GET /api/v2/documents/{document_id}/export-v2.svg
GET /api/v2/documents/{document_id}/export-v2.png
```

`range` 支持：

- `canvas`：完整文档画布；
- `content`：当前可见图层和系统中元素的内容包围盒；
- `viewport`：显式传入浏览器当前 viewBox。

内容范围示例：

```text
/api/v2/documents/{id}/export-v2.svg?range=content&padding=24
```

当前视口示例：

```text
/api/v2/documents/{id}/export-v2.svg?range=viewport&x=200&y=100&width=1200&height=700
```

PNG 示例：

```text
/api/v2/documents/{id}/export-v2.png?range=content&padding=24&scale=2
```

网页入口：

```text
右侧 → 图层/系统 → 导出范围
```

可选择完整画布、可见内容或当前视口，以及 SVG/PNG、内容边距和 PNG 比例。

旧的 `/export.svg`、`/export.png` 保留兼容；新功能和大图导出优先使用 `export-v2`。

## PNG 像素上限

默认最大输出像素数：

```text
40,000,000 pixels
```

可通过环境变量调整：

```bash
export PID_AGENT_MAX_EXPORT_PIXELS=40000000
```

当 `ceil(width × scale) × ceil(height × scale)` 超过限制时，接口返回 HTTP 413：

```json
{
  "detail": {
    "error": "export_too_large",
    "message": "PNG export exceeds the configured pixel limit",
    "requested_pixels": 92160000,
    "max_pixels": 40000000,
    "suggestions": [
      "降低 scale",
      "改用 content 或 viewport 导出范围",
      "使用 SVG 导出超大图纸"
    ]
  }
}
```

超限发生在 CairoSVG 渲染之前，不会分配超大像素缓冲区。

## SVG 大图优化

服务端 SVG 渲染会：

- 先排除隐藏图层和系统；
- 按导出范围裁剪元素；
- 仅为实际输出 connector 渲染箭头和跨线桥；
- 使用 connector 分段网格查找跨线候选，不再全量两两比较。

输出 SVG 包含：

```text
data-document-id
data-revision
data-rendered-elements
```

## 诊断日志

范围导出记录：

```text
export.completed
export.rejected
export.failed
```

主要字段包括：

- document ID 和 revision；
- SVG 或 PNG；
- canvas、content 或 viewport；
- 实际导出 bounds；
- scale、输出宽高和像素数；
- 耗时和输出字节数；
- 超限或渲染失败错误码。

## 性能基准

仓库新增可重复基准脚本：

```bash
PYTHONPATH=backend python backend/benchmarks/benchmark_large_documents.py
```

默认测试：

```text
500
1000
2500
5000 elements
```

输出指标：

- 内容包围盒计算时间；
- 完整 SVG 时间；
- 1600×900 视口 SVG 时间；
- 完整与视口 SVG 字节数；
- 视口实际渲染元素数和裁剪比例；
- Python `tracemalloc` 峰值。

可指定：

```bash
PYTHONPATH=backend python backend/benchmarks/benchmark_large_documents.py \
  --counts 500 1000 2500 5000 \
  --iterations 5 \
  --output jsonl
```

基准脚本只输出测量结果，不在仓库中预填未经当前机器实际执行的性能数字。

## 测试范围

新增测试覆盖：

- 内容包围盒排除隐藏元素；
- viewport SVG 使用指定 viewBox；
- viewport SVG 不输出远端元素；
- `export-info` 返回画布、内容范围和像素上限；
- viewport 参数不完整返回结构化 422；
- 超大 PNG 在实际渲染前返回结构化 413。

## 最终验收阶段

最终验收时运行：

```bash
pytest -q
ruff check backend
cd frontend && npm run build
PYTHONPATH=backend python backend/benchmarks/benchmark_large_documents.py --iterations 5
```

同时使用实际工程图检查：

- 平移和缩放时可见元素是否连续出现；
- 端口吸附、框选和 junction 插入是否仍准确；
- 当前视口导出与浏览器看到的范围是否一致；
- content 导出是否排除隐藏图层和系统；
- 5000 元素基准是否出现异常内存增长或不可接受的长尾耗时。
