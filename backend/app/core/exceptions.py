"""Exceptions métier de l'application.

Traduites en réponses HTTP par des handlers globaux dans main.py.
"""

from typing import Any, Optional


class AppError(Exception):
    """Erreur applicative de base."""

    status_code: int = 400
    code: str = "app_error"

    def __init__(self, message: str, details: Optional[Any] = None) -> None:
        self.message = message
        self.details = details
        super().__init__(message)


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"


class ConflictError(AppError):
    status_code = 409
    code = "conflict"


class ValidationError_(AppError):
    """Erreur de validation métier (hors validation Pydantic automatique)."""

    status_code = 422
    code = "validation_error"


class AuthenticationError(AppError):
    status_code = 401
    code = "authentication_error"


class PermissionDeniedError(AppError):
    status_code = 403
    code = "permission_denied"


class TenantInactiveError(AppError):
    """Le tenant n'est pas actif (pending/suspended/rejected)."""

    status_code = 403
    code = "tenant_not_active"


class RateLimitExceededError(AppError):
    status_code = 429
    code = "rate_limit_exceeded"
