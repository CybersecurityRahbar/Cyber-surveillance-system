import asyncio
import importlib.util
import re
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.responses import FileResponse, Response, StreamingResponse
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
    "models/trackers/cyber_tracktrack_reid.yaml",
}
CHUNK_SIZE = 1024 * 1024


class LiveLabRequest(BaseModel):
    source: str = Field(min_length=1, max_length=2048)
    duration_seconds: int = Field(default=0, ge=0, le=1800)
    tracker: str = "bytetrack.yaml"
    confidence: float = Field(default=0.25, ge=0.05, le=0.95)
    line_position: float = Field(default=0.65, ge=0.1, le=0.9)
    max_width: int = Field(default=640)
    show_hud: bool = False


def _supported_environment() -> tuple[bool, list[str]]:
    missing = [
        name
        for name in ("av", "cv2", "ultralytics")
        if importlib.util.find_spec(name) is None
    ]
    return not missing, missing


def _compute_runtime_info() -> dict:
    """Expose the actual inference device so CPU-only live sessions are not mistaken for real time."""
    try:
        import torch
    except ImportError:
        return {
            "device": "unknown",
            "cuda_available": False,
            "gpu_name": None,
            "torch_version": None,
        }
    cuda_available = bool(torch.cuda.is_available())
    gpu_name = None
    if cuda_available:
        try:
            gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            gpu_name = "CUDA device"
    return {
        "device": "cuda:0" if cuda_available else "cpu",
        "cuda_available": cuda_available,
        "gpu_name": gpu_name,
        "torch_version": str(torch.__version__),
        "cuda_version": getattr(torch.version, "cuda", None),
    }




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

    phone_match = re.fullmatch(r"phone-camera:([A-Za-z0-9_-]{1,48})", source.strip())
    if phone_match:
        camera_id = phone_match.group(1)
        return source.strip(), "phone_camera", f"Phone camera {camera_id}"

    parsed = urlsplit(source.strip())
    if parsed.scheme not in {"rtsp", "rtsps"} or not parsed.hostname:
        raise HTTPException(
            status_code=422,
            detail=(
                "Live source must be phone-camera:ID, server-camera:0, "
                "or an rtsp:// / rtsps:// URL."
            ),
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
    show_hud: bool,
    realtime_mode: bool = False,
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
            inference_size=384 if realtime_mode else 512,
            max_det=30 if realtime_mode else 60,
            vehicle_model_path=runtime_state.settings.vehicle_model_path,
            enable_pretrained_attributes=(
                runtime_state.settings.enable_pretrained_vehicle_attributes
            ),
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
            show_hud=show_hud,
            record_output=not realtime_mode,
            realtime_mode=realtime_mode,
            on_progress=lambda values: manager.update(job_id, **values),
            on_preview=lambda jpeg: manager.set_preview(job_id, jpeg),
            on_crossing=on_crossing,
        )
        final_status = "stopped" if summary["stopped_by_operator"] else "completed"
        finished_at = datetime.now(UTC).isoformat()
        manager.update(
            job_id,
            status=final_status,
            progress=100.0,
            result=summary,
            video_url=f"/api/v1/lab/jobs/{job_id}/video",
            finished_at=finished_at,
        )
        record = manager.get(job_id) or {}
        runtime_state.event_store.save_lab_report(
            session_id=job_id,
            source_type=record.get("source_type", "unknown"),
            source_label=record.get("source_label", "Unknown source"),
            filename=record.get("filename", "unknown"),
            status=final_status,
            started_at=record.get("started_at"),
            finished_at=finished_at,
            summary=summary,
            tracks=summary.get("tracks", []),
        )
    except Exception as exc:
        # Avoid exposing an RTSP URL (which may contain credentials) in the public job record.
        finished_at = datetime.now(UTC).isoformat()
        message = (
            f"{type(exc).__name__}: processing failed. Check the model download, "
            "video codec, RTSP permissions and server logs."
        )
        manager.update(
            job_id,
            status="failed",
            error=message,
            finished_at=finished_at,
        )
        record = manager.get(job_id) or {}
        runtime_state.event_store.save_lab_report(
            session_id=job_id,
            source_type=record.get("source_type", "unknown"),
            source_label=record.get("source_label", "Unknown source"),
            filename=record.get("filename", "unknown"),
            status="failed",
            started_at=record.get("started_at"),
            finished_at=finished_at,
            summary={"error": message},
            tracks=[],
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
        "compute": _compute_runtime_info(),
        "realtime_profile": {
            "model": "YOLO26n",
            "input_width": 640,
            "inference_size": 384,
            "tracker": "ByteTrack",
            "live_video_recording": False,
            "continuous_until_stopped": True,
        },
        "model": model_path.name,
        "model_file_exists": model_path.is_file(),
        "model_will_download_on_first_use": model_alias and not model_path.is_file(),
        "recommended_trackers": sorted(ALLOWED_TRACKERS),
        "max_upload_mb": settings.max_upload_mb,
        "preview_transport": "mjpeg_stream",
        "vehicle_colour": "estimated_from_track_frames",
        "vehicle_make_model_configured": bool(
            (settings.vehicle_model_path and Path(settings.vehicle_model_path).is_file())
            or settings.enable_pretrained_vehicle_attributes
        ),
        "make_model_recognition": (
            "custom_classifier_ready"
            if settings.vehicle_model_path and Path(settings.vehicle_model_path).is_file()
            else "pretrained_candidate_model_enabled"
            if settings.enable_pretrained_vehicle_attributes
            else "not_configured_requires_fine_grained_vehicle_classifier"
        ),
        "phone_streaming": {
            "transport": "authenticated_websocket_jpeg",
            "endpoint": "/api/v1/phone/stream/{camera_id}",
            "source_format": "phone-camera:{camera_id}",
            "active_streams": len(request.app.state.phone_streams),
            "implemented_in_phone_app": True,
            "app_status": "prototype_foreground_activity_required",
        },
        "pretrained_vehicle_attributes_enabled": (
            settings.enable_pretrained_vehicle_attributes
        ),
        "learned_vehicle_models": {
            "colour": "piotreksl/vehicle-color-recognition",
            "make_model": "twincar-group2/twincar-classifier",
            "loaded_after_primary_video_pass": True,
        },
    }


@router.get("/jobs")
async def list_jobs(request: Request) -> list[dict]:
    return request.app.state.lab_jobs.list()


@router.post("/jobs", status_code=202)
async def create_video_job(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),  # noqa: B008
    tracker: str = Form(default="models/trackers/cyber_tracktrack_reid.yaml"),
    confidence: float = Form(default=0.25, ge=0.05, le=0.95),
    line_position: float = Form(default=0.65, ge=0.1, le=0.9),
    max_width: int = Form(default=960),
    show_hud: bool = Form(default=False),
) -> dict:
    _validate_tracker(tracker)
    if max_width not in {640, 800, 960, 1280, 1920}:
        raise HTTPException(
            status_code=422,
            detail="max_width must be 640, 800, 960, 1280 or 1920.",
        )

    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=(
                "Unsupported video extension. Allowed: "
                + ", ".join(sorted(ALLOWED_EXTENSIONS))
            ),
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
            "show_hud": show_hud,
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
        show_hud=show_hud,
    )
    return manager.get(job_id)


@router.post("/live-jobs", status_code=202)
async def create_live_job(
    payload: LiveLabRequest,
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict:
    _validate_tracker(payload.tracker)
    if payload.max_width not in {640, 800, 960, 1280, 1920}:
        raise HTTPException(
            status_code=422,
            detail="max_width must be 640, 800, 960, 1280 or 1920.",
        )
    source, source_type, source_label = _source_label(payload.source)
    if source_type == "phone_camera":
        camera_id = source.split(":", 1)[1]
        stream = request.app.state.phone_streams.get(camera_id)
        if stream is None or stream.closed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Phone camera is not connected. Open the companion app and start "
                    "its secure WebSocket stream first."
                ),
            )
        source = stream
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
            "duration_seconds": payload.duration_seconds or None,
            "realtime_mode": True,
            "record_output": False,
            "show_hud": payload.show_hud,
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
        live_duration_seconds=payload.duration_seconds or None,
        show_hud=payload.show_hud,
        realtime_mode=True,
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




@router.get("/jobs/{job_id}/preview.mjpg")
async def get_job_preview_stream(job_id: str, request: Request) -> StreamingResponse:
    manager = request.app.state.lab_jobs
    if manager.get(job_id) is None:
        raise HTTPException(status_code=404, detail="Laboratory job not found.")

    async def frame_generator():
        version = 0
        while True:
            if await request.is_disconnected():
                break
            preview = await asyncio.to_thread(
                manager.wait_for_preview, job_id, version, 12.0
            )
            if preview is None:
                job = manager.get(job_id)
                if job is None or job.get("status") in {"completed", "stopped", "failed"}:
                    break
                continue
            version, jpeg = preview
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg)}\r\n\r\n".encode("ascii")
                + jpeg
                + b"\r\n"
            )

    return StreamingResponse(
        frame_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.get("/reports")
async def list_lab_reports(request: Request, limit: int = 50) -> list[dict]:
    return request.app.state.event_store.list_lab_reports(limit=limit)


@router.get("/reports/{session_id}")
async def get_lab_report(session_id: str, request: Request) -> dict:
    report = request.app.state.event_store.get_lab_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratory report not found.")
    return report


@router.get("/reports/{session_id}/tracks")
async def get_lab_track_reports(session_id: str, request: Request) -> list[dict]:
    report = request.app.state.event_store.get_lab_report(session_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Laboratory report not found.")
    return request.app.state.event_store.get_lab_tracks(session_id)

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
