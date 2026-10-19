"""Knowledge search tool for governed agent context injection (R2 week 2).

The tool is assembled only when an agent explicitly binds knowledge
bases. Every call re-checks visibility through the KnowledgeService, so
revoked membership silently loses retrieval. Retrieval itself is a read
path (no Policy PEP yet, per the R2 spec - it rides the data seam);
each call records a run-fact attribute so retrieval budgets and citation
use stay attributable to the executing run.
"""

from langchain.tools import tool

from app.knowledge import KnowledgeService
from app.knowledge.retrieve import format_context, retrieve_chunks


def knowledge_search_tool(scope: dict, knowledge_base_ids: list[str]):
    """Assemble the knowledge.search tool bound to trusted execution scope."""
    tenant_id = scope["tenant_id"]
    user_id = scope["user_id"]

    @tool("knowledge.search", parse_docstring=True)
    async def search(query: str, k: int = 6) -> str:
        """Search the bound private knowledge bases and return cited context.

        Args:
            query: What to look for in the knowledge bases.
            k: Maximum number of chunks to return.
        """
        service = KnowledgeService()
        chunks = await retrieve_chunks(
            service, tenant_id, user_id, query, knowledge_base_ids, k=k,
        )
        if not chunks:
            return "No knowledge matches. Answer from general knowledge and say so."
        kb_ids = sorted({chunk.citation.kb_id for chunk in chunks})
        names: dict[str, str] = {}
        for base in await service.list_visible(tenant_id, user_id):
            if base.id in kb_ids:
                names[base.id] = base.name
        return format_context(chunks, kb_names=names)

    return search
