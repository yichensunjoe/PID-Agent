"""
画布/场景管理 — 承载所有图元和图层的中央控制器
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .primitives import Primitive, create_primitive, IndustrialSymbol, create_symbol
from .layer import LayerManager


class DrawingCanvas:
    """
    绘图场景 — 管理所有图元、图层、历史记录
    
    这是整个 CAD 内核的核心对象，所有画图操作都通过它进行。
    """

    def __init__(self, width: int = 1920, height: int = 1080):
        self.width = width
        self.height = height
        self.layer_manager = LayerManager()
        self._history: List[Primitive] = []
        self._redo_stack: List[Primitive] = []

    @property
    def history_size(self) -> int:
        return len(self._history)

    def add_primitive(self, primitive: Primitive):
        """添加图元到指定图层"""
        self.layer_manager.add_primitive(primitive)
        self._history.append(primitive)
        self._redo_stack.clear()

    def create_industrial_symbol(self, symbol_type: str, x: float = 0.0, y: float = 0.0,
                                  label: str = "", color: str = "black", **kwargs) -> IndustrialSymbol:
        """创建工业符号并添加到画布"""
        symbol = create_symbol(symbol_type=symbol_type, x=x, y=y, label=label, color=color, **kwargs)
        self.add_primitive(symbol)
        return symbol

    def undo(self) -> Optional[Primitive]:
        """撤销最后操作"""
        if not self._history:
            return None
        last = self._history.pop()
        self.layer_manager.remove_primitive(last.unique_id)
        self._redo_stack.append(last)
        return last

    def redo(self) -> Optional[Primitive]:
        """重做"""
        if not self._redo_stack:
            return None
        last = self._redo_stack.pop()
        self.layer_manager.add_primitive(last)
        self._history.append(last)
        return last

    def get_all_primitives(self) -> List[dict]:
        """获取所有可见图元（序列化后的字典列表）"""
        return [p.to_dict() for p in self.layer_manager.get_all_visible()]

    def get_primitive_by_id(self, primitive_id: str) -> Optional[dict]:
        """通过 ID 查找图元"""
        for p in self.layer_manager.get_all_visible():
            if p.unique_id == primitive_id:
                return p.to_dict()
        return None

    def delete_primitive(self, primitive_id: str) -> bool:
        """删除指定图元"""
        self.layer_manager.remove_primitive(primitive_id)
        return True

    def clear(self):
        """清空所有图元"""
        self.layer_manager.clear_all()
        self._history.clear()
        self._redo_stack.clear()

    def create_from_dict(self, data: dict) -> Primitive:
        """从字典数据创建图元实例"""
        ptype = data.pop("type")
        if ptype == "industrial_symbol":
            sym_type = data.pop("symbol_type")
            label = data.pop("label", "")
            color = data.pop("color", "black")
            return create_symbol(symbol_type=sym_type, label=label, color=color, **data)
        return create_primitive(primitive_type=ptype, **data)

    def to_dict(self) -> dict:
        """完整场景序列化"""
        return {
            "canvas_size": [self.width, self.height],
            "layers": self.layer_manager.to_dict(),
            "primitives": self.get_all_primitives(),
            "history_size": self.history_size,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DrawingCanvas":
        """从字典反序列化重建场景"""
        canvas = cls(
            width=data.get("canvas_size", [1920, 1080])[0],
            height=data.get("canvas_size", [1920, 1080])[1],
        )
        for pdata in data.get("primitives", []):
            p = canvas.create_from_dict(pdata.copy())
            canvas.add_primitive(p)
        return canvas
