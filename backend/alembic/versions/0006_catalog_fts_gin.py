"""Index GIN full-text PostgreSQL pour la recherche produits.

Colonne calculée `search_vector` (tsvector 'french' sur nom + description) +
index GIN. Trigger pour maintenir la colonne à jour. Sur SQLite (tests) la
migration est un no-op — le fallback ILIKE du CRUD prend le relais.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0006_catalog_fts_gin"
down_revision: Union[str, None] = "0005_catalog_tables"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite/dev sans PG → fallback ILIKE déjà en place

    op.execute("""
        ALTER TABLE products
        ADD COLUMN IF NOT EXISTS search_vector tsvector
        GENERATED ALWAYS AS (
            to_tsvector('french',
                coalesce(name, '') || ' ' ||
                coalesce(short_description, '') || ' ' ||
                coalesce(description, '')
            )
        ) STORED;
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_products_search_vector
        ON products USING GIN (search_vector);
    """)
    # Recherche plus rapide et précise que l'expression inline (sert aussi de
    # support à la requête to_tsvector(...) @@ ... de product_service.fts_search).
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_products_fts_expr
        ON products USING GIN (
            to_tsvector('french',
                coalesce(name, '') || ' ' || coalesce(description, ''))
        );
    """)


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS ix_products_fts_expr;")
    op.execute("DROP INDEX IF EXISTS ix_products_search_vector;")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS search_vector;")
