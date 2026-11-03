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
        vehicle_model_path: str | Path | None = None,
        enable_pretrained_attributes: bool = False,
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
        self._vehicle_classifier = None
        self._pretrained_attributes_enabled = enable_pretrained_attributes
        self._pretrained_attributes = None
        self._pretrained_attributes_error = None
        if vehicle_model_path:
            classifier_path = Path(vehicle_model_path)
            if not classifier_path.is_file():
                raise FileNotFoundError(
                    f"Vehicle make/model classifier not found: {classifier_path}"
                )
            self._vehicle_classifier = YOLO(str(classifier_path))
            if getattr(self._vehicle_classifier, "task", None) != "classify":
                raise ValueError(
                    "Vehicle model weights must be an Ultralytics classification model."
                )
        self._tracker = tracker
        self._confidence = confidence
        self._imgsz = 512
        self._max_det = 60
        self._classes = [0, 1, 2, 3, 5, 7]
        if device is None:
            try:
                import torch

                self._device = "0" if torch.cuda.is_available() else "cpu"
                self._half = bool(torch.cuda.is_available())
                if torch.cuda.is_available():
                    torch.backends.cudnn.benchmark = True
                    torch.set_float32_matmul_precision("high")
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
            imgsz=self._imgsz,
            max_det=self._max_det,
            classes=self._classes,
            half=self._half,
            verbose=False,
        )
        if not results:
            return []

        result = results[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return []

        # Transfer the complete result tensor once. Per-box .cpu()/.item() calls
        # force repeated GPU synchronizations and become expensive in dense scenes.
        data = boxes.data.detach().cpu().numpy()
        is_track = bool(boxes.is_track)
        detections: list[Detection] = []
        for row in data:
            if is_track:
                xyxy = row[:4]
                track_id = int(row[4])
                confidence = float(row[5])
                class_id = int(row[6])
            else:
                xyxy = row[:4]
                track_id = None
                confidence = float(row[4])
                class_id = int(row[5])
            detections.append(
                Detection(
                    label=str(self._model.names[class_id]),
                    confidence=confidence,
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


    def classify_vehicle(self, frame, box) -> dict | None:
        """Compatibility wrapper for the optional user-supplied crop classifier."""

        height, width = frame.shape[:2]
        x1 = max(0, min(width - 1, int(box.x1)))
        y1 = max(0, min(height - 1, int(box.y1)))
        x2 = max(x1 + 1, min(width, int(box.x2)))
        y2 = max(y1 + 1, min(height, int(box.y2)))
        crop = frame[y1:y2, x1:x2]
        return self.classify_vehicle_crop(crop).get("custom_make_model")

    def classify_vehicle_crop(self, crop) -> dict:
        """Run optional learned attribute models on one selected crop after video decoding."""

        predictions: dict = {}
        if crop is None or crop.size == 0:
            return predictions

        if self._vehicle_classifier is not None:
            results = self._vehicle_classifier.predict(
                source=crop,
                imgsz=224,
                device=self._device,
                half=self._half,
                verbose=False,
            )
            if results and results[0].probs is not None:
                probabilities = results[0].probs
                class_id = int(probabilities.top1)
                confidence = float(probabilities.top1conf.item())
                names = self._vehicle_classifier.names
                label = (
                    str(names[class_id])
                    if isinstance(names, dict)
                    else str(names[class_id])
                )
                predictions["custom_make_model"] = {
                    "label": label,
                    "confidence": confidence,
                }

        if self._pretrained_attributes_enabled:
            if self._pretrained_attributes is None and not self._pretrained_attributes_error:
                try:
                    from traffic_surveillance.vision.vehicle_attributes import (
                        PretrainedVehicleAttributes,
                    )

                    self._pretrained_attributes = PretrainedVehicleAttributes()
                except Exception as exc:
                    self._pretrained_attributes_error = type(exc).__name__
            if self._pretrained_attributes is not None:
                predictions.update(self._pretrained_attributes.classify(crop))
            elif self._pretrained_attributes_error:
                predictions["attribute_model_error"] = self._pretrained_attributes_error
        return predictions
