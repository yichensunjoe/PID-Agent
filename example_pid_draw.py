#!/usr/bin/env python3
"""
AgentCAD 示例脚本 — 演示 Agent 如何通过 API 绘制 P&ID 工艺流程图

用法:
    cd src && python3 example_pid_draw.py

依赖:
    pip install requests
"""

import requests
import sys
import time

BASE = "http://localhost:8000/api/v1"


def wait_for_server(timeout=10):
    """等待服务器就绪"""
    for i in range(timeout):
        try:
            r = requests.get(f"{BASE}/symbols/library", timeout=2)
            if r.status_code == 200:
                print("✅ 服务器已就绪")
                return True
        except requests.ConnectionError:
            pass
        time.sleep(1)
    print("❌ 服务器连接失败，请确认 AgentCAD 正在运行")
    sys.exit(1)


def clear():
    """清空画布"""
    r = requests.delete(f"{BASE}/clear")
    data = r.json()
    print(f"🗑 画布已清空，剩余图元: {data['primitives_count']}")


def draw_line(x1, y1, x2, y2, color="black", label=""):
    """画管线"""
    r = requests.post(f"{BASE}/draw/line", json={
        "start": [x1, y1], "end": [x2, y2],
        "color": color, "linewidth": 1.5
    })
    return r.json()


def draw_symbol(symbol_type, x, y, label="", color="black", width=60, height=60):
    """画工业符号"""
    r = requests.post(f"{BASE}/draw/symbol", json={
        "symbol_type": symbol_type,
        "x": x, "y": y,
        "label": label,
        "color": color,
        "width": width,
        "height": height,
    })
    data = r.json()
    if data["success"]:
        name_map = {
            "ball_valve": "球阀", "butterfly_valve": "蝶阀",
            "check_valve": "止回阀", "globe_valve": "截止阀",
            "gate_valve": "闸阀", "control_valve": "调节阀",
            "temperature_indicator": "温度仪表",
            "pressure_indicator": "压力仪表",
            "flow_indicator": "流量仪表",
            "gas_tank": "储气罐", "buffer_tank": "缓冲罐",
            "purification_cabinet": "纯化柜",
            "centrifugal_pump": "离心泵", "reciprocating_pump": "往复泵",
            "fan": "风机", "high_temp_fan": "高温风机",
            "exhaust_cabinet": "排气柜", "control_cabinet": "控制柜",
            "system_interface": "系统接口",
        }
        cname = name_map.get(symbol_type, symbol_type)
        print(f"  ✅ 放置 [{cname}] {label} @ ({x}, {y})")
    return data


def draw_text(content, x, y, font_size=12, color="black"):
    """画文字"""
    r = requests.post(f"{BASE}/draw/text", json={
        "content": content, "x": x, "y": y,
        "font_size": font_size, "color": color
    })
    return r.json()


def export_svg(filename="output_pid_diagram.svg"):
    """导出 SVG"""
    r = requests.get(f"{BASE}/export/svg")
    data = r.json()
    with open(filename, "w", encoding="utf-8") as f:
        f.write(data["svg"])
    print(f"\n💾 SVG 已导出: {filename}")


def main():
    print("=" * 50)
    print("  AgentCAD — P&ID 工艺流程图绘制示例")
    print("=" * 50)

    # 等待服务器
    wait_for_server()

    # 清空画布
    clear()

    print("\n📋 开始绘制工艺流程图...")
    print("-" * 40)

    # ===== 第1步：放置储气罐 =====
    print("\n【步骤1】放置储气罐")
    draw_symbol("gas_tank", 80, 250, "TK-101", "blue", 80, 120)

    # ===== 第2步：放置管线和阀门 =====
    print("\n【步骤2】连接管线与阀门")
    draw_line(160, 310, 200, 310)  # 罐出口到阀门
    draw_symbol("ball_valve", 200, 290, "BV-101", "black", 60, 40)
    draw_line(260, 310, 300, 310)  # 阀门到泵

    # ===== 第3步：放置泵 =====
    print("\n【步骤3】放置离心泵")
    draw_symbol("centrifugal_pump", 300, 280, "P-101A", "red", 60, 60)
    draw_line(360, 310, 420, 310)  # 泵出口管线

    # ===== 第4步：放置压力表 =====
    print("\n【步骤4】安装压力表")
    draw_symbol("pressure_indicator", 440, 270, "PE-101", "green", 40, 40)
    draw_line(460, 290, 460, 310)  # 引压管

    # ===== 第5步：放置温度仪表 =====
    print("\n【步骤5】安装温度仪表")
    draw_symbol("temperature_indicator", 520, 270, "TE-101", "green", 40, 40)
    draw_line(480, 310, 520, 310)  # 管线
    draw_line(540, 310, 580, 310)  # 管线

    # ===== 第6步：放置风机 =====
    print("\n【步骤6】放置风机")
    draw_symbol("fan", 580, 280, "F-101", "orange", 60, 60)
    draw_line(640, 310, 700, 310)  # 风机出口

    # ===== 第7步：放置系统接口 =====
    print("\n【步骤7】放置系统接口")
    draw_symbol("system_interface", 700, 290, "至反应系统", "purple", 100, 40)

    # ===== 第8步：添加标题 =====
    print("\n【步骤8】添加标题")
    draw_text("工艺流程图 PFD-001", 200, 100, 18, "black")
    draw_text("设计日期: 2026-07-16", 200, 130, 12, "gray")

    # ===== 第9步：导出 =====
    print("\n" + "=" * 50)
    export_svg("output_pid_diagram.svg")

    # 查询最终状态
    r = requests.get(f"{BASE}/primitives")
    data = r.json()
    print(f"📊 最终图元总数: {data['primitives_count']}")
    print("=" * 50)


if __name__ == "__main__":
    main()
