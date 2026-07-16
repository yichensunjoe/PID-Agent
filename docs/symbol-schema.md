# 单位图例 Schema

图例是独立于 Python 代码的 JSON 数据。一个文件可以包含多个符号：

```json
{
  "symbols": [
    {
      "key": "company_filter",
      "name": "单位标准过滤器",
      "category": "过滤设备",
      "description": "用于工艺气体精过滤，默认流向从左到右。",
      "width": 100,
      "height": 60,
      "ports": [
        {"id": "in", "name": "入口", "x": 0, "y": 30, "direction": "in"},
        {"id": "out", "name": "出口", "x": 100, "y": 30, "direction": "out"},
        {"id": "drain", "name": "排污", "x": 50, "y": 60, "direction": "out"}
      ],
      "shapes": [
        {"type": "line", "x1": 0, "y1": 30, "x2": 20, "y2": 30},
        {"type": "rect", "x": 20, "y": 5, "width": 60, "height": 50, "rx": 4},
        {"type": "line", "x1": 20, "y1": 10, "x2": 80, "y2": 50},
        {"type": "line", "x1": 80, "y1": 30, "x2": 100, "y2": 30},
        {"type": "line", "x1": 50, "y1": 55, "x2": 50, "y2": 60}
      ],
      "metadata": {
        "standard": "company-internal",
        "revision": "2026-A"
      }
    }
  ]
}
```

## 必填字段

| 字段 | 说明 |
|---|---|
| `key` | 稳定、唯一、适合 Agent 使用的英文标识。已有文档会引用它。 |
| `name` | 人员界面展示名称。 |
| `category` | 图例面板分类。 |
| `width` / `height` | 图例自身局部坐标范围。 |
| `shapes` | SVG 风格的声明式基础形状。 |

## shapes

支持：

### line

```json
{"type":"line","x1":0,"y1":20,"x2":40,"y2":20}
```

### polyline / polygon

```json
{"type":"polyline","points":[[0,0],[40,20],[0,40]],"closed":true}
```

### rect

```json
{"type":"rect","x":0,"y":0,"width":80,"height":50,"rx":4}
```

### circle

```json
{"type":"circle","cx":25,"cy":25,"r":20}
```

### path

```json
{"type":"path","d":"M 0 20 Q 40 0 80 20"}
```

### text

```json
{"type":"text","x":25,"y":30,"text":"PI","font_size":14,"anchor":"middle"}
```

## ports

端口是 Agent 自动连接和后续吸附功能的关键。

```json
{
  "id": "out",
  "name": "出口",
  "x": 100,
  "y": 30,
  "direction": "out",
  "medium": "process"
}
```

`direction` 支持：

- `in`
- `out`
- `bidirectional`
- `none`

`medium` 可以使用单位自己的分类，例如：

- `process`
- `instrument_air`
- `cooling_water`
- `signal`
- `electrical`

## 覆盖规则

`SymbolRegistry` 按加载顺序合并图例。后加载文件中的相同 `key` 会覆盖前面的定义，因此可以：

1. 保留内置图例作为开发占位；
2. 加载单位级图例覆盖内置图例；
3. 再加载项目级图例覆盖单位默认值。

## 从参考图片替换

收到单位图例参考图后，建议按以下步骤处理：

1. 确认每个符号名称和语义；
2. 确认连接口及默认流向；
3. 把图片重绘为标准局部坐标；
4. 保持稳定 `key`；
5. 加入图例预览和 SVG 导出测试；
6. 用单位典型流程做一次 Agent 生成验收。
