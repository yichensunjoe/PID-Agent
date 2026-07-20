# Inline equipment insertion, alignment, and viewport controls

## Insert a two-port device into a process line

Place a compatible symbol on the drawing, switch to the selection tool, and drag the symbol over an interior section of an orthogonal process connector. A valid target is highlighted in green and the proposed pipe gap and two bound ports are shown before release.

On release, the editor performs one transaction that:

- moves and rotates the symbol so its two ports follow the selected pipe segment;
- keeps the original connector ID for the upstream portion;
- creates a downstream connector bound to the second symbol port;
- preserves the original layer, system, style, process tag, medium, nominal diameter, flow direction, crossing properties, and `main_route_id`.

Insertion is intentionally rejected when the symbol does not expose exactly two connectable ports, the symbol is already connected, the target segment is locked or non-orthogonal, or the proposed gap is too close to an existing connector endpoint. Rejection is preview-only and does not modify the document.

## Smart guides and explicit alignment

Dragging symbols or junctions near other symbols or junctions shows center or edge guides. The snapped position is used for both the element move and any connected-pipe route updates in the same transaction.

For two or more selected non-connector elements, open **对齐/分布** in the floating canvas toolbar to align left, horizontal center, right, top, vertical middle, or bottom. Three or more selected elements can also be distributed by horizontal or vertical center spacing.

Connected process connectors retain their semantic endpoint bindings. Only endpoint-adjacent route portions are adjusted by the existing local route-preservation logic.

## Viewport and status bar

The canvas status bar displays:

- current cursor coordinates;
- zoom percentage relative to the document page width;
- workspace and grid mode;
- selection count;
- inline-insertion validation feedback while dragging.

Viewport actions include:

- **全部适配**: fit all visible elements;
- **适配选择**: fit the current selection;
- **100%**: restore a one-screen-pixel to one-document-unit view around the current viewport center.

Middle-button panning and wheel zoom remain available in both fixed-page and infinite-workspace modes.
