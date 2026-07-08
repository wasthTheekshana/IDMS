import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from app.models.user import UserRole


class UserResponse(BaseModel):
    id: uuid.UUID
    org_id: uuid.UUID
    email: EmailStr
    role: UserRole
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class UserCreateRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=10, max_length=128)
    role: UserRole = UserRole.MEMBER


class UserUpdateRequest(BaseModel):
    role: UserRole | None = None
    is_active: bool | None = None


class UsageResponse(BaseModel):
    plan: str
    monthly_page_quota: int
    pages_used_this_month: int
    remaining_pages: int
