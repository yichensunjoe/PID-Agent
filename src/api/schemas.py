"""
请求/响应数据模型 — Pydantic schemas
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


# ==================== 画图请求模型 ====================

class Point(BaseModel):
    x: float
    y: float


class LineRequest(BaseModel):
    start: List[float] = Field(default=[0.0, 0.0], description="起点 [x, y]")
    end: List[float] = Field(default=[0.0, 0.0], description="终点 [x, y]")
    color: str = "black"
    linewidth: float = 1.0
    layer: str = "default"


class CircleRequest(BaseModel):
    center: List[float] = Field(default=[0.0, 0.0], description="圆心 [x, y]")
    radius: float = Field(default=10.0, gt=0, description="半径")
    color: str = "black"
    linewidth: float = 1.0
    layer: str = "default"


class RectangleRequest(BaseModel):
    x1: float = 0.0
    y1: float = 0.0
    x2: float = 100.0
    y2: float = 100.0
    color: str = "black"
    linewidth: float = 1.0
    layer: str = "default"


class PolylineRequest(BaseModel):
    points: List[List[float]] = Field(default_factory=list, description="顶点坐标列表 [[x,y], ...]")
    color: str = "black"
    linewidth: float = 1.0
    layer: str = "default"


class ArcRequest(BaseModel):
    center: List[float] = Field(default=[0.0, 0.0], description="圆心 [x, y]")
    radius: float = Field(default=10.0, gt=0, description="半径")
    start_angle: float = Field(default=0.0, description="起始角度（弧度）")
    end_angle: float = Field(default=3.14159, description="终止角度（弧度）")
    color: str = "black"
    linewidth: float = 1.0
    layer: str = "default"


class TextRequest(BaseModel):
    content: str = Field(default="", description="文字内容")
    x: float = 0.0
    y: float = 0.0
    font_size: float = 12.0
    color: str = "black"
    layer: str = "default"


# ==================== 工业符号请求模型 ====================

class IndustrialSymbolRequest(BaseModel):
    """工业符号创建请求"""
    symbol_type: str = Field(..., description="符号类型，如 ball_valve, gas_tank 等")
    x: float = Field(default=0.0, description="放置位置 x")
    y: float = Field(default=0.0, description="放置位置 y")
    label: str = Field(default="", description="设备标签，如 TE-101")
    color: str = Field(default="black", description="颜色")
    linewidth: float = Field(default=1.0, description="线宽")
    layer: str = Field(default="default", description="所属图层")
    rotation: float = Field(default=0.0, description="旋转角度（度）")
    width: float = Field(default=60.0, description="符号宽度")
    height: float = Field(default=60.0, description="符号高度")


# ==================== 图层请求模型 ====================

class CreateLayerRequest(BaseModel):
    name: str
    visible: bool = True


# ==================== 响应模型 ====================

class ApiResponse(BaseModel):
    success: bool = True
    message: str = "OK"
    data: Optional[dict] = None


class PrimitiveResponse(ApiResponse):
    primitive: Optional[dict] = None


class DrawResult(ApiResponse):
    primitives_count: int = 0
    history_size: int = 0


class LayerInfo(BaseModel):
    name: str
    visible: bool
    locked: bool
    count: int


class LayersResponse(ApiResponse):
    layers: List[LayerInfo] = []


# ==================== 批量操作 ====================

class BatchDrawRequest(BaseModel):
    operations: List[dict] = Field(
        default_factory=list,
        description="图元操作列表，每个元素包含 type 和对应参数"
    )


# ==================== 符号库信息 ====================

class SymbolLibraryResponse(ApiResponse):
    """返回符号库信息"""
    categories: dict = {}
    names: dict = {}
    symbols: dict = {}
