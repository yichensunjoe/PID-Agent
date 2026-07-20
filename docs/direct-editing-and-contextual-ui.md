# Direct editing and contextual UI

Issue #21 adds a first usability layer for high-frequency P&ID editing without changing the document schema.

## Connector editing

Select a process connector to show endpoint and segment handles. Every orthogonal segment can be dragged, including the first and last segments; bound source and target points remain fixed while a local dogleg is introduced when required.

The floating toolbar and connector context menu provide:

- **Add bend**: inserts a short editable subsegment on the chosen or longest connector segment.
- **Remove bend**: removes a local dogleg when the surrounding route can be joined on one axis.
- **Straighten**: replaces the route with a deterministic one-elbow orthogonal path.
- **Reroute**: returns the connector to automatic midpoint-based orthogonal routing.
- **Reverse flow**: toggles the formal connector flow direction rather than adding arrow text.

Dragging a connector endpoint preserves the unaffected route and changes the connector to manual routing, unless it is a direct connector.

## Moving connected equipment

Moving symbols or junctions submits the element moves and explicit manual connector updates in one transaction. Only endpoint-adjacent route portions are adjusted. Middle detours remain stable, and endpoint `element_id` / `port_id` bindings are retained.

Use **Reroute** when a full automatic route replacement is desired.

## Creating a branch from a main connector

Activate the process connector tool and drag from an interior point of an existing connector. Releasing the pointer creates one atomic transaction that:

1. creates a real junction;
2. splits the original connector into two bound main-route descendants;
3. creates a branch bound to the junction `node` port;
4. preserves the original layer, system, style, medium and main-route identity.

Starting too close to an existing connector endpoint is rejected so endpoint reconnection remains unambiguous.

## Contextual controls

A compact floating toolbar appears for the current selection. Right-clicking a symbol or connector opens element-specific commands close to the pointer. Provider configuration, process context and detailed Agent results are collapsed by default so the normal Agent workflow stays focused on the instruction and automatic execution controls.
