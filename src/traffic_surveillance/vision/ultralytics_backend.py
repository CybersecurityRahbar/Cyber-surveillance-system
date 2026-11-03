from pathlib import Path

from traffic_surveillance.domain.models import BoundingBox, Detection


class UltralyticsTrackingBackend:
    """Optional YOLO detector/tracker adapter; use one instance per video stream."""

    DOWNLOADABLE_MODELS = {"yolo26n.pt", "yolo26s.pt"}

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
                "Ultralytics is not installed. Install with: "
                "pip install -e '.[video,vision]'"
            ) from exc

        path = Path(weights)
        model_source = str(path)
        if not path.is_file() and model_source not in self.DOWNLOADABLE_MODELS:
            raise FileNotFoundError(
                f"Model weights not found: {path}. Use yolo26n.pt or provide a local model path."
            )

        self._model = YOLO(model_source)
        self._tracker = tracker
        self._confidence = confidence
        if device is None:
            try:
                import torch

                self._device = "0" if torch.cuda.is_available() else "cpu"
                self._half = bool(torch.cuda.is_available())
            except ImportError:
                self._device = "cpu"
                self._half = False
        else:
            self._device = device
            self._half = str(device).lower() not in {"cpu"}

    def detect_and_track(self, frame) -> list[Detection]:
        results = self._model.track(
            source=frame,
            persist=True,
            tracker=self._tracker,
            conf=self._confidence,
            device=self._device,
            imgsz=640,
            max_det=100,
            half=self._half,
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
