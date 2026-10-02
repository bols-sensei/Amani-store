"""Schemas Pydantic v2 — authentification."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.core.security import validate_password_policy


def _normalize_phone(phone: str) -> str:
    """Normalise un numéro RDC : garde uniquement + et chiffres."""
    cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
    if not cleaned.startswith("+"):
        cleaned = "+" + cleaned.lstrip("00")
    return cleaned


class PasswordMixin(BaseModel):
    """Valide la politique de mot de passe (min 8, majuscule, minuscule, chiffre)."""

    password: str = Field(min_length=1, max_length=128)

    @field_validator("password")
    @classmethod
    def _check_policy(cls, v: str) -> str:
        errors = validate_password_policy(v)
        if errors:
            raise ValueError("; ".join(errors))
        return v


class StaffCreateRequest(PasswordMixin):
    """Création d'un staff par un vendor (tenant_id déduit du JWT, jamais du body).

    model_config extra="forbid" : tout champ inconnu (ex. tenant_id injecté
    dans le body) est rejeté en 422 — règle d'or multi-tenant.
    """

    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    permissions: list[str] = Field(default_factory=list)

    @field_validator("phone")
    @classmethod
    def _norm_phone(cls, v: str) -> str:
        return _normalize_phone(v)


class VendorRegisterRequest(PasswordMixin):
    """Inscription d'un vendeur : crée user(role=vendor) + tenant(pending)."""

    email: EmailStr
    phone: str = Field(min_length=8, max_length=20)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    shop_name: str = Field(min_length=2, max_length=150)
    billing_email: Optional[EmailStr] = None
    accept_cgu: bool

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return _normalize_phone(v)

    @field_validator("accept_cgu")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Vous devez accepter les CGU pour vous inscrire")
        return v


class CustomerRegisterRequest(PasswordMixin):
    """Inscription d'un client (compte simple, sans tenant)."""

    email: Optional[EmailStr] = None
    phone: str = Field(min_length=8, max_length=20)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    accept_cgu: bool

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return _normalize_phone(v)

    @model_validator(mode="after")
    def _email_or_phone(self) -> "CustomerRegisterRequest":
        if not self.email and not self.phone:
            raise ValueError("Email ou téléphone requis")
        return self

    @field_validator("accept_cgu")
    @classmethod
    def _must_accept(cls, v: bool) -> bool:
        if not v:
            raise ValueError("Vous devez accepter les CGU pour vous inscrire")
        return v


class LoginRequest(BaseModel):
    """Login par email OU téléphone + mot de passe."""

    identifier: str = Field(min_length=3, max_length=255)
    password: str


class TokenResponse(BaseModel):
    """Réponse login/refresh : access en body, refresh en cookie httpOnly."""

    access_token: str
    token_type: str = "bearer"
    expires_in: int
    role: str
    tenant_id: Optional[str] = None


class VerifyPhoneRequest(BaseModel):
    token: str = Field(min_length=10, max_length=128)


class ResendVerificationRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)


class ForgotPasswordRequest(BaseModel):
    identifier: str = Field(min_length=3, max_length=255)


class ResetPasswordRequest(PasswordMixin):
    token: str = Field(min_length=10, max_length=128)


class MessageResponse(BaseModel):
    message: str
    # En dev uniquement : lien généré (stub SMS), jamais exposé en prod.
    debug_link: Optional[str] = None


class SessionInfo(BaseModel):
    id: str
    device_info: Optional[dict] = None
    ip_address: Optional[str] = None
    last_active_at: datetime
    created_at: datetime

    model_config = {"from_attributes": True}
