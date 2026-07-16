"""
Agent API 路由 — 所有画图接口的实现
"""

from __future__ import annotations
import math
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from typing import Optional

from fastapi import APIRouter, HTTPException

from engine.canvas import DrawingCanvas
from engine.primitives import (
    Line, Circle, Rectangle, Polyline, Arc, Text,
    IndustrialSymbol, get_symbol_library,
)
from api.schemas import (
    LineRequest, CircleRequest, RectangleRequest,
    PolylineRequest, ArcRequest, TextRequest,
    IndustrialSymbolRequest, SymbolLibraryResponse,
    CreateLayerRequest, BatchDrawRequest,
    DrawResult, LayersResponse, LayerInfo, ApiResponse,
)

router = APIRouter(prefix="/api/v1", tags=["AgentCAD API"])

# 全局画布实例
_canvas: Optional[DrawingCanvas] = None


def set_canvas(canvas: DrawingCanvas):
    global _canvas
    _canvas = canvas


def get_canvas() -> DrawingCanvas:
    if _canvas is None:
        raise RuntimeError("Canvas not initialized. Call set_canvas() first.")
    return _canvas


# ==================== 基础画图接口 ====================

@router.post("/draw/line", response_model=DrawResult)
def draw_line(req: LineRequest):
    canvas = get_canvas()
    if len(req.start) != 2 or len(req.end) != 2:
        raise HTTPException(400, "start and end must be [x, y] pairs")
    line = Line(start=tuple(req.start), end=tuple(req.end), color=req.color,
                linewidth=req.linewidth, layer=req.layer)
    canvas.add_primitive(line)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=line.to_dict())


@router.post("/draw/circle", response_model=DrawResult)
def draw_circle(req: CircleRequest):
    canvas = get_canvas()
    circle = Circle(center=tuple(req.center), radius=req.radius, color=req.color,
                    linewidth=req.linewidth, layer=req.layer)
    canvas.add_primitive(circle)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=circle.to_dict())


@router.post("/draw/rectangle", response_model=DrawResult)
def draw_rectangle(req: RectangleRequest):
    canvas = get_canvas()
    rect = Rectangle(x1=req.x1, y1=req.y1, x2=req.x2, y2=req.y2,
                     color=req.color, linewidth=req.linewidth, layer=req.layer)
    canvas.add_primitive(rect)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=rect.to_dict())


@router.post("/draw/polyline", response_model=DrawResult)
def draw_polyline(req: PolylineRequest):
    canvas = get_canvas()
    if len(req.points) < 2:
        raise HTTPException(400, "Polyline requires at least 2 points")
    polyline = Polyline(points=[tuple(p) for p in req.points], color=req.color,
                       linewidth=req.linewidth, layer=req.layer)
    canvas.add_primitive(polyline)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=polyline.to_dict())


@router.post("/draw/arc", response_model=DrawResult)
def draw_arc(req: ArcRequest):
    canvas = get_canvas()
    arc = Arc(center=tuple(req.center), radius=req.radius,
              start_angle=req.start_angle, end_angle=req.end_angle,
              color=req.color, linewidth=req.linewidth, layer=req.layer)
    canvas.add_primitive(arc)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=arc.to_dict())


@router.post("/draw/text", response_model=DrawResult)
def draw_text(req: TextRequest):
    canvas = get_canvas()
    text = Text(position=(req.x, req.y), content=req.content,
                font_size=req.font_size, color=req.color, layer=req.layer)
    canvas.add_primitive(text)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data=text.to_dict())


# ==================== 工业符号接口 ====================

@router.post("/draw/symbol", response_model=DrawResult)
def draw_industrial_symbol(req: IndustrialSymbolRequest):
    """创建一个工业符号（阀门、仪表、罐体、泵、风机、柜体、系统接口）"""
    canvas = get_canvas()
    symbol = canvas.create_industrial_symbol(
        symbol_type=req.symbol_type,
        x=req.x, y=req.y,
        label=req.label,
        color=req.color,
        linewidth=req.linewidth,
        layer=req.layer,
        rotation=req.rotation,
        width=req.width,
        height=req.height,
    )
    return DrawResult(
        primitives_count=len(canvas.get_all_primitives()),
        history_size=canvas.history_size,
        data=symbol.to_dict(),
    )


@router.get("/symbols/library", response_model=SymbolLibraryResponse)
def get_symbol_library_api():
    """获取完整的工业符号库信息"""
    lib = get_symbol_library()
    return SymbolLibraryResponse(
        success=True, message="OK",
        data={"categories": lib["categories"], "names": lib["names"], "symbols": lib["symbols"]}
    )


# ==================== 批量画图 ====================

@router.post("/draw/batch", response_model=DrawResult)
def draw_batch(req: BatchDrawRequest):
    canvas = get_canvas()
    created = []
    for op in req.operations:
        ptype = op.get("type")
        try:
            if ptype == "line":
                line = Line(start=tuple(op["start"]), end=tuple(op["end"]),
                           color=op.get("color", "black"), linewidth=op.get("linewidth", 1.0),
                           layer=op.get("layer", "default"))
                canvas.add_primitive(line)
                created.append(line.to_dict())
            elif ptype == "circle":
                circ = Circle(center=tuple(op["center"]), radius=op["radius"],
                             color=op.get("color", "black"), linewidth=op.get("linewidth", 1.0),
                             layer=op.get("layer", "default"))
                canvas.add_primitive(circ)
                created.append(circ.to_dict())
            elif ptype == "industrial_symbol":
                symbol = canvas.create_industrial_symbol(
                    symbol_type=op["symbol_type"],
                    x=op.get("x", 0), y=op.get("y", 0),
                    label=op.get("label", ""),
                    color=op.get("color", "black"),
                )
                canvas.add_primitive(symbol)
                created.append(symbol.to_dict())
        except Exception:
            continue
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data={"created": created})


# ==================== 撤销/清空 ====================

@router.post("/undo", response_model=DrawResult)
def undo_last():
    canvas = get_canvas()
    undone = canvas.undo()
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size,
                      data={"undone": undone.to_dict() if undone else None})


@router.post("/redo", response_model=DrawResult)
def redo_last():
    canvas = get_canvas()
    redone = canvas.redo()
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size,
                      data={"redone": redone.to_dict() if redone else None})


@router.delete("/clear", response_model=DrawResult)
def clear_canvas():
    canvas = get_canvas()
    canvas.clear()
    return DrawResult(primitives_count=0, history_size=0)


# ==================== 查询接口 ====================

@router.get("/primitives", response_model=DrawResult)
def list_primitives():
    canvas = get_canvas()
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size,
                      data={"primitives": canvas.get_all_primitives()})


@router.get("/primitives/{primitive_id}", response_model=ApiResponse)
def get_primitive(primitive_id: str):
    canvas = get_canvas()
    prim = canvas.get_primitive_by_id(primitive_id)
    if prim is None:
        raise HTTPException(404, f"Primitive '{primitive_id}' not found")
    return ApiResponse(success=True, message="OK", data=prim)


@router.delete("/primitives/{primitive_id}", response_model=DrawResult)
def delete_primitive(primitive_id: str):
    canvas = get_canvas()
    prim = canvas.get_primitive_by_id(primitive_id)
    if prim is None:
        raise HTTPException(404, f"Primitive '{primitive_id}' not found")
    canvas.delete_primitive(primitive_id)
    return DrawResult(primitives_count=len(canvas.get_all_primitives()),
                      history_size=canvas.history_size, data={"deleted": prim})


@router.get("/scene", response_model=dict)
def get_scene():
    canvas = get_canvas()
    return canvas.to_dict()


# ==================== 图层管理 ====================

@router.get("/layers", response_model=LayersResponse)
def list_layers():
    canvas = get_canvas()
    layers = []
    for name, layer in canvas.layer_manager._layers.items():
        layers.append(LayerInfo(name=name, visible=layer.visible,
                               locked=layer.locked, count=len(layer.primitives)))
    return LayersResponse(layers=layers)


@router.post("/layers", response_model=LayersResponse)
def create_layer(req: CreateLayerRequest):
    canvas = get_canvas()
    try:
        canvas.layer_manager.create_layer(req.name, visible=req.visible)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return list_layers()


@router.delete("/layers/{name}", response_model=LayersResponse)
def delete_layer(name: str):
    canvas = get_canvas()
    try:
        canvas.layer_manager.delete_layer(name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return list_layers()


@router.patch("/layers/{name}/visibility")
def toggle_layer_visibility(name: str):
    canvas = get_canvas()
    layer = canvas.layer_manager.get_layer(name)
    if not layer:
        raise HTTPException(404, f"Layer '{name}' not found")
    layer.visible = not layer.visible
    return {"layer": name, "visible": layer.visible}


# ==================== 导出 ====================

@router.get("/export/svg")
def export_svg():
    canvas = get_canvas()
    svg = generate_svg(canvas)
    return {"svg": svg, "format": "svg"}


def generate_svg(canvas: DrawingCanvas) -> str:
    width, height = canvas.width, canvas.height
    svg_parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">']
    svg_parts.append(f'<rect width="{width}" height="{height}" fill="white"/>')
    
    for prim in canvas.layer_manager.get_all_visible():
        if isinstance(prim, Line):
            svg_parts.append(f'<line x1="{prim.start[0]}" y1="{prim.start[1]}" x2="{prim.end[0]}" y2="{prim.end[1]}" stroke="{prim.color}" stroke-width="{prim.linewidth}"/>')
        elif isinstance(prim, Circle):
            svg_parts.append(f'<circle cx="{prim.center[0]}" cy="{prim.center[1]}" r="{prim.radius}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
        elif isinstance(prim, Rectangle):
            x, y = min(prim.x1, prim.x2), min(prim.y1, prim.y2)
            w, h = abs(prim.x2 - prim.x1), abs(prim.y2 - prim.y1)
            svg_parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
        elif isinstance(prim, Polyline):
            pts = " ".join(f"{p[0]},{p[1]}" for p in prim.points)
            svg_parts.append(f'<polyline points="{pts}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
        elif isinstance(prim, Arc):
            cx, cy = prim.center
            r = prim.radius
            sx = cx + r * math.cos(prim.start_angle)
            sy = cy - r * math.sin(prim.start_angle)
            ex = cx + r * math.cos(prim.end_angle)
            ey = cy - r * math.sin(prim.end_angle)
            large = abs(prim.end_angle - prim.start_angle) > math.pi
            svg_parts.append(f'<path d="M {sx} {sy} A {r} {r} 0 {large} 0 {ex} {ey}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
        elif isinstance(prim, Text):
            svg_parts.append(f'<text x="{prim.position[0]}" y="{prim.position[1]}" fill="{prim.color}" font-size="{prim.font_size}">{prim.content}</text>')
        elif isinstance(prim, IndustrialSymbol):
            # 工业符号：渲染其路径
            shapes = prim.get_path_shapes()
            for shape in shapes:
                if shape["type"] == "line":
                    pts = shape["points"]
                    for i in range(len(pts) - 1):
                        p1, p2 = pts[i], pts[i+1]
                        svg_parts.append(f'<line x1="{p1[0]+prim.width/2}" y1="{p1[1]+prim.height/2}" x2="{p2[0]+prim.width/2}" y2="{p2[1]+prim.height/2}" stroke="{prim.color}" stroke-width="{prim.linewidth}"/>')
                elif shape["type"] == "circle":
                    svg_parts.append(f'<circle cx="{shape["cx"]+prim.width/2}" cy="{shape["cy"]+prim.height/2}" r="{shape["r"]}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
                elif shape["type"] == "polygon":
                    pts = shape["points"]
                    pts_str = " ".join(f"{p[0]+prim.width/2},{p[1]+prim.height/2}" for p in pts)
                    svg_parts.append(f'<polygon points="{pts_str}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
                elif shape["type"] == "rectangle":
                    pts = shape["points"]
                    x, y = pts[0][0]+prim.width/2, pts[0][1]+prim.height/2
                    w, h = pts[1][0]-pts[0][0]+prim.width/2, pts[1][1]-pts[0][1]+prim.height/2
                    svg_parts.append(f'<rect x="{x}" y="{y}" width="{abs(w)}" height="{abs(h)}" stroke="{prim.color}" stroke-width="{prim.linewidth}" fill="none"/>')
    
    svg_parts.append("</svg>")
    return "\n".join(svg_parts)
