"""Application factory and operational endpoints."""

import logging

from fastapi import FastAPI

from app import __version__
from app.api.deps import SettingsDep
from app.api.routes import router
from app.config import get_settings
from app.web import router as web_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    app = FastAPI(
        title="Seat Utilization API",
        version=__version__,
        description="Track seat occupancy and report utilization against a target.",
    )
    app.include_router(router, prefix=API_PREFIX)
    app.include_router(web_router)

    @app.get("/health", tags=["ops"])
    def health(settings: SettingsDep) -> dict[str, str]:
        """Liveness probe. Cheap by design: no downstream calls."""
        return {"status": "ok", "env": settings.env, "version": __version__}

    return app


app = create_app()
