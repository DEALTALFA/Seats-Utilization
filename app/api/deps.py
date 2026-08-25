"""FastAPI dependency wiring."""

from typing import Annotated

from fastapi import Depends

from app.config import Settings, get_settings
from app.services.utilization import SeatStore, build_store

_store: SeatStore | None = None


def get_store() -> SeatStore:
    """Process-wide store singleton. Tests override this dependency."""
    global _store
    if _store is None:
        settings = get_settings()
        _store = build_store(
            target_utilization=settings.target_utilization,
            seed_history_days=settings.seed_history_days,
        )
    return _store


SettingsDep = Annotated[Settings, Depends(get_settings)]
StoreDep = Annotated[SeatStore, Depends(get_store)]
