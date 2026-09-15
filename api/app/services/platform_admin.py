"""Platform-admin cross-org queries. Every function here receives a session
opened via core/deps.py:get_admin_db (the BYPASSRLS idms_platform_admin
role) — these queries deliberately span every organization."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.api_usage import ApiUsage
from app.models.document import Document
from app.models.organization import Organization
from app.models.user import User
from app.schemas.platform_admin import (
    AdminDocumentResponse,
    AdminOrganizationResponse,
    AdminOrgUpdateRequest,
)


async def _build_org_response(
    session: AsyncSession, org: Organization
) -> AdminOrganizationResponse:
    user_count = (
        await session.execute(select(func.count(User.id)).where(User.org_id == org.id))
    ).scalar_one()
    document_count = (
        await session.execute(
            select(func.count(Document.id)).where(Document.org_id == org.id)
        )
    ).scalar_one()
    tokens_total, cost_total = (
        await session.execute(
            select(
                func.coalesce(func.sum(ApiUsage.tokens_used), 0),
                func.coalesce(func.sum(ApiUsage.cost_usd), 0.0),
            ).where(ApiUsage.org_id == org.id)
        )
    ).one()

    return AdminOrganizationResponse(
        id=org.id,
        name=org.name,
        slug=org.slug,
        plan=org.plan,
        is_suspended=org.is_suspended,
        monthly_page_quota=org.monthly_page_quota,
        pages_used_this_month=org.pages_used_this_month,
        user_count=user_count,
        document_count=document_count,
        ai_tokens_total=int(tokens_total),
        ai_cost_total_usd=round(float(cost_total), 6),
        ai_qa_enabled=org.ai_qa_enabled,
        ai_summarization_enabled=org.ai_summarization_enabled,
        ai_search_answer_enabled=org.ai_search_answer_enabled,
        ai_extraction_enabled=org.ai_extraction_enabled,
    )


async def list_organizations(session: AsyncSession) -> list[AdminOrganizationResponse]:
    result = await session.execute(
        select(Organization).order_by(Organization.created_at)
    )
    orgs = result.scalars().all()
    return [await _build_org_response(session, org) for org in orgs]


async def update_organization(
    session: AsyncSession, org_id: uuid.UUID, body: AdminOrgUpdateRequest
) -> AdminOrganizationResponse:
    result = await session.execute(
        select(Organization).where(Organization.id == org_id)
    )
    org = result.scalar_one_or_none()
    if not org:
        raise ValueError("Organization not found")

    if body.is_suspended is not None:
        org.is_suspended = body.is_suspended
    if body.ai_qa_enabled is not None:
        org.ai_qa_enabled = body.ai_qa_enabled
    if body.ai_summarization_enabled is not None:
        org.ai_summarization_enabled = body.ai_summarization_enabled
    if body.ai_search_answer_enabled is not None:
        org.ai_search_answer_enabled = body.ai_search_answer_enabled
    if body.ai_extraction_enabled is not None:
        org.ai_extraction_enabled = body.ai_extraction_enabled

    await session.flush()
    return await _build_org_response(session, org)


async def list_org_documents(
    session: AsyncSession, org_id: uuid.UUID
) -> list[AdminDocumentResponse]:
    result = await session.execute(
        select(Document, User.email)
        .join(User, User.id == Document.uploaded_by)
        .where(Document.org_id == org_id)
        .order_by(Document.created_at.desc())
    )
    return [
        AdminDocumentResponse(
            id=doc.id,
            filename=doc.filename,
            mime_type=doc.mime_type,
            size_bytes=doc.size_bytes,
            status=doc.status,
            page_count=doc.page_count,
            uploaded_by_email=email,
            created_at=doc.created_at,
        )
        for doc, email in result.all()
    ]
