import type { Document } from "./types";

export type WorkspaceMutationOrigin = {
  documentId: string;
  revision: number;
  documentGeneration: number;
  mutationGeneration: number;
};

export function mutationOriginCanApply(
  origin: WorkspaceMutationOrigin,
  current: Document | null,
  documentGeneration: number,
  mutationGeneration: number,
): boolean {
  return origin.documentGeneration === documentGeneration
    && origin.mutationGeneration === mutationGeneration
    && current?.id === origin.documentId
    && current.revision === origin.revision;
}

export function mutationResponseCanApply(
  origin: WorkspaceMutationOrigin,
  current: Document | null,
  documentGeneration: number,
  mutationGeneration: number,
  responseDocument: Document,
): boolean {
  return mutationOriginCanApply(origin, current, documentGeneration, mutationGeneration)
    && responseDocument.id === origin.documentId
    && responseDocument.revision >= origin.revision;
}
