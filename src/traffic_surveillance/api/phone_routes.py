import re
import secrets

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from traffic_surveillance.lab.phone_stream import LatestFrameBuffer

router = APIRouter()


@router.websocket("/api/v1/phone/stream/{camera_id}")
async def phone_camera_stream(websocket: WebSocket, camera_id: str) -> None:
    """Accept authenticated binary JPEG frames from the companion Android camera app.

    Accept the WebSocket handshake before reporting application-level validation
    failures. A close sent before accept is translated by ASGI/Uvicorn into a
    generic HTTP 403, which hides whether the camera ID or API key was rejected.
    """
    await websocket.accept()

    if not re.fullmatch(r"[A-Za-z0-9_-]{1,48}", camera_id):
        await websocket.close(code=4400, reason="Invalid camera ID")
        return

    expected_key = websocket.app.state.settings.api_key or ""
    supplied_key = websocket.headers.get("x-api-key", "")
    if not expected_key or not secrets.compare_digest(expected_key, supplied_key):
        await websocket.close(code=4401, reason="Invalid API key or server key is not configured")
        return

    streams = websocket.app.state.phone_streams
    previous = streams.get(camera_id)
    if previous is not None:
        previous.close()
    source = LatestFrameBuffer()
    streams[camera_id] = source
    try:
        await websocket.send_json(
            {"status": "connected", "camera_id": camera_id, "transport": "websocket-jpeg"}
        )
        while True:
            message = await websocket.receive()
            if message.get("type") == "websocket.disconnect":
                break
            payload = message.get("bytes")
            if payload is not None:
                if not source.push_jpeg(payload):
                    await websocket.send_json(
                        {"status": "frame_rejected", "reason": "invalid_or_oversized_jpeg"}
                    )
    except WebSocketDisconnect:
        pass
    finally:
        source.close()
        if streams.get(camera_id) is source:
            streams.pop(camera_id, None)
