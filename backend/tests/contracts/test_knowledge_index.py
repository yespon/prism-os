"""R2 index and chunk contracts: migrated logic, tenant-scoped layout."""

from pathlib import Path

import pytest

from app.knowledge.chunk import chunk_text
from app.knowledge.index import Hit, KnowledgeIndex, knowledge_index_dir


def test_chunk_text_fixed_windows():
    text = "abcdefghij" * 100  # 1000 chars
    chunks = chunk_text(text, size=800, overlap=120)
    assert all(len(c) <= 800 for c in chunks)
    assert chunks, "non-empty text produces chunks"
    # Overlap: the second window starts size-overlap into the first.
    assert chunks[1][:10] == chunks[0][680:690]
    assert chunk_text("   ") == []
    with pytest.raises(ValueError):
        chunk_text("x", size=0)
    with pytest.raises(ValueError):
        chunk_text("x", size=10, overlap=10)


def test_index_roundtrip_and_delete(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path))
    index = KnowledgeIndex("t1", "kb-1")
    assert index.path.parent == knowledge_index_dir("t1", "kb-1")

    texts = ["alpha beta", "gamma delta"]
    embeddings = [[1.0, 0.0], [0.0, 1.0]]
    index.replace_doc_chunks("doc-1", texts, embeddings, metadata=[{"version": 1}, {"version": 1}])

    hits = index.search([1.0, 0.0], k=2)
    assert hits[0].doc_id == "doc-1" and hits[0].text == "alpha beta"
    assert hits[0].metadata == {"version": 1}
    assert hits[0].score == pytest.approx(1.0)

    index.delete_doc("doc-1")
    assert index.search([1.0, 0.0], k=2) == []


def test_index_replaces_document_chunks_atomically(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path))
    index = KnowledgeIndex("t1", "kb-2")
    index.replace_doc_chunks("doc-1", ["old text"], [[1.0, 1.0]])
    index.replace_doc_chunks("doc-1", ["new text one", "new text two"], [[1.0, 0.0], [0.0, 1.0]])
    hits = index.search([1.0, 0.0], k=10)
    assert sorted(hit.text for hit in hits) == ["new text one", "new text two"]
    assert all("old" not in hit.text for hit in hits)


def test_index_tenant_scoped_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("PRISMOS_HOME", str(tmp_path))
    a = KnowledgeIndex("tenant-a", "kb-1").path
    b = KnowledgeIndex("tenant-b", "kb-1").path
    assert a != b
    assert Path(str(a)).parent.parts[-2] == "tenant-a"
    assert Path(str(b)).parent.parts[-2] == "tenant-b"


def test_hit_dataclass_fields():
    hit = Hit(chunk_id="c", doc_id="d", ordinal=0, text="t", score=0.5, metadata={"k": "v"})
    assert hit.metadata == {"k": "v"}
    assert (hit.chunk_id, hit.doc_id, hit.ordinal, hit.score) == ("c", "d", 0, 0.5)
