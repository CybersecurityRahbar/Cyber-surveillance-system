"""Optional learned vehicle paint-colour and make/model classification."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

COLOUR_REPOSITORY = "piotreksl/vehicle-color-recognition"
MAKE_MODEL_REPOSITORY = "twincar-group2/twincar-classifier"
COLOUR_LABELS = (
    "beige", "black", "blue", "brown", "gold", "green", "grey",
    "orange", "pink", "purple", "red", "silver", "white", "yellow",
)


class PretrainedVehicleAttributes:
    """Lazy Hugging Face/timm classifiers; invoke once per completed track, not per frame."""

    def __init__(self) -> None:
        try:
            import timm
            import torch
            from timm.data import create_transform, resolve_model_data_config
        except ImportError as exc:
            raise RuntimeError(
                "Learned vehicle attributes require timm and torchvision. "
                "Install with: pip install -e '.[vision]'"
            ) from exc

        self._torch = torch
        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        self._half = self._device == "cuda"

        self._colour_model = timm.create_model(
            f"hf-hub:{COLOUR_REPOSITORY}", pretrained=True
        )
        self._colour_model.eval().to(self._device)
        if self._half:
            self._colour_model.half()

        colour_config = resolve_model_data_config(self._colour_model)
        self._colour_transform = create_transform(**colour_config, is_training=False)

        self._make_model_model = None
        self._make_model_labels: list[str] = []
        self._make_model_classes: list[dict[str, Any]] = []
        self._make_transform = None
        try:
            mapping_path = (
                Path(__file__).resolve().parents[3]
                / "models"
                / "vehicle"
                / "twincar_stanford_labels.json"
            )
            mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
            classes = sorted(mapping["classes"], key=lambda item: item["class_id"])
            labels = [str(item["label"]) for item in classes]
            if len(labels) != 196 or [item["class_id"] for item in classes] != list(range(196)):
                raise ValueError("TwinCar label map must contain ordered classes 0..195.")

            make_model = timm.create_model(
                f"hf-hub:{MAKE_MODEL_REPOSITORY}", pretrained=True
            )
            if int(getattr(make_model, "num_classes", 0)) != len(labels):
                raise ValueError("TwinCar checkpoint output does not match the label map.")
            self._make_model_model = make_model.eval().to(self._device)
            if self._half:
                self._make_model_model.half()
            self._make_transform = create_transform(
                **resolve_model_data_config(self._make_model_model),
                is_training=False,
            )
            self._make_model_labels = labels
            self._make_model_classes = classes
        except Exception:
            # Colour classification remains useful if the optional make/model
            # checkpoint or its label mapping cannot be resolved.
            self._make_model_model = None

    @staticmethod
    def _to_pil(crop: Any):
        from PIL import Image
        import cv2

        rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    def _predict(self, model, transform, image):
        tensor = transform(image).unsqueeze(0).to(self._device)
        if self._half:
            tensor = tensor.half()
        with self._torch.inference_mode():
            if self._half:
                with self._torch.autocast(device_type="cuda", dtype=self._torch.float16):
                    logits = model(tensor)
            else:
                logits = model(tensor)
            probabilities = self._torch.softmax(logits.float(), dim=1)[0]
            values, indices = self._torch.topk(probabilities, k=min(3, probabilities.numel()))
        return [
            (int(index.item()), float(score.item()))
            for index, score in zip(indices, values, strict=True)
        ]

    def classify(self, crop: Any) -> dict[str, Any]:
        if crop is None or getattr(crop, "size", 0) == 0:
            return {}
        image = self._to_pil(crop)
        colour_predictions = self._predict(
            self._colour_model, self._colour_transform, image
        )
        make_predictions = (
            self._predict(self._make_model_model, self._make_transform, image)
            if self._make_model_model is not None
            else []
        )

        colour_index, colour_confidence = colour_predictions[0]
        colour_label = (
            COLOUR_LABELS[colour_index]
            if 0 <= colour_index < len(COLOUR_LABELS)
            else None
        )
        make_index, make_confidence = make_predictions[0] if make_predictions else (-1, 0.0)
        make_label = (
            self._make_model_labels[make_index]
            if 0 <= make_index < len(self._make_model_labels)
            else None
        )
        accepted_make = make_label if make_confidence >= 0.60 else None
        class_metadata = (
            self._make_model_classes[make_index]
            if 0 <= make_index < len(self._make_model_classes)
            else {}
        )
        year_match = re.search(r"\b(19\d{2}|20\d{2}|202[0-9])\b", make_label or "")
        return {
            "vehicle_color_model": {
                "label": colour_label,
                "confidence": round(colour_confidence, 4),
                "top3": [
                    {"label": COLOUR_LABELS[index], "confidence": round(score, 4)}
                    for index, score in colour_predictions
                    if 0 <= index < len(COLOUR_LABELS)
                ],
                "model": COLOUR_REPOSITORY,
            },
            "make_model_model": {
                "label": accepted_make,
                "candidate_label": make_label,
                "confidence": round(make_confidence, 4),
                "make": class_metadata.get("make") if accepted_make else None,
                "model": class_metadata.get("model") if accepted_make else None,
                "year": (
                    class_metadata.get("year")
                    if accepted_make else (year_match.group(1) if year_match else None)
                ),
                "top3": [
                    {
                        "label": self._make_model_labels[index],
                        "confidence": round(score, 4),
                    }
                    for index, score in make_predictions
                    if 0 <= index < len(self._make_model_labels)
                ],
                "model": MAKE_MODEL_REPOSITORY,
                "status": "candidate" if accepted_make else "low_confidence_or_unknown",
            },
        }
