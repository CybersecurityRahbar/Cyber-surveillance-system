"""Optional learned vehicle paint-colour and make/model classification."""

from __future__ import annotations

import re
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
        self._make_model_model = timm.create_model(
            f"hf-hub:{MAKE_MODEL_REPOSITORY}", pretrained=True
        )
        self._colour_model.eval().to(self._device)
        self._make_model_model.eval().to(self._device)
        if self._half:
            self._colour_model.half()
            self._make_model_model.half()

        colour_config = resolve_model_data_config(self._colour_model)
        make_config = resolve_model_data_config(self._make_model_model)
        self._colour_transform = create_transform(**colour_config, is_training=False)
        self._make_transform = create_transform(**make_config, is_training=False)

        pretrained_cfg = getattr(self._make_model_model, "pretrained_cfg", {}) or {}
        labels = pretrained_cfg.get("label_names") or pretrained_cfg.get("classnames")
        if isinstance(labels, dict):
            labels = [labels[key] for key in sorted(labels, key=lambda item: int(item))]
        if not isinstance(labels, (list, tuple)) or len(labels) != 196:
            raise RuntimeError(
                "TwinCar weights loaded, but their 196-class label map was not exposed "
                "by timm; make/model results are disabled rather than guessed."
            )
        self._make_model_labels = [str(label) for label in labels]

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
        make_predictions = self._predict(
            self._make_model_model, self._make_transform, image
        )

        colour_index, colour_confidence = colour_predictions[0]
        colour_label = COLOUR_LABELS[colour_index] if 0 <= colour_index < len(COLOUR_LABELS) else None
        make_index, make_confidence = make_predictions[0]
        make_label = (
            self._make_model_labels[make_index]
            if 0 <= make_index < len(self._make_model_labels)
            else None
        )
        accepted_make = make_label if make_confidence >= 0.42 else None
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
                "year": year_match.group(1) if year_match else None,
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
