import type { ConnectorElement } from "../types";

function routeLength(connector: ConnectorElement): number {
  return connector.points.slice(0, -1).reduce((total, first, index) => {
    const second = connector.points[index + 1];
    return total + Math.abs(second.x - first.x) + Math.abs(second.y - first.y);
  }, 0);
}

export function visibleFlowArrowConnectors(connectors: ConnectorElement[]): ConnectorElement[] {
  const selected = new Map<string, ConnectorElement>();
  for (const connector of connectors) {
    if (connector.flow_direction === "none") continue;
    const routeValue = connector.metadata.main_route_id;
    const routeId = typeof routeValue === "string" && routeValue ? routeValue : connector.id;
    const key = `${routeId}\u0000${connector.flow_direction}`;
    const current = selected.get(key);
    if (!current
      || routeLength(connector) > routeLength(current)
      || (routeLength(connector) === routeLength(current) && connector.id < current.id)) {
      selected.set(key, connector);
    }
  }
  const selectedIds = new Set([...selected.values()].map((connector) => connector.id));
  return connectors.filter((connector) => selectedIds.has(connector.id));
}
