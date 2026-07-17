from __future__ import annotations

from typing import Any, Iterable

from .models import Document, Operation


_MAX_CHANGE_SNAPSHOTS = 100


def _changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    return sorted(
        key
        for key in set(before) | set(after)
        if before.get(key) != after.get(key)
    )


def _operation_summary(operation: Operation) -> dict[str, Any]:
    payload = operation.model_dump(mode="json")
    op = payload["op"]
    summary: dict[str, Any] = {"op": op}
    if op == "add_element":
        element = payload["element"]
        summary.update(
            element_id=element.get("id"),
            element_type=element.get("type"),
            name=element.get("name", ""),
        )
    elif op == "update_element":
        summary.update(
            element_id=payload.get("element_id"),
            patch_fields=sorted(payload.get("patch", {}).keys()),
        )
    elif op == "delete_element":
        summary["element_id"] = payload.get("element_id")
    elif op in {"add_layer", "add_system"}:
        value = payload["layer" if op == "add_layer" else "system"]
        summary.update(entity_id=value.get("id"), name=value.get("name", ""))
    elif op in {"update_layer", "update_system"}:
        prefix = "layer" if op == "update_layer" else "system"
        summary.update(
            entity_id=payload.get(f"{prefix}_id"),
            patch_fields=sorted(payload.get("patch", {}).keys()),
        )
    elif op in {"delete_layer", "delete_system"}:
        prefix = "layer" if op == "delete_layer" else "system"
        summary.update(
            entity_id=payload.get(f"{prefix}_id"),
            move_elements_to=payload.get("move_elements_to"),
        )
    return summary


def _entity_changes(
    before_items: Iterable[Any],
    after_items: Iterable[Any],
    *,
    entity_kind: str,
) -> list[dict[str, Any]]:
    before_map = {item.id: item.model_dump(mode="json") for item in before_items}
    after_map = {item.id: item.model_dump(mode="json") for item in after_items}
    changes: list[dict[str, Any]] = []
    for entity_id in sorted(set(before_map) | set(after_map)):
        before = before_map.get(entity_id)
        after = after_map.get(entity_id)
        if before is None:
            changes.append(
                {
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                    "change": "added",
                    "entity_type": after.get("type") if after else None,
                    "changed_fields": sorted(after.keys()) if after else [],
                    "before": None,
                    "after": after,
                }
            )
        elif after is None:
            changes.append(
                {
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                    "change": "deleted",
                    "entity_type": before.get("type"),
                    "changed_fields": sorted(before.keys()),
                    "before": before,
                    "after": None,
                }
            )
        elif before != after:
            changes.append(
                {
                    "entity_kind": entity_kind,
                    "entity_id": entity_id,
                    "change": "updated",
                    "entity_type": after.get("type") or before.get("type"),
                    "changed_fields": _changed_fields(before, after),
                    "before": before,
                    "after": after,
                }
            )
    return changes


def build_history_details(
    before: Document,
    after: Document,
    operations: list[Operation] | None,
    *,
    action: str,
) -> dict[str, Any]:
    element_changes = _entity_changes(before.elements, after.elements, entity_kind="element")
    group_changes = [
        *_entity_changes(before.layers, after.layers, entity_kind="layer"),
        *_entity_changes(before.systems, after.systems, entity_kind="system"),
    ]
    all_changes = [*element_changes, *group_changes]
    affected_element_ids = [
        change["entity_id"]
        for change in element_changes
    ]
    added = [change["entity_id"] for change in element_changes if change["change"] == "added"]
    updated = [change["entity_id"] for change in element_changes if change["change"] == "updated"]
    deleted = [change["entity_id"] for change in element_changes if change["change"] == "deleted"]
    snapshots = all_changes[:_MAX_CHANGE_SNAPSHOTS]
    return {
        "schema_version": 1,
        "action": action,
        "base_revision": before.revision,
        "result_revision": after.revision,
        "element_count_before": len(before.elements),
        "element_count_after": len(after.elements),
        "affected_element_ids": affected_element_ids,
        "added_element_ids": added,
        "updated_element_ids": updated,
        "deleted_element_ids": deleted,
        "change_count": len(all_changes),
        "changes": snapshots,
        "diff_truncated": len(all_changes) > len(snapshots),
        "operation_summaries": [
            _operation_summary(operation) for operation in (operations or [])
        ],
    }
