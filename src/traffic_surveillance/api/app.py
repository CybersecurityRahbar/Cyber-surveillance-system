from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from traffic_surveillance.api.lab_routes import router as lab_router
from traffic_surveillance.api.phone_routes import router as phone_router
from traffic_surveillance.api.routes import router
from traffic_surveillance.core.config import Settings, get_settings
from traffic_surveillance.lab.jobs import LabJobManager
from traffic_surveillance.storage.sqlite_store import SQLiteEventStore


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or get_settings()
    application = FastAPI(
        title="Traffic & Visual Security Surveillance",
        description=(
            "Central Python platform for intelligent traffic and "
            "camera-based visual-security analytics. Includes a single-camera laboratory."
        ),
        version="0.3.0",
    )
    application.state.settings = config
    application.state.event_store = SQLiteEventStore(config.database)
    application.state.lab_jobs = LabJobManager()
    application.state.phone_streams = {}
    application.include_router(router)
    application.include_router(lab_router)
    application.include_router(phone_router)

    web_dir = Path(__file__).resolve().parents[1] / "web"
    application.mount(
        "/lab-assets",
        StaticFiles(directory=str(web_dir)),
        name="lab-assets",
    )

    @application.get("/lab", include_in_schema=False)
    async def lab_home() -> FileResponse:
        return FileResponse(web_dir / "lab.html", media_type="text/html")

    @application.get("/healthz", tags=["health"])
    async def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": "traffic-and-visual-security-surveillance",
        }

    return application


app = create_app()
