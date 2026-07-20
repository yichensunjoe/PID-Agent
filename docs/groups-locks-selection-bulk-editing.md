# Groups, element locks, semantic selection and bulk editing

## Groups

Select two or more editable elements and use **Group** from the floating toolbar, context menu or command palette. The editor writes one shared `editor_group_id` into each member's metadata in a single transaction.

Clicking a grouped member selects every valid member of the group. Hold **Alt** while clicking to address one member without expanding the group. Shift and Alt can be combined for member-level toggle selection.

Group movement uses the existing transaction-backed multi-element translation path. Symbols and junctions move together and affected connector routes are updated in the same transaction. Copying a complete group assigns a new group ID to the copies; copying only part of a group removes stale group identity from the copied elements. When deletion leaves fewer than two valid members, stale group metadata is removed in the same server transaction. If that cleanup would mutate a locked survivor, the transaction is rejected.

## Element locks

Element locks are independent from layer locks and are stored as `metadata.editor_locked = true`.

A locked element remains selectable and inspectable, but cannot be:

- dragged, aligned, distributed or rotated;
- resized or edited through the property inspector;
- rerouted, straightened or given connector bends/anchors;
- deleted, ungrouped or changed by bulk editing;
- modified directly or indirectly by an Agent transaction.

The backend transaction service enforces the lock. Moving or deleting a symbol or junction is also rejected when the operation would rebind or detach a locked connected connector. Unlocking is permitted only through an exact metadata-only unlock patch; unrelated metadata cannot be changed as part of the unlock.

Layer locks continue to take precedence. An element on a locked layer cannot be edited or have its element lock changed until the layer is unlocked.

## Semantic selection

The active element can be used to select all visible elements with the same:

- element type;
- layer;
- system;
- connector process tag;
- editor group;
- connector route family (`main_route_id` or branch family).

**Invert selection** operates over visible layers and systems only. Context-menu selection commands explicitly use the element that was right-clicked as their reference, including when that element belongs to a group.

## Bulk property editing

When multiple elements are selected, the property panel exposes common transaction-backed fields:

- layer and system;
- stroke, fill, line width, opacity and dash pattern;
- for connector-only selections: flow direction, arrow position and crossing style.

A field with different values across the selection is displayed as **mixed** and is left unchanged unless a value is entered. All generated element updates are submitted in one transaction and preserve unrelated metadata, connector endpoints and route identity.

Bulk editing is disabled when any selected element has an element lock or belongs to a locked layer. Heterogeneous selections do not expose connector-only fields.

## Metadata compatibility

Grouping and element locking use the existing generic element metadata object and require no document schema migration or new backend endpoint. Documents without these keys retain their previous behavior. The keys do not alter SVG geometry or connector endpoint semantics.
