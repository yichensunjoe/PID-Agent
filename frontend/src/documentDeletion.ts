type DocumentIdentity = { id: string };

export function documentDeletionConfirmation(name: string): string {
  return `确定删除 P&ID“${name}”吗？\n\n该文档及其 revision 历史将被永久删除，且无法撤销。`;
}

export function nextDocumentIdAfterDeletion(
  before: readonly DocumentIdentity[],
  after: readonly DocumentIdentity[],
  deletedId: string,
  activeId: string | null,
): string | null {
  if (after.length === 0) return null;

  const remainingIds = new Set(after.map((document) => document.id));
  if (activeId !== deletedId && activeId && remainingIds.has(activeId)) {
    return activeId;
  }

  const deletedIndex = before.findIndex((document) => document.id === deletedId);
  if (deletedIndex >= 0) {
    for (let index = deletedIndex + 1; index < before.length; index += 1) {
      const candidateId = before[index].id;
      if (remainingIds.has(candidateId)) return candidateId;
    }
    for (let index = deletedIndex - 1; index >= 0; index -= 1) {
      const candidateId = before[index].id;
      if (remainingIds.has(candidateId)) return candidateId;
    }
  }

  return after[0].id;
}
