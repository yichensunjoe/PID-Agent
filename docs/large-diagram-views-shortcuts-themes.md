# Large-diagram views, custom shortcuts and application themes

This slice adds browser-local navigation and appearance preferences without changing the engineering document model.

## Automatic zones

Visible elements are assigned to deterministic non-empty navigation cells using their geometric centers. Empty cells are omitted and the remaining zones are ordered by row and column. The current zone follows the center of the active canvas viewport.

Open **Views** from the top bar or use the configured `views:open` shortcut to:

- inspect automatic zone labels and visible element counts;
- fit the canvas to a zone;
- see which zone currently contains the viewport center.

Zone calculation only reads visible engineering elements. It does not add annotations, modify elements or create a document revision.

## Named views

The same Views dialog can save the current canvas viewport as a named bookmark. Named views can be opened, renamed and deleted.

Named views are:

- scoped by document ID;
- stored only in browser `localStorage`;
- limited and sanitized before use;
- discarded safely when stored data is malformed;
- cleared from the active UI when another document is opened.

They do not travel with SVG exports or document JSON.

## Custom shortcuts

Open **Preferences** or use the configured `settings:open` shortcut. Click a shortcut field and press the desired chord.

Shortcut behavior:

- `Ctrl` and `Command` are normalized to `Mod`;
- modifier order is normalized to `Mod`, `Alt`, `Shift`;
- duplicate active assignments block saving and identify the conflict;
- Backspace or Delete clears a shortcut assignment;
- resetting restores the shipped defaults;
- ordinary commands do not run while typing in an input, textarea, select or editable field;
- the command-palette shortcut remains available while typing.

Custom shortcuts execute the same command IDs and applicability checks as the command palette. They do not bypass disabled-command guards.

## Application appearance

Appearance modes are:

- **Follow system**;
- **Light**;
- **Dark**.

The selected mode is stored in browser preferences. Follow-system mode reacts to operating-system color-scheme changes.

Theme styling applies to application chrome, panels, dialogs, menus, toolbars and overlays. It intentionally does not recolor the SVG canvas, engineering elements, document background or exported files.

## Storage and revision boundary

The following data remains browser-local:

- workspace/page mode;
- grid preference;
- application appearance;
- shortcut overrides;
- named viewport bookmarks.

Changing any of these preferences must not call the document transaction API or increment the engineering document revision.
