#!/usr/bin/env python3
"""
AgentCAD Agent 使用示例

演示如何通过 HTTP API 驱动 AgentCAD 画图。
这就是 AI Agent 应该使用的调用方式。
"""

import json
import urllib.request


BASE_URL = "http://localhost:8000/api/v1"


def post(path: str, data: dict) -> dict:
    """发送 POST 请求"""
    body = json.dumps(data).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def delete(path: str) -> dict:
    """发送 DELETE 请求"""
    req = urllib.request.Request(f"{BASE_URL}{path}", method="DELETE")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


def get(path: str) -> dict:
    """发送 GET 请求"""
    req = urllib.request.Request(f"{BASE_URL}{path}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())


# ============================================================
# 示例 1: 画一个简单的房屋图形
# ============================================================
def draw_house():
    """用基本图元组合画一个房子"""
    print("🏠 绘制房屋图形...")

    # 画地基（矩形）
    post("/draw/rectangle", {
        "x1": 200, "y1": 400, "x2": 400, "y2": 550,
        "color": "gray", "linewidth": 2,
    })
    print("  ✓ 地基")

    # 画门（矩形）
    post("/draw/rectangle", {
        "x1": 270, "y1": 450, "x2": 330, "y2": 550,
        "color": "brown", "linewidth": 2,
    })
    print("  ✓ 门")

    # 画窗户（矩形）
    post("/draw/rectangle", {
        "x1": 220, "y1": 430, "x2": 255, "y2": 465,
        "color": "skyblue", "linewidth": 1.5,
    })
    post("/draw/line", {
        "start": [237.5, 430], "end": [237.5, 465],
        "color": "black", "linewidth": 1,
    })
    post("/draw/line", {
        "start": [220, 447.5], "end": [255, 447.5],
        "color": "black", "linewidth": 1,
    })
    print("  ✓ 窗户")

    # 画屋顶（三角形 = 三条线）
    post("/draw/line", {
        "start": [180, 400], "end": [300, 280],
        "color": "darkred", "linewidth": 2.5,
    })
    post("/draw/line", {
        "start": [300, 280], "end": [420, 400],
        "color": "darkred", "linewidth": 2.5,
    })
    post("/draw/line", {
        "start": [180, 400], "end": [420, 400],
        "color": "darkred", "linewidth": 2.5,
    })
    print("  ✓ 屋顶")

    # 添加文字标注
    post("/draw/text", {
        "content": "My House", "x": 260, "y": 250,
        "font_size": 16, "color": "black",
    })
    print("  ✓ 标注")

    # 画烟囱
    post("/draw/rectangle", {
        "x1": 350, "y1": 280, "x2": 380, "y2": 350,
        "color": "brown", "linewidth": 2,
    })
    print("  ✓ 烟囱")

    result = get("/primitives")
    print(f"\n✅ 房屋绘制完成！共 {result['primitives_count']} 个图元")


# ============================================================
# 示例 2: 画一个齿轮形状
# ============================================================
def draw_gear():
    """用多段线画一个简单的齿轮"""
    import math

    print("\n⚙️ 绘制齿轮...")

    # 清空画布
    delete("/clear")

    # 中心齿轮圆
    post("/draw/circle", {
        "center": [400, 360], "radius": 80,
        "color": "steelblue", "linewidth": 2,
    })
    print("  ✓ 中心圆")

    # 齿
    num_teeth = 12
    outer_r = 100
    inner_r = 80
    for i in range(num_teeth):
        angle1 = i * 2 * math.pi / num_teeth
        angle2 = (i + 0.3) * 2 * math.pi / num_teeth
        angle3 = (i + 0.7) * 2 * math.pi / num_teeth
        angle4 = (i + 1) * 2 * math.pi / num_teeth

        # 齿的两侧线
        post("/draw/line", {
            "start": [400 + inner_r * math.cos(angle2), 360 + inner_r * math.sin(angle2)],
            "end": [400 + outer_r * math.cos(angle2), 360 + outer_r * math.sin(angle2)],
            "color": "steelblue", "linewidth": 2,
        })
        post("/draw/line", {
            "start": [400 + outer_r * math.cos(angle3), 360 + outer_r * math.sin(angle3)],
            "end": [400 + inner_r * math.cos(angle3), 360 + inner_r * math.sin(angle3)],
            "color": "steelblue", "linewidth": 2,
        })

    # 中心孔
    post("/draw/circle", {
        "center": [400, 360], "radius": 20,
        "color": "white", "linewidth": 2,
    })
    print("  ✓ 齿 + 中心孔")

    # 键槽线
    post("/draw/line", {
        "start": [400, 340], "end": [400, 320],
        "color": "black", "linewidth": 1.5,
    })
    print("  ✓ 键槽")

    result = get("/primitives")
    print(f"\n✅ 齿轮绘制完成！共 {result['primitives_count']} 个图元")


# ============================================================
# 示例 3: 画一个坐标系
# ============================================================
def draw_coordinate_system():
    """画一个标准的二维坐标系"""
    print("\n📐 绘制坐标系...")

    delete("/clear")

    # X 轴
    post("/draw/line", {
        "start": [50, 360], "end": [700, 360],
        "color": "black", "linewidth": 2,
    })
    # Y 轴
    post("/draw/line", {
        "start": [400, 50], "end": [400, 650],
        "color": "black", "linewidth": 2,
    })

    # 箭头
    post("/draw/line", {
        "start": [680, 350], "end": [700, 360],
        "color": "black", "linewidth": 2,
    })
    post("/draw/line", {
        "start": [390, 70], "end": [400, 50],
        "color": "black", "linewidth": 2,
    })

    # 刻度线
    for i in range(-5, 6):
        if i == 0:
            continue
        x = 400 + i * 60
        post("/draw/line", {
            "start": [x, 350], "end": [x, 370],
            "color": "gray", "linewidth": 1,
        })
        post("/draw/text", {
            "content": str(i), "x": x - 5, "y": 395,
            "font_size": 12, "color": "gray",
        })

    for i in range(-5, 6):
        if i == 0:
            continue
        y = 360 - i * 60
        post("/draw/line", {
            "start": [390, y], "end": [410, y],
            "color": "gray", "linewidth": 1,
        })
        post("/draw/text", {
            "content": str(i), "x": 415, "y": y + 5,
            "font_size": 12, "color": "gray",
        })

    # 原点标注
    post("/draw/text", {
        "content": "O", "x": 405, "y": 385,
        "font_size": 14, "color": "black",
    })
    # 轴标签
    post("/draw/text", {
        "content": "X", "x": 680, "y": 340,
        "font_size": 16, "color": "black",
    })
    post("/draw/text", {
        "content": "Y", "x": 380, "y": 60,
        "font_size": 16, "color": "black",
    })

    # 画一条正弦曲线（用多段线近似）
    import math
    points = []
    for i in range(-50, 51):
        x = 400 + i * 6
        y = 360 - 80 * math.sin(i * math.pi / 25)
        points.append([x, y])
    post("/draw/polyline", {
        "points": points, "color": "red", "linewidth": 2,
    })

    # 标注
    post("/draw/text", {
        "content": "y = sin(x)", "x": 600, "y": 280,
        "font_size": 14, "color": "red",
    })

    result = get("/primitives")
    print(f"\n✅ 坐标系绘制完成！共 {result['primitives_count']} 个图元")


# ============================================================
# 主程序
# ============================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  AgentCAD Agent 使用示例")
    print("=" * 50)

    draw_house()
    draw_gear()
    draw_coordinate_system()

    print("\n" + "=" * 50)
    print("  所有示例完成！")
    print("=" * 50)
