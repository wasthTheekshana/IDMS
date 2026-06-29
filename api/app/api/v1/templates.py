import csv
import io
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.core.deps import AuthSession, CurrentUserDep
from app.models.document import Document
from app.models.template import Extraction, ExtractionTemplate
from app.schemas.template import (
    ExtractionResponse,
    ExtractionRow,
    ExtractRequest,
    TemplateCreate,
    TemplateResponse,
    TemplateUpdate,
)
from app.services.extraction import extract_fields

router = APIRouter(prefix="/templates", tags=["templates"])

_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(v: str) -> str:
    if v and v[0] in _FORMULA_PREFIXES:
        return "'" + v
    return v


@router.post("", response_model=TemplateResponse, status_code=201)
async def create_template(
    body: TemplateCreate,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> TemplateResponse:
    tmpl = ExtractionTemplate(
        id=uuid.uuid4(),
        org_id=current_user.org_id,
        name=body.name,
        description=body.description,
        fields=[f.model_dump() for f in body.fields],
    )
    session.add(tmpl)
    await session.flush()
    return TemplateResponse.model_validate(tmpl)


@router.get("", response_model=list[TemplateResponse])
async def list_templates(
    current_user: CurrentUserDep,
    session: AuthSession,
) -> list[TemplateResponse]:
    result = await session.execute(
        select(ExtractionTemplate)
        .where(ExtractionTemplate.org_id == current_user.org_id)
        .order_by(ExtractionTemplate.created_at.desc())
    )
    return [TemplateResponse.model_validate(t) for t in result.scalars().all()]


@router.patch("/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: uuid.UUID,
    body: TemplateUpdate,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> TemplateResponse:
    result = await session.execute(
        select(ExtractionTemplate).where(
            ExtractionTemplate.id == template_id,
            ExtractionTemplate.org_id == current_user.org_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    if body.name is not None:
        tmpl.name = body.name
    if body.description is not None:
        tmpl.description = body.description
    if body.fields is not None:
        tmpl.fields = [f.model_dump() for f in body.fields]
    await session.flush()
    return TemplateResponse.model_validate(tmpl)


@router.delete("/{template_id}", status_code=204)
async def delete_template(
    template_id: uuid.UUID,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> None:
    result = await session.execute(
        select(ExtractionTemplate).where(
            ExtractionTemplate.id == template_id,
            ExtractionTemplate.org_id == current_user.org_id,
        )
    )
    tmpl = result.scalar_one_or_none()
    if not tmpl:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    await session.delete(tmpl)


@router.post("/extract", response_model=ExtractionResponse)
async def run_extraction(
    body: ExtractRequest,
    current_user: CurrentUserDep,
    session: AuthSession,
) -> ExtractionResponse:
    try:
        extraction = await extract_fields(
            session, current_user.org_id, body.document_id, body.template_id
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    return ExtractionResponse.model_validate(extraction)


@router.get("/extractions", response_model=list[ExtractionRow])
async def list_extractions(
    current_user: CurrentUserDep,
    session: AuthSession,
    template_id: uuid.UUID | None = None,
) -> list[ExtractionRow]:
    q = (
        select(Extraction, Document.filename, ExtractionTemplate.name)
        .join(Document, Document.id == Extraction.document_id)
        .join(ExtractionTemplate, ExtractionTemplate.id == Extraction.template_id)
        .where(Extraction.org_id == current_user.org_id)
        .order_by(Extraction.created_at.desc())
    )
    if template_id:
        q = q.where(Extraction.template_id == template_id)

    result = await session.execute(q)
    rows = []
    for ext, filename, tmpl_name in result.all():
        rows.append(
            ExtractionRow(
                document_id=ext.document_id,
                filename=filename,
                template_name=tmpl_name,
                data=ext.data,
                created_at=ext.created_at,
            )
        )
    return rows


@router.get("/extractions/export/csv")
async def export_csv(
    current_user: CurrentUserDep,
    session: AuthSession,
    template_id: uuid.UUID | None = None,
) -> StreamingResponse:
    q = (
        select(Extraction, Document.filename, ExtractionTemplate)
        .join(Document, Document.id == Extraction.document_id)
        .join(ExtractionTemplate, ExtractionTemplate.id == Extraction.template_id)
        .where(Extraction.org_id == current_user.org_id)
        .order_by(Extraction.created_at.desc())
    )
    if template_id:
        q = q.where(Extraction.template_id == template_id)

    result = await session.execute(q)
    rows = result.all()

    if not rows:
        buf = io.StringIO()
        buf.write("No data\n")
        buf.seek(0)
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": 'attachment; filename="extractions.csv"'},
        )

    all_fields: list[str] = []
    seen: set[str] = set()
    for _, _, tmpl in rows:
        for f in tmpl.fields:
            if f["key"] not in seen:
                all_fields.append(f["key"])
                seen.add(f["key"])

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Filename", "Template", "Extracted At"] + all_fields)

    for ext, filename, tmpl in rows:
        row = [_safe_cell(filename), _safe_cell(tmpl.name), ext.created_at.isoformat()]
        for key in all_fields:
            val = ext.data.get(key, "")
            row.append(_safe_cell(str(val)) if val is not None else "")
        writer.writerow(row)

    buf.seek(0)
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": 'attachment; filename="extractions.csv"',
        },
    )


@router.get("/extractions/export/excel")
async def export_excel(
    current_user: CurrentUserDep,
    session: AuthSession,
    template_id: uuid.UUID | None = None,
) -> StreamingResponse:
    from openpyxl import Workbook
    from openpyxl.styles import Font

    q = (
        select(Extraction, Document.filename, ExtractionTemplate)
        .join(Document, Document.id == Extraction.document_id)
        .join(ExtractionTemplate, ExtractionTemplate.id == Extraction.template_id)
        .where(Extraction.org_id == current_user.org_id)
        .order_by(Extraction.created_at.desc())
    )
    if template_id:
        q = q.where(Extraction.template_id == template_id)

    result = await session.execute(q)
    rows = result.all()

    all_fields: list[str] = []
    seen: set[str] = set()
    for _, _, tmpl in rows:
        for f in tmpl.fields:
            if f["key"] not in seen:
                all_fields.append(f["key"])
                seen.add(f["key"])

    wb = Workbook()
    ws = wb.active
    ws.title = "Extractions"

    headers = ["Filename", "Template", "Extracted At"] + all_fields
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True)

    for ext, filename, tmpl in rows:
        row = [_safe_cell(filename), _safe_cell(tmpl.name), ext.created_at.isoformat()]
        for key in all_fields:
            val = ext.data.get(key, "")
            row.append(_safe_cell(str(val)) if val is not None else "")
        ws.append(row)

    for col in ws.columns:
        max_len = max(len(str(cell.value or "")) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": 'attachment; filename="extractions.xlsx"',
        },
    )
