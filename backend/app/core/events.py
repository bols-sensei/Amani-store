"""Bus d'événements interne (découplage modules — PRINCIPE FONDATEUR #3/#4).

Usage :
    events = EventBus()

    @events.on("user.registered")
    async def handler(payload): ...

    await events.emit("user.registered", user)

Infrastructure prête ; aucun listener métier branché pour l'instant.
"""

import logging
from collections import defaultdict
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)

Listener = Callable[..., Awaitable[None]]


class EventBus:
    """Bus pub/sub minimal, asynchrone, en-process."""

    def __init__(self) -> None:
        self._listeners: dict[str, list[Listener]] = defaultdict(list)

    def on(self, event_name: str) -> Callable[[Listener], Listener]:
        """Décorateur d'enregistrement d'un listener."""

        def decorator(fn: Listener) -> Listener:
            self._listeners[event_name].append(fn)
            return fn

        return decorator

    def subscribe(self, event_name: str, fn: Listener) -> None:
        """Enregistre un listener sans décorateur."""
        self._listeners[event_name].append(fn)

    async def emit(self, event_name: str, payload: Any = None) -> None:
        """Émet un événement ; les erreurs de listener sont loguées, jamais propagées."""
        for listener in self._listeners.get(event_name, []):
            try:
                await listener(payload)
            except Exception:  # noqa: BLE001
                logger.exception(
                    "Erreur dans le listener %s pour l'événement %s",
                    getattr(listener, "__name__", "?"),
                    event_name,
                )


# Instance globale du bus.
events = EventBus()
