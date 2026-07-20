import type { Element, Operation } from "../types";

export const EDITOR_GROUP_KEY = "editor_group_id";
export const EDITOR_LOCK_KEY = "editor_locked";

export type SelectionScope = "type" | "layer" | "system" | "process_tag" | "group" | "route_family" | "invert";
export type CommonValue<T> = { state: "empty" } | { state: "single"; value: T } | { state: "mixed" };

export function readEditorGroupId(element: Element): string | null {
  const value = element.metadata[EDITOR_GROUP_KEY];
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

export function isElementEditLocked(element: Element): boolean {
  return element.metadata[EDITOR_LOCK_KEY] === true;
}

export function metadataWithGroup(element: Element, groupId: string | null): Record<string, unknown> {
  const metadata = { ...element.metadata };
  if (groupId) metadata[EDITOR_GROUP_KEY] = groupId;
  else delete metadata[EDITOR_GROUP_KEY];
  return metadata;
}

export function metadataWithEditorLock(element: Element, locked: boolean): Record<string, unknown> {
  const metadata = { ...element.metadata };
  if (locked) metadata[EDITOR_LOCK_KEY] = true;
  else delete metadata[EDITOR_LOCK_KEY];
  return metadata;
}

export function expandSelectionByGroups(elements: Element[], ids: string[]): string[] {
  const selected = new Set(ids);
  const groupIds = new Set<string>();
  for (const element of elements) {
    if (!selected.has(element.id)) continue;
    const groupId = readEditorGroupId(element);
    if (groupId) groupIds.add(groupId);
  }
  if (!groupIds.size) return elements.filter((element) => selected.has(element.id)).map((element) => element.id);
  return elements
    .filter((element) => selected.has(element.id) || Boolean(readEditorGroupId(element) && groupIds.has(readEditorGroupId(element)!)))
    .map((element) => element.id);
}

export function normalizedGroupMembers(elements: Element[]): Map<string, string[]> {
  const groups = new Map<string, string[]>();
  for (const element of elements) {
    const groupId = readEditorGroupId(element);
    if (!groupId) continue;
    const members = groups.get(groupId) ?? [];
    members.push(element.id);
    groups.set(groupId, members);
  }
  for (const [groupId, members] of groups) {
    if (members.length < 2) groups.delete(groupId);
  }
  return groups;
}

export function staleGroupCleanupOperations(elements: Element[]): Operation[] {
  const validGroups = normalizedGroupMembers(elements);
  return elements.flatMap((element) => {
    const groupId = readEditorGroupId(element);
    if (!groupId || validGroups.has(groupId)) return [];
    return [{ op: "update_element", element_id: element.id, patch: { metadata: metadataWithGroup(element, null) } } as Operation];
  });
}

export function routeFamilyId(element: Element): string | null {
  if (element.type !== "connector") return null;
  const main = element.metadata.main_route_id;
  if (typeof main === "string" && main.trim()) return main.trim();
  const branch = element.metadata.branch_of_main_route_id;
  if (typeof branch === "string" && branch.trim()) return branch.trim();
  return element.id;
}

export function semanticSelection(
  elements: Element[],
  activeId: string | null,
  scope: SelectionScope,
  currentIds: string[] = [],
): string[] {
  if (scope === "invert") {
    const selected = new Set(currentIds);
    return elements.filter((element) => !selected.has(element.id)).map((element) => element.id);
  }
  const active = elements.find((element) => element.id === activeId);
  if (!active) return [];
  const groupId = readEditorGroupId(active);
  const familyId = routeFamilyId(active);
  return elements.filter((element) => {
    if (scope === "type") return element.type === active.type;
    if (scope === "layer") return element.layer_id === active.layer_id;
    if (scope === "system") return element.system_id === active.system_id;
    if (scope === "process_tag") return active.type === "connector" && Boolean(active.process_tag) && element.type === "connector" && element.process_tag === active.process_tag;
    if (scope === "group") return Boolean(groupId) && readEditorGroupId(element) === groupId;
    if (scope === "route_family") return Boolean(familyId) && routeFamilyId(element) === familyId;
    return false;
  }).map((element) => element.id);
}

export function commonValue<E extends Element, T>(elements: E[], read: (element: E) => T): CommonValue<T> {
  if (!elements.length) return { state: "empty" };
  const value = read(elements[0]);
  return elements.every((element) => Object.is(read(element), value))
    ? { state: "single", value }
    : { state: "mixed" };
}

export function directLockedOperationTargets(elements: Element[], operations: Operation[]): string[] {
  const byId = new Map(elements.map((element) => [element.id, element]));
  const targets: string[] = [];
  for (const operation of operations) {
    if (operation.op !== "update_element" && operation.op !== "delete_element") continue;
    const element = byId.get(operation.element_id);
    if (!element || !isElementEditLocked(element)) continue;
    if (operation.op === "update_element" && isUnlockOnlyPatch(element, operation.patch)) continue;
    targets.push(element.id);
  }
  return [...new Set(targets)];
}

export function isUnlockOnlyPatch(element: Element, patch: Record<string, unknown>): boolean {
  if (Object.keys(patch).length !== 1 || !("metadata" in patch)) return false;
  const next = patch.metadata;
  if (!next || typeof next !== "object" || Array.isArray(next)) return false;
  const before = { ...element.metadata };
  const after = { ...(next as Record<string, unknown>) };
  delete before[EDITOR_LOCK_KEY];
  delete after[EDITOR_LOCK_KEY];
  return JSON.stringify(before) === JSON.stringify(after) && (next as Record<string, unknown>)[EDITOR_LOCK_KEY] !== true;
}
