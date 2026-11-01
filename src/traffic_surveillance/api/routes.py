from importlib.util import find_spec

from fastapi import APIRouter, Depends, Query, Request

from traffic_surveillance.api.auth import require_api_key
from traffic_surveillance.domain.models import SurveillanceEvent
from traffic_surveillance.storage.sqlite_store import SQLiteEventStore

router = APIRouter(
    prefix="/api/v1",
    tags=["surveillance"],
    dependencies=[Depends(require_api_key)],
)


@router.get("/events", response_model=list[SurveillanceEvent])
async def list_events(
    request: Request,
    camera_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[SurveillanceEvent]:
    store: SQLiteEventStore = request.app.state.event_store
    return store.list_events(camera_id=camera_id, limit=limit)


@router.post("/events", status_code=201, response_model=SurveillanceEvent)
async def create_event(event: SurveillanceEvent, request: Request) -> SurveillanceEvent:
    store: SQLiteEventStore = request.app.state.event_store
    store.add_event(event)
    return event


@router.get("/status")
async def status(request: Request) -> dict[str, object]:
    store: SQLiteEventStore = request.app.state.event_store
    processing_ready = all(find_spec(name) is not None for name in ("av", "cv2", "ultralytics"))
    return {
        "service": "traffic-and-visual-security-surveillance",
        "environment": request.app.state.settings.environment,
        "storage": "sqlite",
        "events_stored": store.count_events(),
        "video_processing_ready": processing_ready,
        "camera_fleet_connected": False,
    }
