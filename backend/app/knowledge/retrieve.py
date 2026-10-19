"""Retrieval with citations for tenant-scoped knowledge bases.

Adapted from Octop v1.0.2b6 (eb280112) infra/knowledge/retrieve.py and
citations.py (MIT). Ranking, char budget and the machine-readable
citation marker are unchanged; the seams are:

- visibility: upstream user_id/is_admin -> PrismOS KnowledgeService
  per-call membership check (revocation is immediate);
- readiness: upstream document.status -> index_state == "ready";
- embedding: injected through the embedding function so the deterministic
  week-1 hash vectors and the week-2 remote endpoint share one path.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.knowledge.index import KnowledgeIndex
from app.models.knowledge import KnowledgeDocumentRecord

CITATIONS_MARKER_PREFIX = "<!--prismos-kb-citations:"
CITATIONS_MARKER_SUFFIX = "-->"

DEFAULT_RETRIEVAL_K = 6
DEFAULT_CONTEXT_CHAR_BUDGET = 6000

EmbeddingFn = Callable[[Sequence[str]], list[list[float]]]


def hash_embed_chunks(chunks: Sequence[str]) -> list[list[float]]:
    """Deterministic fallback embedding (week 1); shared with the upload route."""
    from hashlib import sha256

    dimensions = 64
    vectors: list[list[float]] = []
    for text in chunks:
        vector = [0.0] * dimensions
        for token in text.lower().split():
            digest = int(sha256(token.encode()).hexdigest()[:8], 16)
            vector[digest % dimensions] += 1.0
        vectors.append(vector)
    return vectors


@dataclass(frozen=True)
class Citation:
    kb_id: str
    kb_name: str
    doc_id: str
    filename: str
    content_hash: str
    version: int


@dataclass(frozen=True)
class RetrievedChunk:
    text: str
    score: float
    ordinal: int
    citation: Citation


def citations_from_chunks(chunks: Sequence[RetrievedChunk]) -> list[dict]:
    seen: set[str] = set()
    out: list[dict] = []
    for chunk in chunks:
        if chunk.citation.doc_id in seen:
            continue
        seen.add(chunk.citation.doc_id)
        out.append({
            "kb_id": chunk.citation.kb_id,
            "kb_name": chunk.citation.kb_name,
            "doc_id": chunk.citation.doc_id,
            "filename": chunk.citation.filename,
            "content_hash": chunk.citation.content_hash,
            "version": chunk.citation.version,
        })
    return out


_CITATIONS_MARKER_RE = re.compile(
    r"\n*\s*"
    + re.escape(CITATIONS_MARKER_PREFIX)
    + r"\[.*?\]"
    + re.escape(CITATIONS_MARKER_SUFFIX)
    + r"\s*$",
    re.DOTALL,
)


def append_citations_marker(text: str, citations: Sequence[dict]) -> str:
    body = (text or "").rstrip()
    if not body or not citations:
        return body
    payload = json.dumps(list(citations), ensure_ascii=False, separators=(",", ":"))
    return f"{body}\n\n{CITATIONS_MARKER_PREFIX}{payload}{CITATIONS_MARKER_SUFFIX}"


def strip_citations_marker(text: str) -> str:
    return _CITATIONS_MARKER_RE.sub("", text)


async def retrieve_chunks(
    service,
    tenant_id: str,
    user_id: str,
    query: str,
    knowledge_base_ids: Sequence[str],
    *,
    k: int = DEFAULT_RETRIEVAL_K,
    embed: EmbeddingFn = hash_embed_chunks,
) -> list[RetrievedChunk]:
    """Search the caller's visible knowledge bases and return cited chunks.

    Visibility is re-checked per call through the KnowledgeService: bases the
    user cannot currently read are skipped even if explicitly requested, so
    revoked membership means immediate loss of retrieval. Only documents whose
    index_state is ready participate.
    """
    query_text = (query or "").strip()
    if not query_text or k <= 0:
        return []
    selected_ids = list(dict.fromkeys(str(kb_id).strip() for kb_id in knowledge_base_ids if str(kb_id).strip()))
    if not selected_ids:
        return []

    query_vector = embed([query_text])[0]
    ranked: list[tuple[float, RetrievedChunk]] = []
    for kb_id in selected_ids:
        if not await service.can_read(tenant_id, kb_id, user_id):
            continue
        documents = await service.list_documents(tenant_id, kb_id, user_id)
        if not documents:
            continue
        ready: dict[str, KnowledgeDocumentRecord] = {
            document.id: document for document in documents if document.index_state == "ready"
        }
        if not ready:
            continue
        for hit in KnowledgeIndex(tenant_id, kb_id).search(query_vector, k=k):
            document = ready.get(hit.doc_id)
            if document is None:
                continue
            citation = Citation(
                kb_id=kb_id, kb_name="", doc_id=document.id, filename=document.filename,
                content_hash=document.content_hash, version=document.version,
            )
            ranked.append((hit.score, RetrievedChunk(
                text=hit.text, score=hit.score, ordinal=hit.ordinal, citation=citation,
            )))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [chunk for _, chunk in ranked[:k]]


def format_context(
    chunks: Sequence[RetrievedChunk],
    *,
    kb_names: dict[str, str] | None = None,
    char_budget: int = DEFAULT_CONTEXT_CHAR_BUDGET,
) -> str:
    """Format retrieved chunks into a cited context block with a citation marker."""
    names = kb_names or {}
    sections: list[str] = []
    remaining = char_budget
    for chunk in chunks:
        citation = f"[{chunk.citation.filename}#{chunk.ordinal + 1}] "
        if remaining <= len(citation):
            break
        text = chunk.text.strip()[: remaining - len(citation)]
        if not text:
            continue
        section = f"{citation}{text}"
        sections.append(section)
        remaining -= len(section)
    if not sections:
        return ""
    body = "Knowledge context (cited [filename#chunk]):\n\n" + "\n\n".join(sections)
    cited = [
        {**c, "kb_name": names.get(c["kb_id"], c["kb_name"])} for c in citations_from_chunks(chunks)
    ]
    return append_citations_marker(body, cited)
