"""Structured data extraction from documents using AI."""

import json
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.document import Document
from app.models.organization import Organization
from app.models.template import Extraction, ExtractionTemplate
from app.services.ai import _call_llm

logger = logging.getLogger(__name__)


class AIFeatureDisabledError(Exception):
    """Raised when a tenant has this AI capability turned off."""


async def extract_fields(
    session: AsyncSession,
    org_id: uuid.UUID,
    document_id: uuid.UUID,
    template_id: uuid.UUID,
) -> Extraction:
    org_result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = org_result.scalar_one_or_none()
    # Fail closed: a missing org row is treated the same as the flag being off.
    if org is None or not org.ai_extraction_enabled:
        raise AIFeatureDisabledError("AI extraction is disabled for your organization")

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

    text = doc.extracted_text[:60_000]

    prompt = (
        "Extract the following fields from the document text below. "
        "Each field's label describes what to look for, but the value you "
        "return must be the actual data written in the document (a name, "
        "number, date, address, etc.) — never the field label itself, even "
        "if that label also appears verbatim as a heading or caption in the "
        'document. For example, if a field is labeled "Invoice Number" and '
        'the document has a heading "Invoice Number" followed by "4521", '
        'the correct value is "4521", not "Invoice Number".\n'
        "Return ONLY a valid JSON object with the field keys as properties. "
        "If a field's actual value cannot be found, set it to null — do not "
        "fill it in with the label or any other placeholder text. "
        "Do not include any explanation, just the JSON.\n\n"
        f"## Fields to extract:\n{field_desc}\n\n"
        f"## Document text:\n{text}\n\n"
        "## JSON output:"
    )

    # Scale the output budget with field count so the JSON response for
    # templates with many fields doesn't get cut off mid-generation.
    max_tokens = min(8192, 512 + 150 * len(tmpl.fields))
    raw = await _call_llm(prompt, max_tokens=max_tokens)

    data = _parse_json(raw)
    _discard_label_echoes(data, tmpl.fields)

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


def _discard_label_echoes(data: dict, fields: list[dict]) -> None:
    """Null out any field whose "extracted" value is just its own label
    echoed back — a known LLM failure mode when a field's label also
    appears verbatim in the document (e.g. as a heading), and the model
    copies the heading instead of the value that follows it."""
    for f in fields:
        key = f["key"]
        label = str(f.get("label", "")).strip().casefold()
        value = data.get(key)
        if isinstance(value, str) and value.strip().casefold() == label:
            data[key] = None


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
