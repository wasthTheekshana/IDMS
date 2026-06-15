from pydantic import BaseModel, EmailStr, field_validator


class RegisterRequest(BaseModel):
    org_name: str
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 10:
            raise ValueError("Password must be at least 10 characters")
        return v

    @field_validator("org_name")
    @classmethod
    def org_name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("org_name cannot be blank")
        return v.strip()


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str
