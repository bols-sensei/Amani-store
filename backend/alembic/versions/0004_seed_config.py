"""Seed des données de référence config-driven.

Appelle la MÊME logique que les tests (app.services.seed_service) :
source de vérité unique du seed. Idempotent (upsert par clé).
"""

from typing import Sequence, Union

import asyncio
from alembic import op
import sqlalchemy as sa

from app.services.seed_service import seed_config

revision: str = "0004_seed_config"
down_revision: Union[str, None] = "0003_permission_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    # La migration tourne sur une connexion sync ; on seede via un engine
    # async dédié créé à partir de l'URL effective de la migration.
    url = str(bind.engine.url) if hasattr(bind, "engine") else None
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def _seed() -> None:
        async with factory() as session:
            await seed_config(session)
            await session.commit()

    asyncio.run(_seed())
    asyncio.run(engine.dispose())


def downgrade() -> None:
    bind = op.get_bind()
    for table in ("role_templates", "permissions", "business_rules",
                  "exchange_rates", "currencies"):
        bind.execute(sa.text(f"DELETE FROM {table}"))
