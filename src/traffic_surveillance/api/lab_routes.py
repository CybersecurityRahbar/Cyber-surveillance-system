import importlib.util
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from traffic_surveillance.api.auth import require_api_key
from traffic_surveillance.domain.models import EventType, Severity, SurveillanceEvent
from traffic_surveillance.lab.jobs import LabJobManager
from traffic_surveillance.lab.video_processor import VideoLabProcessor
from traffic_surveillance.vision.ultralytics_backend import UltralyticsTrackingBackend

router = APIRouter(
    prefix="/api/v1/lab",
    tags=["single-camera-lab"],
    dependencies=[Depends(require_api_key)],
)

ALLOWED_EXTENSIONS = {
    ".mp4",
    ".mov",
    ".mkv",
    ".avi",
    ".m4v",
    ".webm",
    ".mpeg",
    ".mpg",
    ".ts",
}
ALLOWED_TRACKERS = {
    "bytetrack.yaml",
    "botsort.yaml",
    "ocsort.yaml",
    "deepocsort.yaml",
    "fasttrack.yaml",
    "tracktrack.yaml",
}
CHUNK_SIZE = 1024 * 1024


class LiveLabRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2048)
    duration_seconds: int = Field(default=60, ge=10, le=1800)
    tracker: str = "bytetrack.yaml"
    confidence: float = Field(default=0.25, ge=0.05, le=0.95)
    line_position: float = Field(default=0.65, ge=0.1, le=0.9)
    max_width: int = Field(default=1280)


def _supported_environment() -> tuple[bool, list[str]]:
    missing = [
        name
        for name in ("av", "cv2", "ultralytics")
        if importlib.util.find_spec(name) is None
    ]
    return not missing, missing


def _validate_tracker(tracker: str) -> None:
    if tracker not in ALLOWED_TRACKERS:
        raise HTTPException(status_code=422, detail="Unsupported tracker configuration.")


def _source_label(source: str) -> tuple[str | int, str, str]:
    camera_match = re.fullmatch(r"server-camera:(\d{1,2})", source.strip())
    if camera_match:
        index = int(camera_match.group(1))
        if index > 9:
            raise HTTPException(status_code=422, detail="Server camera index must be 0-9.")
        return index, "server_camera", f"Server webcam {index}"

    parsed = urlsplit(source.strip())
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail="Live source must be server-camera:0 or an rtsp:// / rtsps:// URL.",
        )
    try:
        port = f":{parsed.port}" if parsed.port else ""
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid RTSP port.") from exc

    # Never return credentials, query parameters or path tokens in the job listing.
    safe_label = f"{parsed.scheme}://{parsed.hostname}{port}"
    return source.strip(), "rtsp", safe_label


def _run_job(
    runtime_state,
    *,
    job_id: str,
    source: str | int | Path,
    output_path: Path,
    tracker: str,
    confidence: float,
    line_position: float,
    max_width: int,
    live_duration_seconds: int | None,
) -> None:
    manager: LabJobManager = runtime_state.lab_jobs
    stop_event = manager.stop_event(job_id)
    manager.update(
        job_id,
        status="running",
        started_at=datetime.now(UTC).isoformat(),
        error=None,
    )
    try:
        detector = UltralyticsTrackingBackend(
            runtime_state.settings.model_path,
            tracker=tracker,
            confidence=confidence,
        )
        processor = VideoLabProcessor(detector)

        def on_crossing(item: dict) -> None:
            event = SurveillanceEvent(
                camera_id=f"lab-{job_id[:8]}",
                event_type=EventType.LINE_CROSSING,
                severity=Severity.INFO,
                occurred_at=datetime.now(UTC),
                title=f"Vehicle crossed the counting line ({item['direction']})",
                description=(
                    f"{item['class']} with track ID {item['track_id']} crossed "
                    "the laboratory counting line."
                ),
                track_id=item["track_id"],
                confidence=1.0,
                evidence={
                    "job_id": job_id,
                    "direction": item["direction"],
                    "frame_index": item["frame_index"],
                    "media_time_seconds": item["media_time_seconds"],
                    "timestamp_quality": item["timestamp_quality"],
                },
            )
            runtime_state.event_store.add_event(event)

        summary = processor.run(
            source,
            output_path,
            line_position=line_position,
            max_width=max_width,
            live_duration_seconds=live_duration_seconds,
            stop_event=stop_event,
            on_progress=lambda values: manager.update(job_id, **values),
            on_preview=lambda jpeg: manager.set_preview(job_id, jpeg),
            on_crossing=on_crossing,
        )
        final_status = "stopped" if summary["stopped_by_operator"] else "completed"
        manager.update(
            job_id,
            status=final_status,
            progress=100.0,
            result=summary,
            video_url=f"/api/v1/lab/jobs/{job_id}/video",
            finished_at=datetime.now(UTC).isoformat(),
        )
    except Exception as exc:
        # Avoid exposing an RTSP URL (which may contain credentials) in the public job record.
        manager.update(
            job_id,
            status="failed",
            error=(
                f"{type(exc).__name__}: processing failed. Check the model download, "
                "video codec, RTSP permissions and server logs."
            ),
            finished_at=datetime.now(UTC).isoformat(),
        )


@router.get("/capabilities")
async def capabilities(request: Request) -> dict:
    settings = request.app.state.settings
    processing_ready, missing = _supported_environment()
    model_path = Path(settings.model_path)
    model_alias = settings.model_path in {"yolo26n.pt", "yolo26s.pt"}
    return {
        "video_backend_ready": (
            importlib.util.find_spec("av") is not None
            and importlib.util.find_spec("cv2") is not None
        ),
        "tracking_backend_installed": importlib.util.find_spec("ultralytics") is not None,
        "processing_ready": processing_ready,
        "missing_packages": missing,
        "model": model_path.name,
        "model_file_exists": model_path.is_file(),
        "model_will_download_on_first_use": model_alias and not model_path.is_file(),
        "recommended_trackers": sorted(ALLOWED_TRACKERS),
        "max_upload_mb": settings.max_upload_mb,
        "phone_streaming": {
            "media_gateway": "MediaMTX",
            "recommended_mobile_publish": "WebRTC/WHIP",
            "python_input": "RTSP pulled from MediaMTX",
            "implemented_in_phone_app": False,
        },
    }


@router.get("/jobs")
async def list_jobs(request: Request) -> list[dict]:
    return request.app.state.lab_jobs.list()


@router.post("/jobs", status_code=202)
async def create_video_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    tracker: str = Form(default="bytetrack.yaml"),
    confidence: float = Form(default=0.25, ge=0.05, le=0.95),
    line_position: float = Form(default=0.65, ge=0.1, le=0.9),
    max_width: int = Form(default=1280),
) -> dict:
    _validate_tracker(tracker)
    if max_width not in {960, 1280, 1920}:
        raise HTTPException(status_code=422, detail="max_width must be 960, 1280 or 1920.")

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail="Unsupported video extension. Allowed: " + ", ".join(sorted(ALLOWED_EXTENSIONS)),
        )

    settings = request.app.state.settings
    lab_root = Path(settings.lab_storage_dir)
    uploads = lab_root / "uploads"
    results = lab_root / "results"
    uploads.mkdir(parents=True, exist_ok=True)
    results.mkdir(parents=True, exist_ok=True)

    input_path = uploads / f"{uuid4()}{suffix}"
    size = 0
    try:
        with input_path.open("wb") as destination:
            while chunk := await file.read(CHUNK_SIZE):
                size += len(chunk)
                if size > settings.max_upload_mb * 1024 * 1024:
                    raise HTTPException(
                        status_code=413,
                        detail=f"Video exceeds the {settings.max_upload_mb} MB upload limit.",
                    )
                destination.write(chunk)
    except Exception:
        input_path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()

    if size == 0:
        input_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="The uploaded video is empty.")

    manager: LabJobManager = request.app.state.lab_jobs
    job_id = manager.create(
        source_type="uploaded_video",
        source_label="Local video upload",
        filename=Path(file.filename or "video").name,
        options={
            "tracker": tracker,
            "confidence": confidence,
            "line_position": line_position,
            "max_width": max_width,
            "size_bytes": size,
        },
    )
    output_path = results / f"{job_id}.mp4"
    background_tasks.add_task(
        _run_job,
        request.app.state,
        job_id=job_id,
        source=input_path,
        output_path=output_path,
        tracker=tracker,
        confidence=confidence,
        line_position=line_position,
        max_width=max_width,
        live_duration_seconds=None,
    )
    return manager.get(job_id)


@router.post("/live-jobs", status_code=202)
async def create_live_job(
    payload: LiveLabRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    _validate_tracker(payload.tracker)
    if payload.max_width not in {960, 1280, 1920}:
        raise HTTPException(status_code=422, detail="max_width must be 960, 1280 or 1920.")
    source, source_type, source_label = _source_label(payload.source)
    manager: LabJobManager = request.app.state.lab_jobs
    job_id = manager.create(
        source_type=source_type,
        source_label=source_label,
        filename="Live single-camera session",
        options={
            "tracker": payload.tracker,
            "confidence": payload.confidence,
            "line_position": payload.line_position,
            "max_width": payload.max_width,
            "duration_seconds": payload.duration_seconds,
        },
    )
    output_path = Path(request.app.state.settings.lab_storage_dir) / "results" / f"{job_id}.mp4"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    background_tasks.add_task(
        _run_job,
        request.app.state,
        job_id=job_id,
        source=source,
        output_path=output_path,
        tracker=payload.tracker,
        confidence=payload.confidence,
        line_position=payload.line_position,
        max_width=payload.max_width,
        live_duration_seconds=payload.duration_seconds,
    )
    return manager.get(job_id)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request) -> dict:
    job = request.app.state.lab_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Laboratory job not found.")
    return job


@router.get("/jobs/{job_id}/preview.jpg")
async def get_job_preview(job_id: str, request: Request) -> Response:
    if request.app.state.lab_jobs.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Laboratory job not found.")
    preview = request.app.state.lab_jobs.get_preview(job_id)
    if preview is None:
        return Response(status_code=204)
    version, jpeg = preview
    return Response(
        content=jpeg,
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "X-Preview-Version": str(version)},
    )


@router.get("/jobs/{job_id}/video")
async def get_job_video(job_id: str, request: Request) -> FileResponse:
    job = request.app.state.lab_jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Laboratory job not found.")
    if job["status"] not in {"completed", "stopped"}:
        raise HTTPException(status_code=409, detail="The processed video is not ready.")
    path = Path(request.app.state.settings.lab_storage_dir) / "results" / f"{job_id}.mp4"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Processed video file not found.")
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"traffic-lab-{job_id[:8]}.mp4",
    )


@router.post("/jobs/{job_id}/stop")
async def stop_job(job_id: str, request: Request) -> dict:
    manager = request.app.state.lab_jobs
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Laboratory job not found.")
    if not manager.request_stop(job_id):
        raise HTTPException(status_code=409, detail="This job is not currently running.")
    return {"job_id": job_id, "stop_requested": True}
