# 工程 DXF 导出

P&ID-Agent 提供服务端生成的 ASCII DXF，目标版本为 AutoCAD 2013 的 `AC1027`。导出不依赖 AutoCAD、LibreCAD 或浏览器打印能力，也不修改文档 revision。当前切片只负责 CAD 交换导出，不提供 DXF 导入或 CAD 内编辑回写。

## 浏览器操作

1. 打开文档并切换到右侧 **图层/系统** 面板。
2. 在 **导出与打印** 中选择 `DXF`。
3. 选择导出范围、CAD 单位和坐标比例。
4. 点击 **导出 DXF**。

下载文件保留当前可见图层和系统中的工程元素。隐藏图层或隐藏系统不会进入 DXF。

## 坐标与单位

编辑器坐标以左上角为原点，Y 轴向下；CAD 模型空间以所选导出范围的左下角为原点，Y 轴向上。转换规则为：

```text
cad_x = (document_x - bounds.x) * scale
cad_y = (bounds.y + bounds.height - document_y) * scale
```

`units` 写入 DXF `$INSUNITS`：

| 参数 | `$INSUNITS` | 含义 |
|---|---:|---|
| `unitless` | 0 | 无单位 |
| `in` | 1 | 英寸 |
| `ft` | 2 | 英尺 |
| `mm` | 4 | 毫米 |
| `cm` | 5 | 厘米 |
| `m` | 6 | 米 |

`scale` 必须大于 0 且不超过 1000。它只控制坐标和文字/半径尺寸换算，不改变文档内容。例如文档坐标按毫米使用时选择 `mm + 1`；要按米交换可选择 `m + 0.001`。

## 图层与实体映射

文档图层按文档顺序映射为稳定 DXF layer。名称使用 `PID_` 前缀，非 ASCII 字符和 CAD 不安全字符会被规范化；重名使用确定性数字后缀。未包含任何可见元素的图层不会创建。

主要映射：

- 直线：`LINE`；
- 折线、矩形、连接线和符号轮廓：`LWPOLYLINE`；
- 圆和节点：`CIRCLE`；
- 非等比缩放的符号圆：`ELLIPSE`；
- 标签和工程文字：`TEXT`，文字样式使用 Noto Sans CJK；
- 连接线流向箭头：`SOLID`。

线色使用 DXF true-color，虚线使用 `DASHED` linetype。设备、连接和注释复用现有文档模型与符号定义，不另建一套 CAD 图形模型。

## 工程 XDATA

每个实体使用已注册的 `PID_AGENT` APPID 写入 XDATA。字段包括：

```text
element_id
element_type
system_id
name
```

连接线还包含 routing、flow_direction、crossing_style、process_tag、medium、nominal_diameter，以及已绑定的 source/target。XDATA 用于下游识别和审计，不代表支持 DXF 回导。

## REST API

```text
GET /api/v2/documents/{document_id}/export-v2.dxf
```

查询参数：

```text
range=content|canvas|viewport
padding=24
units=unitless|mm|cm|m|in|ft
scale=1
```

`viewport` 还需要 `x`、`y`、`width`、`height`。响应类型为 `application/dxf`，响应头包括：

```text
X-PID-Agent-DXF-Version
X-PID-Agent-DXF-Entity-Count
X-PID-Agent-DXF-Layer-Count
X-PID-Agent-DXF-Units
X-PID-Agent-DXF-Scale
```

无效单位、比例、范围或非有限几何返回 HTTP 422。环境变量 `PID_AGENT_MAX_DXF_ENTITIES` 控制实体上限，默认 100000，最小有效配置为 1000。超限返回 HTTP 413，不生成部分文件。

## Python Client

```python
from agentcad.client import AgentCADClient

with AgentCADClient("http://127.0.0.1:8000/api/v2") as client:
    client.export_dxf(
        "doc_123",
        "drawing.dxf",
        export_range="content",
        units="m",
        scale=0.001,
    )
```

`client.export(document_id, "dxf", destination)` 使用 `content`、`mm`、比例 1 的默认配置。

## 验证与互操作

自动测试检查 HEADER、TABLES、BLOCKS 和 ENTITIES 段、`AC1027`、`$INSUNITS`、稳定图层、全部实体类型、Unicode 文字、工程 XDATA、隐藏图层过滤、坐标翻转、实体上限、REST、Python Client 和浏览器下载。

生成结果还会由独立的 `ezdxf` 解析器读取并执行 audit，确保不是仅能被项目自身的宽松解析代码接受。涉及互操作的有意变更仍应在目标 CAD 应用中抽查：

- 图层名称和可见性；
- 设备轮廓、管线路径和流向；
- 中文/英文文字；
- 单位、比例和左下角原点；
- `PID_AGENT` XDATA；
- 超大图纸拆分策略。
