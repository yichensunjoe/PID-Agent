from pathlib import Path

import pytest

from agentcad.models import Document
from agentcad.store import (
    SQLiteDocumentStore,
    StoredDocument,
    StoreRevisionConflictError,
)


def test_delete_compares_revision_atomically_and_preserves_stale_target(tmp_path: Path):
    store = SQLiteDocumentStore(tmp_path / "store.db")
    document = Document(name="Revision guarded")
    store.save(StoredDocument(document=document, undo_stack=[], redo_stack=[]))

    with pytest.raises(StoreRevisionConflictError, match="current revision is 0"):
        store.delete(document.id, expected_revision=1)

    assert store.get(document.id) is not None
    assert store.delete(document.id, expected_revision=0) is True
    assert store.get(document.id) is None
    assert store.delete(document.id, expected_revision=0) is False
