"""Registre des modèles SQLAlchemy (importer ce module pour la metadata Base)."""

from app.models.audit_log import AuditLog
from app.models.business_rule import BusinessRule
from app.models.currency import Currency
from app.models.exchange_rate import ExchangeRate
from app.models.login_attempt import LoginAttempt
from app.models.permission import Permission
from app.models.role_template import RoleTemplate
from app.models.session import Session
from app.models.setting import Setting
from app.models.tenant import Tenant
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.models.user_consent import UserConsent
from app.models.user_permission import UserPermission
from app.models.verification_token import VerificationToken

__all__ = [
    "AuditLog", "BusinessRule", "Currency", "ExchangeRate", "LoginAttempt",
    "Permission", "RoleTemplate", "Session", "Setting", "Tenant",
    "TokenBlacklist", "User", "UserConsent", "UserPermission", "VerificationToken",
]
