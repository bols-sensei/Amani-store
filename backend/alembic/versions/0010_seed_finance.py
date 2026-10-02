"""Seed finance data (prompt 5): plans, global commission rule, billing rules.

Delegates to app.services.seed_finance (idempotent). Runs inside the
migration transaction on PostgreSQL; on SQLite/tests the same function is
called from the seed pipeline.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_seed_finance"
down_revision: Union[str, None] = "0009_finance_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from app.db.base import new_uuid, utcnow
    from app.services.seed_finance import BILLING_RULES, PLANS

    bind = op.get_bind()
    now = utcnow()

    for plan in PLANS:
        exists = bind.execute(
            __import__("sqlalchemy").text("SELECT 1 FROM plans WHERE key = :k"),
            {"k": plan["key"]},
        ).first()
        if exists is None:
            bind.execute(
                __import__("sqlalchemy").text(
                    "INSERT INTO plans (id, key, name, price_usd_monthly,"
                    " commission_rate, commission_min_usd, limits, features,"
                    " is_active, display_order, created_at, updated_at)"
                    " VALUES (:id, :key, :name, :price, :rate, :min,"
                    " :limits, :features, 1, :ord, :ts, :ts)"
                ),
                {
                    "id": new_uuid(), "key": plan["key"], "name": plan["name"],
                    "price": plan["price_usd_monthly"],
                    "rate": plan["commission_rate"],
                    "min": plan["commission_min_usd"],
                    "limits": __import__("json").dumps(plan["limits"]),
                    "features": __import__("json").dumps(plan["features"]),
                    "ord": plan["display_order"], "ts": now,
                },
            )

    sa = __import__("sqlalchemy")
    has_global = bind.execute(
        sa.text("SELECT 1 FROM commission_rules WHERE tenant_id IS NULL"
                " AND category_id IS NULL AND applies_to = 'products'")
    ).first()
    if has_global is None:
        bind.execute(
            sa.text(
                "INSERT INTO commission_rules (id, tenant_id, category_id,"
                " applies_to, rate, min_amount_usd, priority, is_active, notes,"
                " created_at, updated_at) VALUES (:id, NULL, NULL,"
                " 'products', 0.05, 0.50, 1, 1,"
                " 'Règle de commission globale par défaut (tous vendeurs)',"
                " :ts, :ts)"
            ),
            {"id": new_uuid(), "ts": now},
        )

    for rule in BILLING_RULES:
        exists = bind.execute(
            sa.text("SELECT 1 FROM business_rules WHERE key = :k"),
            {"k": rule["key"]},
        ).first()
        if exists is None:
            value = rule["value"]
            rtype = ("json" if value.startswith("[")
                     else "boolean" if value in ("true", "false")
                     else "number")
            bind.execute(
                sa.text(
                    "INSERT INTO business_rules (id, key, value, type, category,"
                    " description, editable_by, created_at, updated_at)"
                    " VALUES (:id, :k, :v, :t, 'billing',"
                    " 'Règle de facturation SaaS', 'superadmin', :ts, :ts)"
                ),
                {"id": new_uuid(), "k": rule["key"], "v": value, "t": rtype, "ts": now},
            )


def downgrade() -> None:
    sa = __import__("sqlalchemy")
    bind = op.get_bind()
    keys = [r["key"] for r in _billing_keys()]
    bind.execute(
        sa.text("DELETE FROM business_rules WHERE key = ANY(:keys)"),
        {"keys": keys},
    )
    bind.execute(sa.text(
        "DELETE FROM commission_rules WHERE tenant_id IS NULL"
        " AND category_id IS NULL AND applies_to = 'products'"))
    bind.execute(sa.text("DELETE FROM plans WHERE key IN ('free','pro','business')"))


def _billing_keys():
    from app.services.seed_finance import BILLING_RULES
    return BILLING_RULES
