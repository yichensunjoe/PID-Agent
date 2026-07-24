import type {
  ConnectorElement,
  Document,
  SymbolDefinition,
  SymbolElement,
} from "./types";

export type FlowMediumClass = "water" | "gas" | "other";
export type ValveState = "open" | "closed";

const WATER_NAMES = new Set([
  "water", "h2o", "cw", "chw", "hw", "cooling water", "chilled water", "hot water",
  "水", "冷却水", "冷冻水", "热水",
]);
const GAS_NAMES = new Set([
  "gas", "air", "steam", "natural gas", "fuel gas", "instrument air",
  "气体", "空气", "蒸汽", "天然气", "燃气",
]);
const CLOSED_STATES = new Set(["closed", "close", "shut", "blocked", "off", "关", "关闭", "已关"]);

export function normalizeFlowMedium(value: string): FlowMediumClass {
  const normalized = value.trim().toLocaleLowerCase().replaceAll("_", " ").replaceAll("-", " ").replace(/\s+/g, " ");
  if (WATER_NAMES.has(normalized) || normalized.includes("water") || normalized.includes("水")) return "water";
  if (GAS_NAMES.has(normalized) || /(^|\s)gas($|\s)|air|steam|气|蒸汽/.test(normalized)) return "gas";
  return "other";
}

export function valveState(symbol: SymbolElement): ValveState {
  const value = String(symbol.properties.valve_state ?? "open").trim().toLocaleLowerCase();
  return CLOSED_STATES.has(value) ? "closed" : "open";
}

export function isValveDefinition(definition: SymbolDefinition | undefined, symbolKey = ""): boolean {
  if (!definition) return symbolKey.toLocaleLowerCase().includes("valve");
  return String(definition.metadata?.capability ?? "").toLocaleLowerCase() === "valve"
    || definition.category.includes("阀")
    || definition.key.toLocaleLowerCase().includes("valve");
}

export function isOpcDefinition(definition: SymbolDefinition | undefined, symbolKey = ""): boolean {
  return String(definition?.metadata?.capability ?? "").toLocaleLowerCase() === "opc"
    || definition?.key.startsWith("off_page_connector_") === true
    || symbolKey.startsWith("off_page_connector_");
}

export function opcDirection(definition: SymbolDefinition | undefined, symbol: SymbolElement): "in" | "out" | null {
  const explicit = String(symbol.properties.opc_direction ?? "").toLocaleLowerCase();
  if (explicit === "in" || explicit === "out") return explicit;
  const metadata = String(definition?.metadata?.opc_direction ?? "").toLocaleLowerCase();
  if (metadata === "in" || metadata === "out") return metadata;
  if (symbol.symbol_key.endsWith("_in")) return "in";
  if (symbol.symbol_key.endsWith("_out")) return "out";
  return null;
}

export function animatedConnector(connector: ConnectorElement): boolean {
  return connector.flow_direction !== "none" && normalizeFlowMedium(connector.medium) !== "other";
}

function directedElementIds(connector: ConnectorElement): [string | null, string | null] {
  const source = connector.source?.element_id ?? null;
  const target = connector.target?.element_id ?? null;
  if (connector.flow_direction === "forward") return [source, target];
  if (connector.flow_direction === "reverse") return [target, source];
  return [null, null];
}

function routeIdentity(connector: ConnectorElement): string {
  const route = String(connector.metadata.main_route_id ?? "").trim();
  if (route) return `route:${route}`;
  if (connector.process_tag.trim()) return `tag:${connector.process_tag.trim().toLocaleLowerCase()}`;
  return `connector:${connector.id}`;
}

export type BlockedFlowFinding = {
  valveId: string;
  connectorIds: string[];
  media: FlowMediumClass[];
  message: string;
};

export function blockedFlowFindings(document: Document, definitions: SymbolDefinition[]): BlockedFlowFinding[] {
  const definitionMap = new Map(definitions.map((definition) => [definition.key, definition]));
  const connectors = document.elements.filter((element): element is ConnectorElement => element.type === "connector");
  const result: BlockedFlowFinding[] = [];
  for (const symbol of document.elements.filter((element): element is SymbolElement => element.type === "symbol")) {
    if (!isValveDefinition(definitionMap.get(symbol.symbol_key), symbol.symbol_key) || valveState(symbol) !== "closed") continue;
    const incoming = connectors.filter((connector) => directedElementIds(connector)[1] === symbol.id);
    if (!incoming.length) continue;
    const outgoing = connectors.filter((connector) => directedElementIds(connector)[0] === symbol.id);
    const identities = new Set([...incoming, ...outgoing].map(routeIdentity));
    const media = [...new Set(incoming.map((connector) => normalizeFlowMedium(connector.medium)))];
    const related = connectors.filter((connector) => identities.has(routeIdentity(connector)));
    const connectorIds = [...new Set([...incoming, ...outgoing, ...related].map((connector) => connector.id))].sort();
    const display = symbol.label.trim() || symbol.id;
    result.push({
      valveId: symbol.id,
      connectorIds,
      media,
      message: `阀门 ${display} 已关闭，${media.join(" / ") || "process"} 介质流动被阻断。`,
    });
  }
  return result.sort((first, second) => first.valveId.localeCompare(second.valveId));
}
