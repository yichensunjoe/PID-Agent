"""
工业符号库 — P&ID 风格的标准设备与仪表符号

包含：
- 阀门类：球阀、蝶阀、止回阀、调节阀、截止阀
- 仪表类：温度计、压力表、流量计
- 罐体类：储气罐、缓冲罐、纯化柜
- 泵类：离心泵、往复泵
- 风机类：普通风机、高温风机
- 柜体类：排气柜、控制柜
- 系统接口：带箭头的长方形（系统边界标记）
"""

from __future__ import annotations

import uuid
import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple, Dict, Optional


class Color(str, Enum):
    RED = "red"
    BLUE = "blue"
    GREEN = "green"
    BLACK = "black"
    WHITE = "white"
    YELLOW = "yellow"
    CYAN = "cyan"
    MAGENTA = "magenta"
    ORANGE = "orange"
    PURPLE = "purple"
    GRAY = "gray"


@dataclass
class Primitive(ABC):
    """所有图元的抽象基类"""
    unique_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    layer: str = "default"
    color: str = "black"
    linewidth: float = 1.0
    visible: bool = True
    label: str = ""  # 设备标签

    @abstractmethod
    def to_dict(self) -> dict:
        ...

    @abstractmethod
    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        ...


# ==================== 基础图元 ====================

@dataclass
class Line(Primitive):
    start: Tuple[float, float] = (0.0, 0.0)
    end: Tuple[float, float] = (0.0, 0.0)

    def to_dict(self) -> dict:
        return {
            "type": "line", "id": self.unique_id,
            "start": list(self.start), "end": list(self.end),
            "layer": self.layer, "color": self.color,
            "linewidth": self.linewidth, "visible": self.visible, "label": self.label,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        length_sq = dx * dx + dy * dy
        if length_sq == 0:
            return (x - self.start[0]) ** 2 + (y - self.start[1]) ** 2 <= tolerance ** 2
        t = max(0, min(1, ((x - self.start[0]) * dx + (y - self.start[1]) * dy) / length_sq))
        proj_x = self.start[0] + t * dx
        proj_y = self.start[1] + t * dy
        return (x - proj_x) ** 2 + (y - proj_y) ** 2 <= tolerance ** 2


@dataclass
class Circle(Primitive):
    center: Tuple[float, float] = (0.0, 0.0)
    radius: float = 10.0

    def to_dict(self) -> dict:
        return {
            "type": "circle", "id": self.unique_id,
            "center": list(self.center), "radius": self.radius,
            "layer": self.layer, "color": self.color,
            "linewidth": self.linewidth, "visible": self.visible, "label": self.label,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        dist = ((x - self.center[0]) ** 2 + (y - self.center[1]) ** 2) ** 0.5
        return abs(dist - self.radius) <= tolerance


@dataclass
class Rectangle(Primitive):
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 0.0
    y2: float = 0.0

    @property
    def width(self) -> float:
        return abs(self.x2 - self.x1)

    @property
    def height(self) -> float:
        return abs(self.y2 - self.y1)

    def to_dict(self) -> dict:
        return {
            "type": "rectangle", "id": self.unique_id,
            "x1": self.x1, "y1": self.y1, "x2": self.x2, "y2": self.y2,
            "layer": self.layer, "color": self.color,
            "linewidth": self.linewidth, "visible": self.visible, "label": self.label,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        left, right = min(self.x1, self.x2), max(self.x1, self.x2)
        top, bottom = min(self.y1, self.y2), max(self.y1, self.y2)
        on_top = abs(y - top) <= tolerance and left - tolerance <= x <= right + tolerance
        on_bottom = abs(y - bottom) <= tolerance and left - tolerance <= x <= right + tolerance
        on_left = abs(x - left) <= tolerance and top - tolerance <= y <= bottom + tolerance
        on_right = abs(x - right) <= tolerance and top - tolerance <= y <= bottom + tolerance
        return on_top or on_bottom or on_left or on_right


@dataclass
class Text(Primitive):
    position: Tuple[float, float] = (0.0, 0.0)
    content: str = ""
    font_size: float = 12.0

    def to_dict(self) -> dict:
        return {
            "type": "text", "id": self.unique_id,
            "position": list(self.position), "content": self.content,
            "font_size": self.font_size,
            "layer": self.layer, "color": self.color, "visible": self.visible,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        dx = x - self.position[0]
        dy = y - self.position[1]
        return dx * dx + dy * dy <= (tolerance + self.font_size) ** 2


# ==================== 多段线 ====================

@dataclass
class Polyline(Primitive):
    """多段线图元"""
    points: List[Tuple[float, float]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "type": "polyline", "id": self.unique_id,
            "points": [list(p) for p in self.points],
            "layer": self.layer, "color": self.color,
            "linewidth": self.linewidth, "visible": self.visible, "label": self.label,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        for i in range(len(self.points) - 1):
            p1, p2 = self.points[i], self.points[i + 1]
            dx = p2[0] - p1[0]; dy = p2[1] - p1[1]
            lsq = dx * dx + dy * dy
            if lsq == 0:
                if (x - p1[0])**2 + (y - p1[1])**2 <= tolerance**2: return True
                continue
            t = max(0, min(1, ((x - p1[0]) * dx + (y - p1[1]) * dy) / lsq))
            if (x - (p1[0] + t * dx))**2 + (y - (p1[1] + t * dy))**2 <= tolerance**2: return True
        return False


# ==================== 圆弧 ====================

@dataclass
class Arc(Primitive):
    """圆弧图元"""
    center: Tuple[float, float] = (0.0, 0.0)
    radius: float = 10.0
    start_angle: float = 0.0
    end_angle: float = 0.0

    def to_dict(self) -> dict:
        return {
            "type": "arc", "id": self.unique_id,
            "center": list(self.center), "radius": self.radius,
            "start_angle": self.start_angle, "end_angle": self.end_angle,
            "layer": self.layer, "color": self.color,
            "linewidth": self.linewidth, "visible": self.visible, "label": self.label,
        }

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        dist = ((x - self.center[0])**2 + (y - self.center[1])**2)**0.5
        if abs(dist - self.radius) > tolerance: return False
        angle = math.atan2(y - self.center[1], x - self.center[0]) % (2 * math.pi)
        sa = self.start_angle % (2 * math.pi)
        ea = self.end_angle % (2 * math.pi)
        if sa <= ea: return sa - tolerance <= angle <= ea + tolerance
        else: return angle >= sa - tolerance or angle <= ea + tolerance


# ==================== 工业符号基类 ====================

@dataclass
class IndustrialSymbol(Primitive, ABC):
    """
    工业符号基类 — 表示一个复合的P&ID符号
    
    每个符号由多个子形状组成（path_shapes），渲染时依次绘制。
    选择检测时，只要点到任一子形状的距离在容忍范围内即命中。
    """
    # 符号名称（如 "ball_valve"）
    symbol_type: str = ""
    # 符号尺寸（默认宽度）
    width: float = 60.0
    # 符号尺寸（默认高度）
    height: float = 60.0
    # 旋转角度（度）
    rotation: float = 0.0
    # 放置位置（世界坐标）
    x: float = 0.0
    y: float = 0.0

    @abstractmethod
    def get_path_shapes(self) -> List[dict]:
        """返回符号的路径定义列表，每个dict包含 type 和参数"""
        ...

    def contains_point(self, x: float, y: float, tolerance: float = 5.0) -> bool:
        """检查点是否在符号的任意路径上"""
        shapes = self.get_path_shapes()
        for shape in shapes:
            stype = shape.get("type")
            if stype == "line":
                pts = shape["points"]
                for i in range(len(pts) - 1):
                    p1, p2 = pts[i], pts[i + 1]
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    lsq = dx * dx + dy * dy
                    if lsq == 0:
                        if (x - p1[0])**2 + (y - p1[1])**2 <= tolerance**2:
                            return True
                    else:
                        t = max(0, min(1, ((x - p1[0])*dx + (y - p1[1])*dy) / lsq))
                        px = p1[0] + t * dx
                        py = p1[1] + t * dy
                        if (x - px)**2 + (y - py)**2 <= tolerance**2:
                            return True
            elif stype == "circle":
                cx, cy = shape["cx"], shape["cy"]
                r = shape["r"]
                dist = ((x - cx)**2 + (y - cy)**2)**0.5
                if abs(dist - r) <= tolerance:
                    return True
            elif stype == "polygon":
                pts = shape["points"]
                # 点到多边形边的距离
                for i in range(len(pts)):
                    p1 = pts[i]
                    p2 = pts[(i + 1) % len(pts)]
                    dx = p2[0] - p1[0]
                    dy = p2[1] - p1[1]
                    lsq = dx * dx + dy * dy
                    if lsq == 0:
                        if (x - p1[0])**2 + (y - p1[1])**2 <= tolerance**2:
                            return True
                    else:
                        t = max(0, min(1, ((x - p1[0])*dx + (y - p1[1])*dy) / lsq))
                        px = p1[0] + t * dx
                        py = p1[1] + t * dy
                        if (x - px)**2 + (y - py)**2 <= tolerance**2:
                            return True
        return False

    def to_dict(self) -> dict:
        return {
            "type": "industrial_symbol",
            "id": self.unique_id,
            "symbol_type": self.symbol_type,
            "position": [self.x, self.y],
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "layer": self.layer,
            "color": self.color,
            "linewidth": self.linewidth,
            "visible": self.visible,
            "label": self.label,
            "path_shapes": self.get_path_shapes(),
        }


# ==================== 阀门类符号 ====================

@dataclass
class BallValve(IndustrialSymbol):
    """球阀 — 两个三角形对顶，中间一条横线"""
    symbol_type: str = "ball_valve"
    width: float = 60.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h/2], [w/2 - 5, h/2]]},
            {"type": "line", "points": [[w/2 + 5, h/2], [w, h/2]]},
            {"type": "polygon", "points": [[w/2 - 5, 0], [w/2, h/2], [w/2 - 5, h]]},
            {"type": "polygon", "points": [[w/2 + 5, 0], [w/2, h/2], [w/2 + 5, h]]},
        ]


@dataclass
class ButterflyValve(IndustrialSymbol):
    """蝶阀 — 两个三角形对顶，中间一个圆圈"""
    symbol_type: str = "butterfly_valve"
    width: float = 60.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h/2], [w/2 - 8, h/2]]},
            {"type": "line", "points": [[w/2 + 8, h/2], [w, h/2]]},
            {"type": "polygon", "points": [[w/2 - 8, 0], [w/2, h/2], [w/2 - 8, h]]},
            {"type": "polygon", "points": [[w/2 + 8, 0], [w/2, h/2], [w/2 + 8, h]]},
            {"type": "circle", "cx": w/2, "cy": h/2, "r": 5},
        ]


@dataclass
class CheckValve(IndustrialSymbol):
    """止回阀 — 一个三角形指向右侧，一侧有竖线"""
    symbol_type: str = "check_valve"
    width: float = 60.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h/2], [w/2 - 5, h/2]]},
            {"type": "line", "points": [[w/2 + 5, h/2], [w, h/2]]},
            {"type": "line", "points": [[w/2 - 5, 0], [w/2 - 5, h]]},
            {"type": "polygon", "points": [[w/2 - 5, 0], [w, h/2], [w/2 - 5, h]]},
        ]


@dataclass
class GlobeValve(IndustrialSymbol):
    """截止阀 — 两个三角形对顶，顶部有横线手柄"""
    symbol_type: str = "globe_valve"
    width: float = 60.0
    height: float = 50.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h/2], [w/2 - 5, h/2]]},
            {"type": "line", "points": [[w/2 + 5, h/2], [w, h/2]]},
            {"type": "polygon", "points": [[w/2 - 5, h/4], [w/2, h/2], [w/2 - 5, 3*h/4]]},
            {"type": "polygon", "points": [[w/2 + 5, h/4], [w/2, h/2], [w/2 + 5, 3*h/4]]},
            {"type": "line", "points": [[w/2 - 10, h/4 - 5], [w/2 + 10, h/4 - 5]]},
            {"type": "line", "points": [[w/2, h/4 - 5], [w/2, h/4]]},
        ]


@dataclass
class GateValve(IndustrialSymbol):
    """闸阀 — 两个直角三角形对顶"""
    symbol_type: str = "gate_valve"
    width: float = 60.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h/2], [w/2 - 5, h/2]]},
            {"type": "line", "points": [[w/2 + 5, h/2], [w, h/2]]},
            {"type": "polygon", "points": [[w/2 - 5, 0], [w/2, h/2], [w/2 - 5, h], [w/2 + 5, 0]]},
        ]


@dataclass
class ControlValve(IndustrialSymbol):
    """调节阀 — 球阀带执行机构（顶部方框）"""
    symbol_type: str = "control_valve"
    width: float = 60.0
    height: float = 70.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "line", "points": [[0, h*0.6], [w/2 - 5, h*0.6]]},
            {"type": "line", "points": [[w/2 + 5, h*0.6], [w, h*0.6]]},
            {"type": "polygon", "points": [[w/2 - 5, h*0.4], [w/2, h*0.6], [w/2 - 5, h*0.8]]},
            {"type": "polygon", "points": [[w/2 + 5, h*0.4], [w/2, h*0.6], [w/2 + 5, h*0.8]]},
            {"type": "rectangle", "points": [[w/2 - 12, 0], [w/2 + 12, h*0.35]]},
            {"type": "line", "points": [[w/2, h*0.35], [w/2, h*0.4]]},
        ]


# ==================== 仪表类符号 ====================

@dataclass
class TemperatureIndicator(IndustrialSymbol):
    """温度指示仪 — 圆圈内有字母TI"""
    symbol_type: str = "temperature_indicator"
    width: float = 40.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "circle", "cx": w/2, "cy": h/2, "r": w/2 - 2},
        ]

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["text"] = self.label or "TE"
        return d


@dataclass
class PressureIndicator(IndustrialSymbol):
    """压力指示仪 — 圆圈内有字母PI"""
    symbol_type: str = "pressure_indicator"
    width: float = 40.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "circle", "cx": w/2, "cy": h/2, "r": w/2 - 2},
        ]

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["text"] = self.label or "PE"
        return d


@dataclass
class FlowIndicator(IndustrialSymbol):
    """流量指示仪 — 圆圈内有字母FI"""
    symbol_type: str = "flow_indicator"
    width: float = 40.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "circle", "cx": w/2, "cy": h/2, "r": w/2 - 2},
        ]

    def to_dict(self) -> dict:
        d = super().to_dict()
        d["text"] = self.label or "FE"
        return d


# ==================== 罐体类符号 ====================

@dataclass
class GasTank(IndustrialSymbol):
    """储气罐 — 椭圆形罐体（上下半圆+中间矩形）"""
    symbol_type: str = "gas_tank"
    width: float = 80.0
    height: float = 120.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        r = w / 2
        return [
            {"type": "circle", "cx": w/2, "cy": r, "r": r},
            {"type": "line", "points": [[r, r], [r, h - r]]},
            {"type": "line", "points": [[w - r, r], [w - r, h - r]]},
            {"type": "circle", "cx": w/2, "cy": h - r, "r": r},
        ]


@dataclass
class BufferTank(IndustrialSymbol):
    """缓冲罐 — 卧式圆柱形（矩形+两端半圆）"""
    symbol_type: str = "buffer_tank"
    width: float = 120.0
    height: float = 60.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        r = h / 2
        return [
            {"type": "line", "points": [[r, 0], [w - r, 0]]},
            {"type": "line", "points": [[r, h], [w - r, h]]},
            {"type": "circle", "cx": r, "cy": h/2, "r": r},
            {"type": "circle", "cx": w - r, "cy": h/2, "r": r},
        ]


@dataclass
class PurificationCabinet(IndustrialSymbol):
    """纯化柜 — 矩形框内有分隔线"""
    symbol_type: str = "purification_cabinet"
    width: float = 100.0
    height: float = 80.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "rectangle", "points": [[0, 0], [w, h]]},
            {"type": "line", "points": [[w/3, 0], [w/3, h]]},
            {"type": "line", "points": [[2*w/3, 0], [2*w/3, h]]},
        ]


# ==================== 泵类符号 ====================

@dataclass
class CentrifugalPump(IndustrialSymbol):
    """离心泵 — 圆形外壳+出口管"""
    symbol_type: str = "centrifugal_pump"
    width: float = 60.0
    height: float = 60.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        r = w / 2 - 4
        return [
            {"type": "circle", "cx": w/2, "cy": h/2, "r": r},
            {"type": "line", "points": [[w/2 - 3, 0], [w/2 + 3, h*0.3]]},
            {"type": "line", "points": [[0, h/2], [r, h/2]]},
        ]


@dataclass
class ReciprocatingPump(IndustrialSymbol):
    """往复泵 — 三角形+圆圈组合"""
    symbol_type: str = "reciprocating_pump"
    width: float = 60.0
    height: float = 60.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "polygon", "points": [[10, h*0.2], [w-10, h/2], [10, h*0.8]]},
            {"type": "circle", "cx": w/2, "cy": h/2, "r": 8},
        ]


# ==================== 风机类符号 ====================

@dataclass
class Fan(IndustrialSymbol):
    """风机 — 半圆+叶片"""
    symbol_type: str = "fan"
    width: float = 60.0
    height: float = 60.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        r = w / 2 - 4
        return [
            {"type": "circle", "cx": w/2, "cy": h/2, "r": r},
            {"type": "line", "points": [[w/2, 4], [w/2, h-4]]},
            {"type": "line", "points": [[4, h/2], [w-4, h/2]]},
        ]


@dataclass
class HighTempFan(IndustrialSymbol):
    """高温风机 — 风机符号外加方框"""
    symbol_type: str = "high_temp_fan"
    width: float = 80.0
    height: float = 80.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        r = w/2 - 12
        cx, cy = w/2, h/2
        return [
            {"type": "rectangle", "points": [[4, 4], [w-4, h-4]]},
            {"type": "circle", "cx": cx, "cy": cy, "r": r},
            {"type": "line", "points": [[cx, cy - r], [cx, cy + r]]},
            {"type": "line", "points": [[cx - r, cy], [cx + r, cy]]},
        ]


# ==================== 柜体类符号 ====================

@dataclass
class ExhaustCabinet(IndustrialSymbol):
    """排气柜 — 大矩形框"""
    symbol_type: str = "exhaust_cabinet"
    width: float = 100.0
    height: float = 120.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "rectangle", "points": [[0, 0], [w, h]]},
        ]


@dataclass
class ControlCabinet(IndustrialSymbol):
    """控制柜 — 矩形框内有小矩形"""
    symbol_type: str = "control_cabinet"
    width: float = 80.0
    height: float = 100.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "rectangle", "points": [[0, 0], [w, h]]},
            {"type": "rectangle", "points": [[8, 8], [w-8, h*0.6]]},
        ]


# ==================== 系统接口符号 ====================

@dataclass
class SystemInterface(IndustrialSymbol):
    """
    系统接口 — 左侧长方形 + 右侧箭头尖头
    用于标记不同系统之间的连接点
    """
    symbol_type: str = "system_interface"
    width: float = 100.0
    height: float = 40.0

    def get_path_shapes(self) -> List[dict]:
        w, h = self.width, self.height
        return [
            {"type": "rectangle", "points": [[0, 0], [w - h/2, h]]},
            {"type": "polygon", "points": [[w - h/2, 0], [w, h/2], [w - h/2, h]]},
        ]


# ==================== 符号注册表 ====================

SYMBOL_REGISTRY: Dict[str, type] = {
    # 阀门
    "ball_valve": BallValve,
    "butterfly_valve": ButterflyValve,
    "check_valve": CheckValve,
    "globe_valve": GlobeValve,
    "gate_valve": GateValve,
    "control_valve": ControlValve,
    # 仪表
    "temperature_indicator": TemperatureIndicator,
    "pressure_indicator": PressureIndicator,
    "flow_indicator": FlowIndicator,
    # 罐体
    "gas_tank": GasTank,
    "buffer_tank": BufferTank,
    "purification_cabinet": PurificationCabinet,
    # 泵
    "centrifugal_pump": CentrifugalPump,
    "reciprocating_pump": ReciprocatingPump,
    # 风机
    "fan": Fan,
    "high_temp_fan": HighTempFan,
    # 柜体
    "exhaust_cabinet": ExhaustCabinet,
    "control_cabinet": ControlCabinet,
    # 系统接口
    "system_interface": SystemInterface,
}

# 符号分类信息（用于前端面板展示）
SYMBOL_CATEGORIES = {
    "阀门": ["ball_valve", "butterfly_valve", "check_valve", "globe_valve", "gate_valve", "control_valve"],
    "仪表": ["temperature_indicator", "pressure_indicator", "flow_indicator"],
    "罐体": ["gas_tank", "buffer_tank", "purification_cabinet"],
    "泵": ["centrifugal_pump", "reciprocating_pump"],
    "风机": ["fan", "high_temp_fan"],
    "柜体": ["exhaust_cabinet", "control_cabinet"],
    "系统接口": ["system_interface"],
}

# 符号显示名称映射
SYMBOL_NAMES = {
    "ball_valve": "球阀",
    "butterfly_valve": "蝶阀",
    "check_valve": "止回阀",
    "globe_valve": "截止阀",
    "gate_valve": "闸阀",
    "control_valve": "调节阀",
    "temperature_indicator": "温度仪表",
    "pressure_indicator": "压力仪表",
    "flow_indicator": "流量仪表",
    "gas_tank": "储气罐",
    "buffer_tank": "缓冲罐",
    "purification_cabinet": "纯化柜",
    "centrifugal_pump": "离心泵",
    "reciprocating_pump": "往复泵",
    "fan": "风机",
    "high_temp_fan": "高温风机",
    "exhaust_cabinet": "排气柜",
    "control_cabinet": "控制柜",
    "system_interface": "系统接口",
}


def create_symbol(symbol_type: str, x: float = 0.0, y: float = 0.0, 
                  label: str = "", color: str = "black", **kwargs) -> IndustrialSymbol:
    """根据符号类型创建工业符号实例"""
    cls = SYMBOL_REGISTRY.get(symbol_type)
    if cls is None:
        raise ValueError(f"Unknown symbol type: {symbol_type}. Available: {list(SYMBOL_REGISTRY.keys())}")
    
    instance = cls(**kwargs)
    # 设置位置和属性
    instance.x = x
    instance.y = y
    instance.unique_id = str(uuid.uuid4())[:8]
    instance.label = label
    instance.color = color
    return instance


def create_primitive(primitive_type: str, **kwargs) -> Primitive:
    """根据类型名创建图元实例（兼容旧代码）"""
    if primitive_type == "industrial_symbol":
        sym_type = kwargs.pop("symbol_type", "")
        return create_symbol(symbol_type=sym_type, **kwargs)
    cls = {
        "line": Line, "circle": Circle, "rectangle": Rectangle,
        "polyline": Polyline, "arc": Arc, "text": Text,
    }.get(primitive_type)
    if cls is None:
        raise ValueError(f"Unknown primitive type: {primitive_type}")
    return cls(**kwargs)


def get_symbol_library() -> dict:
    """返回完整的符号库信息（分类、名称、尺寸）"""
    return {
        "categories": SYMBOL_CATEGORIES,
        "names": SYMBOL_NAMES,
        "symbols": {
            name: {
                "category": cat,
                "width": cls.width if hasattr(cls, 'width') else 60,
                "height": cls.height if hasattr(cls, 'height') else 60,
            }
            for cat, names in SYMBOL_CATEGORIES.items()
            for name in names
            for cls in [SYMBOL_REGISTRY[name]]
        }
    }
