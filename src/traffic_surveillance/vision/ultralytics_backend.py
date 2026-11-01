from pathlib import Path

from traffic_surveillance.domain.models import BoundingBox, Detection


class UltralyticsTrackingBackend:
    """Optional YOLO detector/tracker adapter; create one instance per camera stream.

    Ultralytics is optional because model/runtime footprint and licensing must be
    evaluated for the deployment environment before distribution.
    """

    def __init__(
        self,
        weights: str | Path,
        *,
        tracker: str = "bytetrack.yaml",
        confidence: float = 0.25,
        device: str | None = None,
    ) -> None:
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is not installed. Install the optional 'vision' extra."
            ) from exc

        path = Path(weights)
        if not path.is_file():
            raise FileNotFoundError(f"Model weights not found: {path}")
        self._model = YOLO(str(path))
        self._tracker = tracker
        self._confidence = confidence
        self._device = device

    def detect_and_track(self, frame) -> list[Detection]:
        results = self._model.track(
            source=frame,
            persist=True,
            tracker=self._tracker,
            conf=self._confidence,
            device=self._device,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        if result.boxes is None:
            return []

        detections: list[Detection] = []
        for box in result.boxes:
            xyxy = box.xyxy[0].detach().cpu().tolist()
            class_id = int(box.cls[0].item())
            track_id = int(box.id[0].item()) if box.id is not None else None
            detections.append(
                Detection(
                    label=str(self._model.names[class_id]),
                    confidence=float(box.conf[0].item()),
                    box=BoundingBox(
                        x1=float(xyxy[0]),
                        y1=float(xyxy[1]),
                        x2=float(xyxy[2]),
                        y2=float(xyxy[3]),
                    ),
                    track_id=track_id,
                )
            )
        return detections
