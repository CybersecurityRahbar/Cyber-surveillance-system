from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from cyber_surveillance.api.routes import router
from cyber_surveillance.core.config import Settings, get_settings
from cyber_surveillance.services.runtime import MonitorRuntime


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        # Initialize long-lived database, broker and connector resources here later.
        yield

    application = FastAPI(
        title="Cyber Surveillance API",
        description=(
            "Defensive security event ingestion, normalization and detection API. "
            "The current development store is in-memory and non-durable."
        ),
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = config
    application.state.runtime = MonitorRuntime(
        max_events=config.max_memory_events,
        threshold=config.auth_failure_threshold,
        window_seconds=config.auth_failure_window_seconds,
    )
    application.include_router(router)

    @application.get("/healthz", tags=["health"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "cyber-surveillance-api",
            "environment": config.environment,
        }

    return application


app = create_app()
