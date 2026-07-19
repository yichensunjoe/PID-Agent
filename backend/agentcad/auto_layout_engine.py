from __future__ import annotations

from collections import defaultdict, deque

from .auto_layout import AutoLayoutEngine as BaseAutoLayoutEngine
from .layout_models import AutoLayoutRequest
from .models import Document, Operation, Point, UpdateElementOperation


class AutoLayoutEngine(BaseAutoLayoutEngine):
    """Compatibility-hardened automatic layout engine.

    The base module contains geometry and routing primitives. This subclass keeps
    junction coordinates center-based, handles cyclic process graphs
    deterministically, and applies attached-text movement to the preview copy.
    """

    def _layout_components(self, document, nodes, components, connectors, request):
        positions = super()._layout_components(
            document,
            nodes,
            components,
            connectors,
            request,
        )
        element_map = {element.id: element for element in document.elements}
        for element_id, point in list(positions.items()):
            element = element_map.get(element_id)
            if element is not None and element.type == "junction":
                positions[element_id] = Point(
                    x=point.x + element.radius,
                    y=point.y + element.radius,
                )
        return positions

    @staticmethod
    def _component_ranks(component, connectors, nodes, direction):
        component_set = set(component)
        adjacency: dict[str, set[str]] = {element_id: set() for element_id in component}
        indegree = {element_id: 0 for element_id in component}
        has_directed_edge = False
        for connector in connectors:
            source = connector.source.element_id if connector.source else None
            target = connector.target.element_id if connector.target else None
            if source in component_set and target in component_set and source != target:
                if target not in adjacency[source]:
                    adjacency[source].add(target)
                    indegree[target] += 1
                    has_directed_edge = True

        coordinate = lambda element_id: (
            nodes[element_id].x if direction == "horizontal" else nodes[element_id].y,
            nodes[element_id].y if direction == "horizontal" else nodes[element_id].x,
            element_id,
        )
        if not has_directed_edge:
            ordered = sorted(component, key=coordinate)
            return {element_id: index for index, element_id in enumerate(ordered)}

        queue = deque(sorted((item for item in component if indegree[item] == 0), key=coordinate))
        ranks = {element_id: 0 for element_id in component}
        processed: set[str] = set()
        while queue:
            current = queue.popleft()
            processed.add(current)
            for target in sorted(adjacency[current], key=coordinate):
                ranks[target] = max(ranks[target], ranks[current] + 1)
                indegree[target] -= 1
                if indegree[target] == 0:
                    queue.append(target)

        # Cyclic strongly connected regions remain after Kahn traversal. Keep
        # their members together at the next deterministic rank instead of
        # allowing an unbounded longest-path update around the cycle.
        remaining = sorted(component_set - processed, key=coordinate)
        if remaining:
            incoming_rank: dict[str, int] = defaultdict(int)
            for source, targets in adjacency.items():
                if source not in processed:
                    continue
                for target in targets:
                    if target in remaining:
                        incoming_rank[target] = max(incoming_rank[target], ranks[source] + 1)
            cycle_rank = max([*ranks.values(), 0]) + 1
            for element_id in remaining:
                ranks[element_id] = max(cycle_rank, incoming_rank[element_id])
        return ranks

    def _move_attached_annotations(
        self,
        working: Document,
        operations: list[Operation],
        deltas: dict[str, tuple[float, float]],
        locked_layer_ids: set[str],
    ) -> list[str]:
        moved: list[str] = []
        attachment_keys = ("parent_element_id", "attached_to", "element_id")
        for element in list(working.elements):
            if element.type != "text" or element.layer_id in locked_layer_ids:
                continue
            parent_id = next(
                (
                    element.metadata.get(key)
                    for key in attachment_keys
                    if isinstance(element.metadata.get(key), str)
                ),
                None,
            )
            if parent_id not in deltas:
                continue
            dx, dy = deltas[parent_id]
            operation = UpdateElementOperation(
                element_id=element.id,
                patch={
                    "position": {
                        "x": element.position.x + dx,
                        "y": element.position.y + dy,
                    }
                },
            )
            self.service._apply_operation(working, operation)
            operations.append(operation)
            moved.append(element.id)
        return moved
