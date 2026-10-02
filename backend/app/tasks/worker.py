"""ARQ worker — stub. Les tâches planifiées (auto-cancel commandes, facturation
mensuelle, snapshots de taux) seront branchées ici via le bus d'événements."""


async def startup(ctx) -> None:
    """Init worker ARQ (placeholder)."""


async def shutdown(ctx) -> None:
    """Cleanup worker ARQ (placeholder)."""


class WorkerSettings:
    """Configuration ARQ (Redis). Vide pour l'instant — infrastructure prête."""

    functions: list = []
    on_startup = startup
    on_shutdown = shutdown
