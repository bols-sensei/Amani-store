"""Données de référence du seed (config-driven).

Modifier une valeur ici n'affecte PAS le comportement runtime : ces dicts
sont insérés en base au premier seed ; ensuite la BASE est la source de
vérité (le superadmin peut tout changer via SQL/API sans redéploiement).
"""

CURRENCIES: list[dict] = [
    {
        "code": "USD", "name": "Dollar américain", "symbol": "$",
        "symbol_position": "before", "decimal_places": 2,
        "thousands_sep": ",", "decimal_sep": ".", "is_active": True, "display_order": 1,
    },
    {
        "code": "CDF", "name": "Franc congolais", "symbol": "FC",
        "symbol_position": "after", "decimal_places": 0,
        "thousands_sep": " ", "decimal_sep": ",", "is_active": True, "display_order": 2,
    },
]

EXCHANGE_RATES: list[dict] = [
    {"from_currency": "USD", "to_currency": "CDF", "rate": 2500, "source": "manual"},
]

BUSINESS_RULES: list[dict] = [
    {"key": "order.auto_cancel_hours", "value": "48", "type": "number",
     "category": "orders", "description": "Annulation auto si non confirmée (heures)",
     "editable_by": "superadmin"},
    {"key": "order.max_reschedule_count", "value": "2", "type": "number",
     "category": "orders", "description": "Report max d'une livraison",
     "editable_by": "superadmin"},
    {"key": "order.reschedule_fee_after_max", "value": "500", "type": "number",
     "category": "orders", "description": "Frais après dépassement (monnaie tenant)",
     "editable_by": "superadmin"},
    {"key": "commission.calculation_base", "value": "products_only", "type": "string",
     "category": "commissions", "description": "Base de calcul commission (hors livraison)",
     "editable_by": "system"},
    {"key": "tenant.validation_required", "value": "true", "type": "boolean",
     "category": "tenants", "description": "Validation superadmin requise à l'inscription",
     "editable_by": "superadmin"},
    {"key": "notification.max_promo_per_day", "value": "3", "type": "number",
     "category": "notifications", "description": "Promos max/jour/client",
     "editable_by": "superadmin"},
    {"key": "notification.quiet_hours_start", "value": "22", "type": "number",
     "category": "notifications", "description": "Début plage silencieuse (h locale)",
     "editable_by": "superadmin"},
    {"key": "notification.quiet_hours_end", "value": "7", "type": "number",
     "category": "notifications", "description": "Fin plage silencieuse (h locale)",
     "editable_by": "superadmin"},
    {"key": "password.min_length", "value": "8", "type": "number",
     "category": "security", "description": "Longueur min mot de passe",
     "editable_by": "superadmin"},
    {"key": "login.max_attempts", "value": "5", "type": "number",
     "category": "security", "description": "Tentatives login avant lockout",
     "editable_by": "superadmin"},
    {"key": "login.lockout_minutes", "value": "15", "type": "number",
     "category": "security", "description": "Durée lockout (minutes)",
     "editable_by": "superadmin"},
    {"key": "rate_limit.public_per_minute", "value": "60", "type": "number",
     "category": "security", "description": "Endpoints publics req/min/IP",
     "editable_by": "superadmin"},
    {"key": "rate_limit.login_per_minute", "value": "5", "type": "number",
     "category": "security", "description": "Login+register req/min/IP",
     "editable_by": "superadmin"},
    {"key": "rate_limit.api_per_minute", "value": "300", "type": "number",
     "category": "security", "description": "API standard req/min",
     "editable_by": "superadmin"},
]

PERMISSIONS: list[dict] = [
    {"key": "products.view", "category": "products", "plan_min": "free"},
    {"key": "products.create", "category": "products", "plan_min": "free"},
    {"key": "products.edit", "category": "products", "plan_min": "free"},
    {"key": "products.delete", "category": "products", "plan_min": "free"},
    {"key": "products.stock", "category": "products", "plan_min": "free"},
    {"key": "orders.view", "category": "orders", "plan_min": "free"},
    {"key": "orders.confirm", "category": "orders", "plan_min": "free"},
    {"key": "orders.cancel", "category": "orders", "plan_min": "free"},
    {"key": "orders.ship", "category": "orders", "plan_min": "free"},
    {"key": "shipments.view", "category": "shipments", "plan_min": "free"},
    {"key": "shipments.manage", "category": "shipments", "plan_min": "pro"},
    {"key": "couriers.manage", "category": "shipments", "plan_min": "pro"},
    {"key": "customers.view", "category": "customers", "plan_min": "free"},
    {"key": "customers.manage", "category": "customers", "plan_min": "pro"},
    {"key": "segments.view", "category": "marketing", "plan_min": "pro"},
    {"key": "segments.manage", "category": "marketing", "plan_min": "pro"},
    {"key": "campaigns.view", "category": "marketing", "plan_min": "pro"},
    {"key": "campaigns.manage", "category": "marketing", "plan_min": "business"},
    {"key": "finances.view", "category": "finances", "plan_min": "free"},
    {"key": "finances.invoices", "category": "finances", "plan_min": "pro"},
    {"key": "finances.export", "category": "finances", "plan_min": "business"},
    {"key": "analytics.view", "category": "analytics", "plan_min": "free"},
    {"key": "analytics.export", "category": "analytics", "plan_min": "pro"},
    {"key": "settings.view", "category": "settings", "plan_min": "free"},
    {"key": "settings.manage", "category": "settings", "plan_min": "business"},
    {"key": "staff.manage", "category": "staff", "plan_min": "pro"},
]

ROLE_TEMPLATES: list[dict] = [
    {"key": "manager", "name": "Manager", "is_system": True,
     "permissions": ["products.*", "orders.*", "shipments.*", "customers.*",
                     "segments.*", "campaigns.*", "finances.*", "analytics.*",
                     "settings.view"]},
    {"key": "stock_manager", "name": "Gestionnaire stock", "is_system": True,
     "permissions": ["products.*"]},
    {"key": "order_manager", "name": "Gestionnaire commandes", "is_system": True,
     "permissions": ["orders.*", "shipments.*"]},
    {"key": "accountant", "name": "Comptable", "is_system": True,
     "permissions": ["finances.view", "finances.invoices", "analytics.view"]},
    {"key": "marketing", "name": "Marketing", "is_system": True,
     "permissions": ["campaigns.*", "segments.*", "customers.view"]},
    {"key": "support", "name": "Support", "is_system": True,
     "permissions": ["customers.view", "orders.view"]},
]
