# AgentCAD v2 — AI Agent 驱动的轻量级 CAD 系统

> 一个面向 AI Agent 的 2D 绘图引擎，提供 REST API + 交互式前端。  
> 可以像 AutoCAD 一样画图、编辑、移动、旋转，同时开放 API 让 Agent 自动化操作。

## 🚀 快速开始

```bash
cd src
pip install fastapi uvicorn python-multipart
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

打开浏览器访问 `http://localhost:8000`

## ✨ v2 新增功能

### 交互式前端
- **🖱️ 选择工具** — 点击选中图元，拖拽移动
- **↔️ 平移画布** — 空格键 + 拖拽，或中键拖拽
- **🔍 滚轮缩放** — 以鼠标位置为中心缩放
- **📦 框选多选** — 点击空白区域拖拽框选
- **⌨️ 键盘操作** — Delete 删除、Ctrl+Z 撤销、Ctrl+Y 重做、方向键微调
- **✏️ 多段线闭合** — 双击或右键闭合多段线
- **🎯 吸附网格** — 自动吸附到网格点
- **📐 变换手柄** — 选中图元显示虚线框和变换手柄
- **📊 坐标追踪** — 实时显示光标坐标和缩放比例

### Agent API
- 17 个 REST 端点，支持所有图元操作
- 批量画图接口，减少请求次数
- SVG 导出，方便 Agent 获取可视化结果
- 完整的撤销/重做历史

## 📡 API 接口一览

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/draw/line` | 画直线 |
| POST | `/api/v1/draw/circle` | 画圆 |
| POST | `/api/v1/draw/rectangle` | 画矩形 |
| POST | `/api/v1/draw/polyline` | 画多段线 |
| POST | `/api/v1/draw/arc` | 画圆弧 |
| POST | `/api/v1/draw/text` | 添加文字 |
| POST | `/api/v1/draw/batch` | 批量画图 |
| DELETE | `/api/v1/primitives/{id}` | 删除图元 |
| GET | `/api/v1/primitives/{id}` | 查询图元 |
| GET | `/api/v1/primitives` | 查询所有图元 |
| GET | `/api/v1/scene` | 获取完整场景 |
| POST | `/api/v1/undo` | 撤销 |
| POST | `/api/v1/redo` | 重做 |
| DELETE | `/api/v1/clear` | 清空画布 |
| GET | `/api/v1/layers` | 列出图层 |
| POST | `/api/v1/layers` | 创建图层 |
| GET | `/api/v1/export/svg` | 导出 SVG |

## 📁 项目结构

```
P001-AgentCAD/
├── src/
│   ├── engine/
│   │   ├── primitives.py    ← 6 种图元定义
│   │   ├── layer.py         ← 图层管理
│   │   └── canvas.py        ← 画布/场景控制器
│   ├── api/
│   │   ├── routes.py        ← REST API 路由
│   │   └── schemas.py       ← 请求/响应模型
│   ├── frontend/
│   │   ├── index.html       ← 主页面
│   │   ├── css/style.css    ← 样式
│   │   └── js/app.js        ← 前端交互逻辑
│   └── server.py            ← 应用入口
├── tests/
│   └── agent_example.py     ← Agent 调用示例
├── docs/
│   └── API_REFERENCE.md     ← 接口文档
└── logs/
    └── REUSE_AND_PITFALL.md ← 经验沉淀
```

## 🤖 Agent 使用示例

```python
import requests

BASE = "http://localhost:8000/api/v1"

# 画一个房子
requests.post(f"{BASE}/draw/line", json={
    "start": [200, 400], "end": [400, 280], "color": "darkred", "linewidth": 2.5
})
requests.post(f"{BASE}/draw/rectangle", json={
    "x1": 200, "y1": 400, "x2": 400, "y2": 550, "color": "gray"
})

# 批量画图
requests.post(f"{BASE}/draw/batch", json={
    "operations": [
        {"type": "circle", "center": [300, 300], "radius": 30, "color": "blue"},
        {"type": "text", "content": "Hello!", "x": 250, "y": 250, "color": "black"}
    ]
})

# 导出 SVG
svg = requests.get(f"{BASE}/export/svg").json()["svg"]
```

## 🛠️ 技术栈

- **后端**: Python 3.9+ / FastAPI / Uvicorn
- **前端**: Vanilla JavaScript / HTML5 Canvas
- **图元**: Line, Circle, Rectangle, Polyline, Arc, Text
- **导出**: SVG

## 📝 License

MIT
