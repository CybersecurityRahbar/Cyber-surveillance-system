from fastapi import APIRouter, Depends, Query, Request

from cyber_surveillance.api.auth import require_api_key
from cyber_surveillance.api.schemas import IngestRequest, IngestResponse, RuntimeStatus
from cyber_surveillance.ingestion.normalizer import EventNormalizer

router = APIRouter(
    prefix="/api/v1",
    tags=["security-monitoring"],
    dependencies=[Depends(require_api_key)],
)
normalizer = EventNormalizer()


@router.post("/events/ingest", response_model=IngestResponse)
async def ingest_events(payload: IngestRequest, request: Request) -> IngestResponse:
    # Normalize the complete batch before writing any event, so validation errors do not
    # leave a partially ingested batch.
    normalized = [
        normalizer.normalize(
            item,
            sensor_id=payload.sensor_id,
            tenant_id=payload.tenant_id,
            source_type=payload.source_type,
        )
        for item in payload.events
    ]
    summary = await request.app.state.runtime.ingest(normalized)
    return IngestResponse(
        accepted=summary.accepted,
        duplicates=summary.duplicates,
        alerts_created=summary.alerts_created,
    )


@router.get("/events")
async def list_events(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return request.app.state.runtime.store.recent_events(limit)


@router.get("/alerts")
async def list_alerts(
    request: Request,
    limit: int = Query(default=100, ge=1, le=1000),
):
    return request.app.state.runtime.store.recent_alerts(limit)


@router.get("/status", response_model=RuntimeStatus)
async def runtime_status(request: Request) -> RuntimeStatus:
    runtime = request.app.state.runtime
    return RuntimeStatus(
        service="cyber-surveillance-api",
        environment=request.app.state.settings.environment,
        storage="in-memory",
        durable_storage=False,
        events_in_memory=runtime.store.event_count,
        alerts_in_memory=runtime.store.alert_count,
    )
