# AgentCAD API 接口文档 v2

## 概述

AgentCAD 提供 RESTful API，供 AI Agent 通过 HTTP 请求驱动绘图。所有接口基于 `http://localhost:8000/api/v1`。

## 画图接口

### 1. 画直线 `POST /draw/line`

```json
{
  "start": [100, 100],
  "end": [300, 200],
  "color": "red",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 2. 画圆 `POST /draw/circle`

```json
{
  "center": [400, 300],
  "radius": 50,
  "color": "blue",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 3. 画矩形 `POST /draw/rectangle`

```json
{
  "x1": 100, "y1": 100,
  "x2": 300, "y2": 250,
  "color": "green",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 4. 画多段线 `POST /draw/polyline`

```json
{
  "points": [[50,50],[150,50],[150,200],[50,200],[50,50]],
  "color": "green",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 5. 画圆弧 `POST /draw/arc`

```json
{
  "center": [400, 300],
  "radius": 80,
  "start_angle": 0,
  "end_angle": 3.14159,
  "color": "black",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 6. 添加文字 `POST /draw/text`

```json
{
  "content": "Hello",
  "x": 100,
  "y": 50,
  "font_size": 16,
  "color": "black",
  "layer": "default"
}
```

### 7. 批量画图 `POST /draw/batch`

```json
{
  "operations": [
    {"type": "line", "start": [0,0], "end": [100,100]},
    {"type": "circle", "center": [50,50], "radius": 20}
  ]
}
```

## 编辑接口

### 8. 查询所有图元 `GET /primitives`

返回所有可见图元列表。

### 9. 查询单条图元 `GET /primitives/{id}`

通过图元 ID 查询详细信息。

### 10. 删除图元 `DELETE /primitives/{id}`

删除指定 ID 的图元。

### 11. 撤销 `POST /undo`

撤销上一步操作。

### 12. 重做 `POST /redo`

重做被撤销的操作。

### 13. 清空画布 `DELETE /clear`

清空所有图元和历史。

## 图层管理

### 14. 列出图层 `GET /layers`

### 15. 创建图层 `POST /layers`

```json
{"name": "annotations", "visible": true}
```

### 16. 删除图层 `DELETE /layers/{name}`

### 17. 切换图层可见性 `PATCH /layers/{name}/visibility`

## 导出

### 18. 导出 SVG `GET /export/svg`

返回 SVG 格式的矢量图字符串。

## 支持的顏色

`black`, `red`, `blue`, `green`, `yellow`, `cyan`, `magenta`, `orange`, `purple`, `gray`, `white`

## Agent 调用最佳实践

1. **批量操作优先** — 使用 `/draw/batch` 减少网络请求
2. **按需查询** — 画完后调用 `/primitives` 确认结果
3. **图层隔离** — 复杂图纸用不同图层区分元素
4. **及时导出** — 完成后调用 `/export/svg` 获取可视化结果
5. **错误处理** — 检查响应中的 `success` 字段
