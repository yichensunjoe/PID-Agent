# JSON and project package import/export

P&ID-Agent supports two versioned JSON formats for moving engineering documents between installations. Both formats are validated completely before SQLite is changed. An invalid document, unsupported version, broken endpoint reference, or persistence conflict leaves the existing project unchanged.

## Supported formats

### Single document

The preferred document export is `pid-agent.document` version 1:

```json
{
  "format": "pid-agent.document",
  "version": 1,
  "document": {
    "id": "doc_example",
    "name": "Process Unit A",
    "revision": 4,
    "layers": [],
    "systems": [],
    "elements": [],
    "metadata": {}
  }
}
```

The importer also accepts the legacy raw `Document` JSON produced by `/api/v2/documents/{document_id}/export.json`. Existing consumers of that endpoint remain compatible. New integrations should prefer `/export-v1.json`, because its format and version are explicit.

### Project package

A project package carries project settings and one or more documents:

```json
{
  "format": "pid-agent.project-package",
  "version": 1,
  "project": {
    "name": "Expansion Project",
    "metadata": {
      "project_number": "P-200",
      "revision": "B"
    }
  },
  "documents": []
}
```

The package deliberately excludes `symbols.json`, external symbol paths, unit-symbol imports, API keys, local preferences, diagnostics, history snapshots, and browser data. A package containing unknown top-level fields such as embedded symbol data is rejected.

## Validation and atomicity

Before writing, the service validates the complete Pydantic document schema and engineering references, including:

- format and version;
- unique document and element IDs;
- layers and systems;
- symbol keys and bound port IDs;
- connector endpoint element references and endpoint coordinates;
- orthogonal/manual connector geometry;
- structured metadata such as `main_route_id`, route anchors, flow, crossing, groups, and locks.

A project package is imported in one SQLite transaction. All documents and project settings succeed together or all writes are rolled back. A failed import does not overwrite an existing document, consume a generated document ID, create history rows, or leave a partial project.

## ID conflicts

Both import endpoints accept `conflict_policy`:

- `regenerate` (default): keep every element ID and internal reference unchanged, but deterministically assign a new document ID when the incoming document ID already exists;
- `reject`: return HTTP 409 without writing anything.

The response includes `document_id_map`, which maps each conflicting source document ID to its imported ID. Element IDs are not silently rewritten. Duplicate document IDs inside one project package are invalid.

## REST API

```text
GET  /api/v2/documents/{document_id}/export.json
GET  /api/v2/documents/{document_id}/export-v1.json
POST /api/v2/imports/document?conflict_policy=regenerate

GET  /api/v2/project/settings
PUT  /api/v2/project/settings
GET  /api/v2/project/export.json
POST /api/v2/imports/project-package?conflict_policy=regenerate
```

Example document import:

```bash
curl -X POST \
  'http://127.0.0.1:8000/api/v2/imports/document?conflict_policy=regenerate' \
  -H 'Content-Type: application/json' \
  --data-binary @unit-a.pid.json
```

Validation errors use a stable error code:

```json
{
  "detail": {
    "error": "unsupported_version",
    "message": "unsupported pid-agent.document version: 2; supported version is 1",
    "retryable": false
  }
}
```

## Browser workflow

The document sidebar provides separate **导入 JSON** and **导入项目包** actions. A successful import opens the first imported document. The project summary displays the imported project name and metadata. A validation or persistence error remains visible and explicitly states that the current project was not changed.

Versioned document JSON and the complete project package can be downloaded from the editor toolbar. After import, documents use the normal transaction path and remain editable, persistent, undoable, and redoable.

## Python Client

The installed package remains `pid-agent`, with the compatible `agentcad` import path:

```python
from agentcad.client import AgentCADClient

with AgentCADClient("http://127.0.0.1:8000") as cad:
    envelope = cad.export_document_envelope("doc_example")
    imported = cad.import_document(
        envelope.model_dump(mode="json"),
        conflict_policy="regenerate",
    )
    imported_document = imported.documents[0]

    cad.update_project_settings({
        "name": "Expansion Project",
        "metadata": {"project_number": "P-200"},
    })
    package = cad.export_project_package()
    project_result = cad.import_project_package(
        package,
        conflict_policy="regenerate",
    )
```

The methods return validated `DocumentEnvelope`, `ProjectPackageEnvelope`, `ProjectSettings`, and `ImportResult` models.

## Compatibility and version policy

Version 1 is the only supported version. A missing or future version in a versioned envelope is rejected rather than guessed or silently migrated. The legacy raw document format remains importable for backward compatibility. Future format migrations must be explicit, tested, and lossless for engineering semantics.
