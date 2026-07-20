import type { Element } from "../types";

export type PaletteCommand = {
  id: string;
  label: string;
  description?: string;
  keywords?: string[];
  enabled: boolean;
  group: "command" | "element";
  elementId?: string;
};

function normalized(value: string): string {
  return value.trim().toLowerCase();
}

function subsequenceScore(query: string, candidate: string): number | null {
  if (!query) return 0;
  let cursor = 0;
  let gap = 0;
  for (const character of query) {
    const index = candidate.indexOf(character, cursor);
    if (index < 0) return null;
    gap += index - cursor;
    cursor = index + 1;
  }
  return gap;
}

export function paletteScore(command: PaletteCommand, query: string): number | null {
  const needle = normalized(query);
  if (!needle) return command.group === "command" ? 0 : 20;
  const fields = [command.label, command.description ?? "", ...(command.keywords ?? [])].map(normalized).filter(Boolean);
  let best = Number.POSITIVE_INFINITY;
  for (const field of fields) {
    if (field === needle) best = Math.min(best, 0);
    else if (field.startsWith(needle)) best = Math.min(best, 2 + field.length - needle.length);
    else {
      const index = field.indexOf(needle);
      if (index >= 0) best = Math.min(best, 10 + index);
      const fuzzy = subsequenceScore(needle, field);
      if (fuzzy !== null) best = Math.min(best, 30 + fuzzy);
    }
  }
  if (!Number.isFinite(best)) return null;
  return best + (command.enabled ? 0 : 1000) + (command.group === "element" ? 5 : 0);
}

export function filterPaletteCommands(commands: PaletteCommand[], query: string, limit = 18): PaletteCommand[] {
  return commands
    .map((command, index) => ({ command, index, score: paletteScore(command, query) }))
    .filter((entry): entry is { command: PaletteCommand; index: number; score: number } => entry.score !== null)
    .sort((left, right) => left.score - right.score || left.index - right.index || (left.command.label < right.command.label ? -1 : left.command.label > right.command.label ? 1 : 0))
    .slice(0, limit)
    .map((entry) => entry.command);
}

function elementLabel(element: Element): string {
  if (element.type === "symbol") return element.label || element.name || element.symbol_key || element.id;
  if (element.type === "connector") return element.process_tag || element.name || element.id;
  if (element.type === "text") return element.text || element.name || element.id;
  if (element.type === "junction") return element.label || element.name || element.id;
  return element.name || element.id;
}

export function elementPaletteCommands(elements: Element[]): PaletteCommand[] {
  return elements.map((element) => ({
    id: `element:${element.id}`,
    label: elementLabel(element),
    description: `${element.type} · ${element.id}`,
    keywords: [element.id, element.type, element.name, element.system_id, element.layer_id],
    enabled: true,
    group: "element" as const,
    elementId: element.id,
  }));
}
