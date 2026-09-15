import uuid

from fastapi import APIRouter, HTTPException, status

from app.core.deps import AdminSession, CurrentPlatformAdminDep
from app.repositories.platform_admin import PlatformAdminRepository
from app.schemas.platform_admin import (
    AdminDocumentResponse,
    AdminOrganizationResponse,
    AdminOrgUpdateRequest,
    PlatformAdminProfile,
)
from app.services import platform_admin as admin_service

router = APIRouter(prefix="/platform-admin", tags=["platform-admin"])


@router.get("/me", response_model=PlatformAdminProfile)
async def get_me(
    admin: CurrentPlatformAdminDep, session: AdminSession
) -> PlatformAdminProfile:
    record = await PlatformAdminRepository(session).get_by_id(admin.admin_id)
    if not record:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Admin not found"
        )
    return PlatformAdminProfile(id=record.id, email=record.email)


@router.get("/organizations", response_model=list[AdminOrganizationResponse])
async def list_organizations(
    admin: CurrentPlatformAdminDep, session: AdminSession
) -> list[AdminOrganizationResponse]:
    return await admin_service.list_organizations(session)


@router.patch("/organizations/{org_id}", response_model=AdminOrganizationResponse)
async def update_organization(
    org_id: uuid.UUID,
    body: AdminOrgUpdateRequest,
    admin: CurrentPlatformAdminDep,
    session: AdminSession,
) -> AdminOrganizationResponse:
    try:
        return await admin_service.update_organization(session, org_id, body)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@router.get(
    "/organizations/{org_id}/documents", response_model=list[AdminDocumentResponse]
)
async def list_org_documents(
    org_id: uuid.UUID,
    admin: CurrentPlatformAdminDep,
    session: AdminSession,
) -> list[AdminDocumentResponse]:
    return await admin_service.list_org_documents(session, org_id)
