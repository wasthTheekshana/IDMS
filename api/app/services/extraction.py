"""Structured data extraction from documents using AI."""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.template import Extraction, ExtractionTemplate
from app.services.ai import _call_llm

logger = logging.getLogger(__name__)


async def extract_fields(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    template_id: uuid.UUID,
) -> Extraction:
    doc_result = await session.execute(
        select(Document).where(Document.id == document_id, Document.org_id == org_id)
    )
    doc = doc_result.scalar_one_or_none()
    if not doc or not doc.extracted_text:
        raise ValueError("Document not found or has no text")

    tmpl_result = await session.execute(
        select(ExtractionTemplate).where(
            ExtractionTemplate.id == template_id,
            ExtractionTemplate.org_id == org_id,
        )
    )
    tmpl = tmpl_result.scalar_one_or_none()
    if not tmpl:
        raise ValueError("Template not found")

    field_desc = "\n".join(
        f'- "{f["key"]}": {f["label"]} (type: {f.get("type", "text")})'
        for f in tmpl.fields
    )

    text = doc.extracted_text[:12_000]

    prompt = (
        "Extract the following fields from the document text below. "
        "Return ONLY a valid JSON object with the field keys as properties. "
        "If a field cannot be found, set its value to null. "
        "Do not include any explanation, just the JSON.\n\n"
        f"## Fields to extract:\n{field_desc}\n\n"
        f"## Document text:\n{text}\n\n"
        "## JSON output:"
    )

    raw = await _call_llm(prompt)

    data = _parse_json(raw)

    extraction = Extraction(
        id=uuid.uuid4(),
        org_id=org_id,
        document_id=document_id,
        template_id=template_id,
        data=data,
    )
    session.add(extraction)
    await session.flush()
    return extraction


def _parse_json(raw: str) -> dict:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [line for line in lines if not line.strip().startswith("```")]
        cleaned = "\n".join(lines)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                return json.loads(cleaned[start:end])
            except json.JSONDecodeError:
                pass
        return {"_raw": raw, "_error": "Failed to parse AI response as JSON"}
