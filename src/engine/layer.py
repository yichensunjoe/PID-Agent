"""
图层管理 — 支持多层绘图，每层可独立控制显隐
"""

from __future__ import annotations

from typing import Dict, List, Optional

from .primitives import Primitive


class Layer:
    """单个图层"""

    def __init__(self, name: str, visible: bool = True, locked: bool = False):
        self.name = name
        self.visible = visible
        self.locked = locked
        self.primitives: List[Primitive] = []

    def add(self, primitive: Primitive):
        if self.locked:
            raise ValueError(f"Layer '{self.name}' is locked")
        primitive.layer = self.name
        self.primitives.append(primitive)

    def remove(self, primitive_id: str):
        self.primitives = [p for p in self.primitives if p.unique_id != primitive_id]

    def clear(self):
        self.primitives.clear()

    def get_visible_primitives(self) -> List[Primitive]:
        """获取该图层中所有可见图元"""
        return [p for p in self.primitives if p.visible]

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "visible": self.visible,
            "locked": self.locked,
            "count": len(self.primitives),
        }


class LayerManager:
    """图层管理器"""

    DEFAULT_LAYER_NAME = "default"

    def __init__(self):
        self._layers: Dict[str, Layer] = {}
        self.create_layer(self.DEFAULT_LAYER_NAME)

    @property
    def layer_names(self) -> List[str]:
        return list(self._layers.keys())

    def create_layer(self, name: str, visible: bool = True) -> Layer:
        if name in self._layers:
            raise ValueError(f"Layer '{name}' already exists")
        layer = Layer(name, visible=visible)
        self._layers[name] = layer
        return layer

    def get_layer(self, name: str) -> Optional[Layer]:
        return self._layers.get(name)

    def delete_layer(self, name: str):
        if name == self.DEFAULT_LAYER_NAME:
            raise ValueError("Cannot delete default layer")
        if name in self._layers:
            del self._layers[name]

    def toggle_visibility(self, name: str):
        layer = self._layers.get(name)
        if layer:
            layer.visible = not layer.visible

    def lock_layer(self, name: str, locked: bool = True):
        layer = self._layers.get(name)
        if layer:
            layer.locked = locked

    def add_primitive(self, primitive: Primitive):
        layer_name = primitive.layer or self.DEFAULT_LAYER_NAME
        layer = self._layers.get(layer_name)
        if layer is None:
            layer = self.create_layer(layer_name)
        layer.add(primitive)

    def remove_primitive(self, primitive_id: str):
        for layer in self._layers.values():
            layer.remove(primitive_id)

    def get_all_visible(self) -> List[Primitive]:
        """获取所有可见图层中的所有可见图元"""
        result = []
        for layer in self._layers.values():
            if layer.visible:
                result.extend(layer.get_visible_primitives())
        return result

    def clear_all(self):
        for layer in self._layers.values():
            layer.clear()

    def undo(self) -> Optional[Primitive]:
        """从最后一个非空图层中移除最近添加的图元"""
        for layer_name in reversed(self.layer_names):
            layer = self._layers[layer_name]
            if layer.primitives:
                last = layer.primitives.pop()
                return last
        return None

    def to_dict(self) -> dict:
        return {
            "layers": {name: layer.to_dict() for name, layer in self._layers.items()},
        }
