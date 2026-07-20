# Agent canvas preview and minimap navigation

## Agent ghost preview

A valid compiled manual Agent plan is simulated in the browser before it is applied. The simulator accepts element add, update and delete operations only, verifies the expected document revision and constructs a detached element graph without mutating the workspace document.

The canvas renders the simulation as a non-interactive overlay:

- green dashed geometry: elements that will be added;
- purple faded and dashed geometry: the before and after states of updated elements;
- red dashed geometry: elements that will be deleted.

Connector endpoints are refreshed against simulated symbol ports and junction nodes. Direct and orthogonal connectors are rerouted deterministically; manual connectors preserve their middle route while rebinding moved endpoints. Unsupported operation families or stale revisions produce a warning badge instead of an inaccurate preview.

Use **定位预览** in the canvas badge to fit all affected before/after geometry. Applying, discarding or replanning replaces the overlay through the existing Agent state. A document switch or revision change clears the stale manual preview.

## Structured issue focus

When a validation issue contains an `element_id` or `connector_id` that still exists in the current document, the issue card exposes **画布定位**. The action selects the referenced element and fits it in the editor. Issues without a resolvable ID retain their textual diagnostics without changing selection.

## Minimap

The minimap shows simplified bounds for visible elements and the current viewport rectangle. In fixed-page mode it also shows the page boundary. In infinite mode it is omitted when there is no element extent.

Click or drag inside the minimap to recenter the main viewport. The transform is derived from document coordinates and the current content extent, so navigation is independent of browser zoom and SVG screen scale.

## Safety

Ghost preview never submits a transaction and does not change the document revision. The minimap is a viewport control only. Normal selection, connector hit targets, wheel zoom and middle-button panning remain unchanged.
