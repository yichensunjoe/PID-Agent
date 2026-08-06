"""按 GB/T 6567.4-2008 重画阀门图例 shapes（保持 key/尺寸/端口不变），并清理缓冲罐。"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent / "backend" / "agentcad" / "data"


def line(x1, y1, x2, y2):
    return {"type": "line", "x1": x1, "y1": y1, "x2": x2, "y2": y2}


def tri(x, y, tx, ty, x2, y2, fill=None):
    s = {"type": "polyline", "points": [[x, y], [tx, ty], [x2, y2]], "closed": True}
    if fill:
        s["fill"] = fill
    return s


def circle(cx, cy, r):
    return {"type": "circle", "cx": cx, "cy": cy, "r": r}


def rect(x, y, w, h, rx=0):
    return {"type": "rect", "x": x, "y": y, "width": w, "height": h, "rx": rx}


def path(d):
    return {"type": "path", "d": d}


def txt(x, y, t, fs=12):
    return {"type": "text", "x": x, "y": y, "text": t, "font_size": fs, "anchor": "middle"}


# GB/T 6567.4-2008 shapes per symbol key.
NEW_SHAPES = {
    # 截止阀 4.1: 小圆 + 连接线
    "globe_valve": [
        line(0, 40, 22, 40), circle(35, 40, 13), line(48, 40, 70, 40),
    ],
    # 闸阀 4.2: 空心双三角对接
    "gate_valve": [
        line(0, 30, 15, 30),
        tri(15, 18, 30, 30, 15, 42),
        tri(45, 18, 30, 30, 45, 42),
        line(45, 30, 60, 30),
    ],
    # 球阀 4.4: 圆 + X 斜线
    "ball_valve": [
        line(0, 20, 16, 20),
        circle(30, 20, 14),
        line(20, 10, 40, 30),
        line(20, 30, 40, 10),
        line(44, 20, 60, 20),
    ],
    # 止回阀 4.8: 喇叭三角 + 竖线挡板
    "check_valve": [
        line(0, 25, 22, 25),
        tri(22, 13, 40, 25, 22, 37),
        line(40, 13, 40, 37),
        line(40, 25, 80, 25),
    ],
    # 蝶阀 4.5: 双弧相对
    "butterfly_valve": [
        line(0, 35, 28, 35),
        path("M 28 20 Q 40 35 28 50"),
        path("M 52 20 Q 40 35 52 50"),
        line(52, 35, 80, 35),
    ],
    # 节流阀 4.3 (针型阀采用节流阀画法): 实心黑双三角
    "needle_valve": [
        line(0, 45, 17, 45),
        tri(17, 32, 35, 45, 17, 58, fill="#111827"),
        tri(53, 32, 35, 45, 53, 58, fill="#111827"),
        line(53, 45, 70, 45),
    ],
    # 旋塞阀 4.7: 沙漏 + 顶部 T 形横杆
    "plug_valve": [
        line(0, 30, 17, 30),
        tri(17, 18, 35, 30, 17, 42),
        tri(53, 18, 35, 30, 53, 42),
        line(53, 30, 70, 30),
        line(35, 18, 35, 8),
        line(25, 8, 45, 8),
    ],
    # 隔膜阀 4.6: 沙漏 + 顶部小横矩形
    "diaphragm_valve": [
        line(0, 42, 17, 42),
        tri(17, 30, 35, 42, 17, 54),
        tri(53, 30, 35, 42, 53, 54),
        line(53, 42, 70, 42),
        line(35, 30, 35, 16),
        rect(26, 6, 18, 10),
    ],
    # 三通阀 4.14: 三个三角汇聚中心
    "three_way_valve": [
        line(0, 35, 15, 35),
        tri(15, 23, 35, 35, 15, 47),
        tri(55, 23, 35, 35, 55, 47),
        tri(23, 60, 35, 35, 47, 60),
        line(55, 35, 70, 35),
        line(35, 60, 35, 75),
    ],
    # 安全阀(弹簧式) 4.9: 沙漏(上下) + 左上弹簧折线 + 箭头；端口 下进/右出
    "safety_relief_valve": [
        tri(22, 45, 48, 45, 35, 60),
        tri(22, 75, 48, 75, 35, 60),
        line(35, 75, 35, 90),
        line(48, 60, 80, 55),
        line(22, 48, 14, 38),
        line(14, 38, 20, 30),
        line(20, 30, 12, 20),
        line(12, 20, 18, 10),
        tri(18, 10, 24, 16, 14, 18),
    ],
    # 调节阀（6567.4 未含，按行业画法）: 沙漏 + 顶部膜头圆
    "control_valve": [
        line(0, 55, 17, 55),
        tri(17, 42, 35, 55, 17, 68),
        tri(53, 42, 35, 55, 53, 68),
        line(53, 55, 70, 55),
        line(35, 42, 35, 26),
        circle(35, 16, 10),
    ],
    # 电动阀（6567.4 未含，按行业画法）: 沙漏 + 顶部执行机构矩形
    "motor_operated_valve": [
        line(0, 58, 17, 58),
        tri(17, 46, 35, 58, 17, 70),
        tri(53, 46, 35, 58, 53, 70),
        line(53, 58, 70, 58),
        line(35, 46, 35, 24),
        rect(23, 10, 24, 14),
    ],
    # 电磁阀（6567.4 未含，按行业画法）: 沙漏 + 顶部矩形 + S
    "solenoid_valve": [
        line(0, 58, 17, 58),
        tri(17, 46, 35, 58, 17, 70),
        tri(53, 46, 35, 58, 53, 70),
        line(53, 58, 70, 58),
        line(35, 46, 35, 24),
        rect(23, 10, 24, 14),
        txt(35, 20, "S", 11),
    ],
    # 疏水阀 4.12: 沙漏 + 左右竖线外框
    "steam_trap": [
        line(0, 20, 35, 20),
        tri(35, 10, 50, 20, 35, 30),
        tri(65, 10, 50, 20, 65, 30),
        line(65, 20, 100, 20),
        line(28, 6, 28, 34),
        line(72, 6, 72, 34),
    ],
    # 缓冲罐: 干净胶囊轮廓（删除内部重叠线）
    "buffer_tank": [
        path("M 0 35 A 35 35 0 0 1 70 35 L 70 65 A 35 35 0 0 1 0 65 Z"),
    ],
}

NEW_DESC = {
    "globe_valve": "截止阀。GB/T 6567.4-2008 图形：小圆阀体 + 两端连接线。",
    "gate_valve": "闸阀。GB/T 6567.4-2008 图形：两个空心三角形对接。",
    "ball_valve": "球阀。GB/T 6567.4-2008 图形：圆形 + 两条对角斜线。",
    "check_valve": "止回阀。GB/T 6567.4-2008 图形：喇叭三角 + 竖线挡板，流向左→右。",
    "butterfly_valve": "蝶阀。GB/T 6567.4-2008 图形：两条相对弧线。",
    "needle_valve": "针型阀（采用 GB/T 6567.4-2008 节流阀画法）：两个实心黑色三角形对接。",
    "plug_valve": "旋塞阀。GB/T 6567.4-2008 图形：沙漏 + 顶部 T 形横杆。",
    "diaphragm_valve": "隔膜阀。GB/T 6567.4-2008 图形：沙漏 + 顶部小横矩形手轮。",
    "three_way_valve": "三通阀。GB/T 6567.4-2008 图形：三个三角形顶点汇聚中心。",
    "safety_relief_valve": "安全阀（弹簧式）。GB/T 6567.4-2008 图形：沙漏 + 左上弹簧折线 + 箭头。",
    "control_valve": "调节阀。沙漏 + 顶部膜头圆（GB/T 6567.4 未含，按行业画法）。",
    "motor_operated_valve": "电动阀。沙漏 + 顶部执行机构矩形（GB/T 6567.4 未含，按行业画法）。",
    "solenoid_valve": "电磁阀。沙漏 + 顶部矩形 + S（GB/T 6567.4 未含，按行业画法）。",
    "steam_trap": "疏水阀。GB/T 6567.4-2008 图形：沙漏 + 左右竖线外框。",
    "buffer_tank": "竖直胶囊形缓冲罐（矩形罐体上下圆弧，无内部线）。左右两端各一个接口。",
}


def dump_symbol(sym, indent=4):
    pad = " " * indent
    lines = [pad + "{"]
    keys = list(sym.keys())
    for i, k in enumerate(keys):
        v = sym[k]
        comma = "," if i < len(keys) - 1 else ""
        if isinstance(v, list) and v and isinstance(v[0], dict):
            lines.append(pad + f'  "{k}": [')
            for j, item in enumerate(v):
                icomma = "," if j < len(v) - 1 else ""
                lines.append(pad + "    " + json.dumps(item, ensure_ascii=False) + icomma)
            lines.append(pad + "  ]" + comma)
        else:
            lines.append(pad + f'  "{k}": {json.dumps(v, ensure_ascii=False)}{comma}')
    lines.append(pad + "}")
    return "\n".join(lines)


def process(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = []
    for sym in data["symbols"]:
        key = sym["key"]
        if key in NEW_SHAPES:
            sym["shapes"] = NEW_SHAPES[key]
            if key in NEW_DESC:
                sym["description"] = NEW_DESC[key]
            changed.append(key)
    if not changed:
        return []
    # re-serialize preserving the file's mixed format (top-level indent=2, array items single-line)
    out = ["{"]
    top_keys = list(data.keys())
    for i, k in enumerate(top_keys):
        comma = "," if i < len(top_keys) - 1 else ""
        v = data[k]
        if k == "symbols":
            out.append('  "symbols": [')
            for j, sym in enumerate(v):
                scomma = "," if j < len(v) - 1 else ""
                out.append(dump_symbol(sym) + scomma)
            out.append("  ]" + comma)
        elif isinstance(v, dict):
            inner = json.dumps(v, ensure_ascii=False, indent=2)
            inner_lines = inner.split("\n")
            first = f'  "{k}": ' + inner_lines[0]
            rest = ["  " + ln for ln in inner_lines[1:]]
            out.append("\n".join([first, *rest]) + comma)
        else:
            out.append(f'  "{k}": ' + json.dumps(v, ensure_ascii=False) + comma)
    out.append("}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return changed


if __name__ == "__main__":
    for name in ["symbols.json", "standard_symbols.json"]:
        changed = process(ROOT / name)
        print(name, "updated:", changed)
