# AgentCAD — AI Agent 操作手册

## 概述

AgentCAD 是一个轻量级 CAD 绘图系统，专为 AI Agent 设计。Agent 可以通过 RESTful API 直接操作画布，绘制工程图纸、P&ID 流程图、电气图等。

**服务地址:** `http://localhost:8000`  
**API 前缀:** `/api/v1`  
**前端界面:** `http://localhost:8000`

---

## 基础画图接口

### 画直线
```
POST /api/v1/draw/line
Content-Type: application/json

{
  "start": [100, 100],
  "end": [300, 100],
  "color": "black",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 画圆
```
POST /api/v1/draw/circle
Content-Type: application/json

{
  "center": [200, 200],
  "radius": 50,
  "color": "red",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 画矩形
```
POST /api/v1/draw/rectangle
Content-Type: application/json

{
  "x1": 100,
  "y1": 100,
  "x2": 300,
  "y2": 200,
  "color": "black",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 画多段线
```
POST /api/v1/draw/polyline
Content-Type: application/json

{
  "points": [[100,100], [200,80], [300,120], [400,90]],
  "color": "blue",
  "linewidth": 1.5,
  "layer": "default"
}
```

### 画圆弧
```
POST /api/v1/draw/arc
Content-Type: application/json

{
  "center": [200, 200],
  "radius": 60,
  "start_angle": 0,
  "end_angle": 1.57,
  "color": "black",
  "linewidth": 1.0,
  "layer": "default"
}
```

### 写文字
```
POST /api/v1/draw/text
Content-Type: application/json

{
  "content": "管道 PN100",
  "x": 150,
  "y": 250,
  "font_size": 14,
  "color": "black",
  "layer": "default"
}
```

---

## 工业符号接口（P&ID 专用）

### 创建工业符号
```
POST /api/v1/draw/symbol
Content-Type: application/json

{
  "symbol_type": "ball_valve",
  "x": 100,
  "y": 100,
  "label": "BV-101",
  "color": "black",
  "linewidth": 1.0,
  "layer": "default",
  "rotation": 0,
  "width": 60,
  "height": 40
}
```

### 可用符号类型

| 分类 | symbol_type | 中文名称 |
|------|-------------|----------|
| **阀门** | `ball_valve` | 球阀 |
| | `butterfly_valve` | 蝶阀 |
| | `check_valve` | 止回阀 |
| | `globe_valve` | 截止阀 |
| | `gate_valve` | 闸阀 |
| | `control_valve` | 调节阀 |
| **仪表** | `temperature_indicator` | 温度仪表 |
| | `pressure_indicator` | 压力仪表 |
| | `flow_indicator` | 流量仪表 |
| **罐体** | `gas_tank` | 储气罐 |
| | `buffer_tank` | 缓冲罐 |
| | `purification_cabinet` | 纯化柜 |
| **泵** | `centrifugal_pump` | 离心泵 |
| | `reciprocating_pump` | 往复泵 |
| **风机** | `fan` | 风机 |
| | `high_temp_fan` | 高温风机 |
| **柜体** | `exhaust_cabinet` | 排气柜 |
| | `control_cabinet` | 控制柜 |
| **系统接口** | `system_interface` | 系统接口 |

---

## 批量操作

### 批量画图
```
POST /api/v1/draw/batch
Content-Type: application/json

{
  "operations": [
    {"type": "line", "start": [0, 0], "end": [100, 100], "color": "black"},
    {"type": "circle", "center": [200, 200], "radius": 30, "color": "red"},
    {"type": "industrial_symbol", "symbol_type": "ball_valve", "x": 300, "y": 100, "label": "BV-001"}
  ]
}
```

---

## 查询与管理

### 列出所有图元
```
GET /api/v1/primitives
```

### 查询单个图元
```
GET /api/v1/primitives/{primitive_id}
```

### 删除图元
```
DELETE /api/v1/primitives/{primitive_id}
```

### 获取完整场景
```
GET /api/v1/scene
```

### 撤销 / 重做
```
POST /api/v1/undo
POST /api/v1/redo
```

### 清空画布
```
DELETE /api/v1/clear
```

---

## 图层管理

### 列出图层
```
GET /api/v1/layers
```

### 创建图层
```
POST /api/v1/layers
Content-Type: application/json

{"name": "pipes", "visible": true}
```

### 删除图层
```
DELETE /api/v1/layers/{name}
```

### 切换图层可见性
```
PATCH /api/v1/layers/{name}/visibility
```

---

## 导出

### 导出 SVG
```
GET /api/v1/export/svg
```
返回 SVG 字符串，可直接保存为 `.svg` 文件。

---

## 示例：Agent 绘制 P&ID 流程图

以下是一个完整的 Agent 操作示例，绘制一个简单的工艺流程：

```python
import requests

BASE = "http://localhost:8000"

# 清空画布
requests.delete(f"{BASE}/api/v1/clear")

# 1. 画储气罐
requests.post(f"{BASE}/api/v1/draw/symbol", json={
    "symbol_type": "gas_tank", "x": 100, "y": 200,
    "label": "TK-101", "width": 80, "height": 120
})

# 2. 画离心泵
requests.post(f"{BASE}/api/v1/draw/symbol", json={
    "symbol_type": "centrifugal_pump", "x": 250, "y": 230,
    "label": "P-101A"
})

# 3. 画球阀
requests.post(f"{BASE}/api/v1/draw/symbol", json={
    "symbol_type": "ball_valve", "x": 200, "y": 255,
    "label": "BV-101"
})

# 4. 画管线（连接）
requests.post(f"{BASE}/api/v1/draw/line", json={
    "start": [180, 260], "end": [250, 260], "color": "black"
})
requests.post(f"{BASE}/api/v1/draw/line", json={
    "start": [310, 260], "end": [400, 260], "color": "black"
})

# 5. 画压力表
requests.post(f"{BASE}/api/v1/draw/symbol", json={
    "symbol_type": "pressure_indicator", "x": 420, "y": 220,
    "label": "PE-101"
})

# 6. 画管线连接压力表
requests.post(f"{BASE}/api/v1/draw/line", json={
    "start": [450, 240], "end": [450, 220], "color": "black"
})

# 7. 画系统接口
requests.post(f"{BASE}/api/v1/draw/symbol", json={
    "symbol_type": "system_interface", "x": 500, "y": 240,
    "label": "至下游系统", "width": 100, "height": 40
})

# 8. 导出
resp = requests.get(f"{BASE}/api/v1/export/svg")
with open("pid_diagram.svg", "w") as f:
    f.write(resp.json()["svg"])

print("P&ID 流程图绘制完成！")
```

---

## 坐标系说明

- 画布默认大小: 1280 × 720 像素
- 原点 (0, 0) 在左上角
- X 轴向右为正，Y 轴向下为正
- 所有坐标单位为像素

## 颜色枚举

`black`, `red`, `blue`, `green`, `yellow`, `cyan`, `magenta`, `orange`, `purple`, `gray`
