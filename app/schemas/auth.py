import uuid

from pydantic import BaseModel, EmailStr, Field


class RegisterIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    organisation: str = Field(min_length=1, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class MeOut(BaseModel):
    id: uuid.UUID
    name: str
    organisation: str
    email: EmailStr
    credits: int
    emailVerified: bool = False


# ── OTP ────────────────────────────────────────────────────────────────────────

class VerifyEmailIn(BaseModel):
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class ForgotPasswordIn(BaseModel):
    email: EmailStr


class ResetPasswordIn(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")
    newPassword: str = Field(min_length=8, max_length=200)
