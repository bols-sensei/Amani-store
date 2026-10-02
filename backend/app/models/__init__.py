"""Registre des modèles SQLAlchemy (importer ce module pour la metadata Base)."""

from app.models.audit_log import AuditLog
from app.models.business_rule import BusinessRule
from app.models.category import Category
from app.models.cart import Cart, CartItem
from app.models.currency import Currency
from app.models.delivery import (
    DeliveryConfirmation,
    DeliveryDispute,
    DeliveryReschedule,
    DeliveryToken,
)
from app.models.document import CourierProfile, Document
from app.models.exchange_rate import ExchangeRate
from app.models.login_attempt import LoginAttempt
from app.models.order import DeliveryZone, Order, OrderItem, OrderStatusHistory
from app.models.permission import Permission
from app.models.product import Product, ProductImage, ProductVariant
from app.models.role_template import RoleTemplate
from app.models.search_query import SearchQuery
from app.models.shipment import Shipment
from app.models.session import Session
from app.models.setting import Setting
from app.models.tenant import Tenant
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.models.user_consent import UserConsent
from app.models.user_permission import UserPermission
from app.models.verification_token import VerificationToken

__all__ = [
    "AuditLog", "BusinessRule", "Cart", "CartItem", "Category", "CourierProfile",
    "Currency", "DeliveryConfirmation", "DeliveryDispute", "DeliveryReschedule",
    "DeliveryToken", "DeliveryZone", "Document", "ExchangeRate",
    "LoginAttempt", "Order", "OrderItem", "OrderStatusHistory", "Permission",
    "Product", "ProductImage", "ProductVariant",
    "RoleTemplate", "SearchQuery", "Session", "Setting", "Shipment", "Tenant",
    "TokenBlacklist", "User", "UserConsent", "UserPermission", "VerificationToken",
]
