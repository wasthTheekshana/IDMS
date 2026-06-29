"""AI service — document Q&A and summarization via Groq/Gemini."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.document import Document
from app.repositories.chunk import ChunkRepository
from app.services.embed import MistralEmbed, StubEmbed


async def _get_relevant_chunks(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID | None,
    question: str,
    limit: int | None = None,
) -> list[dict[str, object]]:
    """Retrieve top-K chunks via semantic search, optionally filtered to one doc."""
    k = limit or settings.AI_MAX_CONTEXT_CHUNKS
    provider: MistralEmbed | StubEmbed = (
        MistralEmbed() if settings.MISTRAL_API_KEY else StubEmbed()
    )
    vecs = await provider.embed_batch([question])
    query_vec = vecs[0]

    repo = ChunkRepository(session)
    chunks = await repo.semantic_search(org_id, query_vec, limit=k)

    if document_id:
        chunks = [c for c in chunks if c.document_id == document_id]

    return [
        {
            "page": c.page,
            "content": c.content,
            "document_id": str(c.document_id),
        }
        for c in chunks
    ]


def _build_context(chunks: list[dict[str, object]]) -> str:
    parts = []
    for i, c in enumerate(chunks):
        parts.append(f"[Chunk {i + 1}, page {c['page']}]\n{c['content']}")
    return "\n\n".join(parts)


async def ask_document(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    question: str,
) -> dict[str, object]:
    """RAG Q&A: retrieve relevant chunks from one document, ask Gemini."""
    chunks = await _get_relevant_chunks(session, org_id, document_id, question)
    if not chunks:
        return {
            "answer": "No relevant content found in this document.",
            "sources": [],
        }

    context = _build_context(chunks)
    prompt = (
        "You are a document analysis assistant. "
        "Answer the question based ONLY on the provided context. "
        "If the answer is not in the context, say so.\n\n"
        f"## Context\n{context}\n\n"
        f"## Question\n{question}"
    )

    answer = await _call_llm(prompt)
    sources = [{"page": c["page"], "excerpt": str(c["content"])[:200]} for c in chunks]
    return {"answer": answer, "sources": sources}


async def ask_org(
    session: AsyncSession,
    org_id: uuid.UUID,
    question: str,
) -> dict[str, object]:
    """RAG Q&A across all org documents."""
    chunks = await _get_relevant_chunks(session, org_id, None, question)
    if not chunks:
        return {"answer": "No relevant documents found.", "sources": []}

    context = _build_context(chunks)
    prompt = (
        "You are a document analysis assistant. "
        "Answer based ONLY on the provided context. "
        "Cite the source chunk numbers.\n\n"
        f"## Context\n{context}\n\n"
        f"## Question\n{question}"
    )

    answer = await _call_llm(prompt)

    doc_ids = list({str(c["document_id"]) for c in chunks})
    doc_result = await session.execute(
        select(Document).where(Document.id.in_([uuid.UUID(d) for d in doc_ids]))
    )
    docs = {str(d.id): d.filename for d in doc_result.scalars().all()}

    sources = [
        {
            "document_id": str(c["document_id"]),
            "filename": docs.get(str(c["document_id"]), "unknown"),
            "page": c["page"],
            "excerpt": str(c["content"])[:200],
        }
        for c in chunks
    ]
    return {"answer": answer, "sources": sources}


async def summarize_document(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
) -> str:
    """Generate a summary from the document's extracted text."""
    result = await session.execute(
        select(Document).where(
            Document.id == document_id,
            Document.org_id == org_id,
        )
    )
    doc = result.scalar_one_or_none()
    if not doc or not doc.extracted_text:
        return "No text available to summarize."

    text = doc.extracted_text[:15_000]
    prompt = (
        "Summarize the following document concisely. "
        "Include key points, main topics, and any important details. "
        "Use bullet points for clarity.\n\n"
        f"## Document: {doc.filename}\n{text}"
    )
    return await _call_llm(prompt)


async def _call_llm(prompt: str) -> str:
    """Call LLM: Groq (primary) → Gemini (fallback)."""
    if settings.GROQ_API_KEY:
        return await _call_groq(prompt)
    if settings.GOOGLE_AI_API_KEY:
        return await _call_llm(prompt)
    return "[AI disabled: no GROQ_API_KEY or GOOGLE_AI_API_KEY configured]"


async def _call_groq(prompt: str) -> str:
    try:
        from groq import AsyncGroq

        client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        response = await client.chat.completions.create(
            model=settings.GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=settings.AI_MAX_RESPONSE_TOKENS,
        )
        return response.choices[0].message.content or "[No response from AI]"
    except Exception as exc:
        return f"[AI error: {exc}]"


async def _call_gemini(prompt: str) -> str:
    try:
        from google import genai

        client = genai.Client(api_key=settings.GOOGLE_AI_API_KEY)
        response = await client.aio.models.generate_content(
            model=settings.GEMINI_MODEL,
            contents=prompt,
        )
        return response.text or "[No response from AI]"
    except Exception as exc:
        return f"[AI error: {exc}]"
