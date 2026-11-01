from fastapi import FastAPI

from traffic_surveillance.api.routes import router
from traffic_surveillance.core.config import Settings, get_settings
from traffic_surveillance.storage.sqlite_store import SQLiteEventStore


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    application = FastAPI(
        title="Traffic & Visual Security Surveillance",
        description=(
            "Central API for intelligent traffic and camera-based visual-security events. "
            "Live camera orchestration is not enabled in this initial slice."
        ),
        version="0.2.0",
    )
    application.state.settings = config
    application.state.event_store = SQLiteEventStore(config.database)
    application.include_router(router)

    @application.get("/healthz", tags=["health"])
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "traffic-and-visual-security-surveillance"}

    return application


app = create_app()
