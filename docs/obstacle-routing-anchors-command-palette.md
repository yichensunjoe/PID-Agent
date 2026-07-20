# Obstacle-aware routing, locked anchors and command palette

Issue #27 adds opt-in professional routing tools without rewriting existing connectors automatically.

## Obstacle-aware connector routing

Select one or more connectors and use **避障** from the floating toolbar, the connector context menu, or the `Ctrl/Cmd + K` command palette.

The editor builds a bounded deterministic orthogonal search lattice from:

- the connector endpoints and existing route corridor;
- inflated symbol, junction, text, rectangle and circle bounds;
- the page working margin when fixed-page mode is active;
- any user-locked route anchors.

The route cost prefers fewer bends, shorter paths and reuse of the existing corridor. Search is bounded by a fixed coordinate and state limit. If no path is found inside those limits, the editor applies a deterministic orthogonal fallback and reports that fallback in the canvas status bar.

The action preserves connector identity, source and target bindings, `main_route_id`, flow direction, arrow position, crossing style and other process metadata.

Existing documents are not batch-rewritten. Avoidance is only run after an explicit user command.

## Locked route anchors

When a connector is selected, every interior route point displays a diamond handle:

- click an unfilled diamond to lock the point;
- click an amber diamond to unlock it;
- right-click a connector segment and choose **在此锁定路由锚点** to insert and lock a point at that location;
- use **清除锚点** to remove all locks from the selected connector or connectors.

Locks are stored in `connector.metadata.locked_route_points` as canvas coordinates. They remain fixed during endpoint reconnection, connected-equipment movement and obstacle-aware rerouting. Segment dragging and dogleg deletion are blocked when they would move or remove a locked point.

Connector duplication translates its anchor coordinates with the copied route. Connector splitting keeps only anchors that still belong to each descendant segment.

## Command palette

Press `Ctrl/Cmd + K` or use the top-bar **命令** button.

The palette supports:

- viewport fit and 100% reset;
- alignment and equal distribution;
- selected-connector rerouting, obstacle avoidance and anchor clearing;
- selection, duplication and deletion;
- tool switching and Agent-panel focus;
- element search by label, process tag, element ID, type, layer or system.

Unavailable commands remain visible but disabled. Search ordering is deterministic and supports exact, substring and compact subsequence matching.

## Validation

Permanent frontend tests cover:

- deterministic obstacle avoidance;
- orthogonality and obstacle-interior rejection;
- bounded fallback behavior;
- locked-anchor preservation during endpoint movement and rerouting;
- anchor insertion and metadata validation;
- command search, disabled-command handling and element/tag lookup.
