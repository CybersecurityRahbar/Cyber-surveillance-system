"""Lightweight, explicitly approximate vehicle paint-colour estimation."""

from __future__ import annotations

from typing import Any


def estimate_vehicle_color(frame: Any, box: Any) -> tuple[str | None, float]:
    """Estimate dominant body colour from an inset ROI; never treat it as definitive."""

    import cv2
    import numpy as np

    height, width = frame.shape[:2]
    x1 = max(0, min(width - 1, int(box.x1 + (box.x2 - box.x1) * 0.18)))
    x2 = max(x1 + 1, min(width, int(box.x2 - (box.x2 - box.x1) * 0.18)))
    y1 = max(0, min(height - 1, int(box.y1 + (box.y2 - box.y1) * 0.28)))
    y2 = max(y1 + 1, min(height, int(box.y1 + (box.y2 - box.y1) * 0.82)))
    crop = frame[y1:y2, x1:x2]
    if crop.size == 0 or crop.shape[0] < 12 or crop.shape[1] < 12:
        return None, 0.0

    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    hue = hsv[:, :, 0].astype(np.int16)
    saturation = hsv[:, :, 1].astype(np.int16)
    value = hsv[:, :, 2].astype(np.int16)
    valid = (value > 28) & (value < 250)
    if int(valid.sum()) < 40:
        return None, 0.0

    neutral = valid & (saturation < 48)
    neutral_ratio = float(neutral.sum()) / float(valid.sum())
    if neutral_ratio >= 0.40:
        median_value = float(np.median(value[neutral]))
        if median_value >= 190:
            colour = "white"
        elif median_value <= 52:
            colour = "black"
        elif median_value >= 132:
            colour = "silver"
        else:
            colour = "grey"
        brightness_consistency = 1.0 - min(
            1.0, float(np.std(value[neutral])) / 105.0
        )
        confidence = min(0.82, neutral_ratio * (0.55 + 0.35 * brightness_consistency))
        return colour, round(confidence, 3)

    chromatic = valid & (saturation >= 48)
    if int(chromatic.sum()) < 30:
        return None, 0.0

    weights = saturation[chromatic].astype(np.float64)
    hues = hue[chromatic]
    groups = {
        "red": ((hues <= 7) | (hues >= 171)),
        "orange": ((hues > 7) & (hues <= 20)),
        "yellow": ((hues > 20) & (hues <= 34)),
        "green": ((hues > 34) & (hues <= 82)),
        "blue": ((hues > 82) & (hues <= 124)),
        "purple": ((hues > 124) & (hues < 171)),
    }
    scores = {
        name: float(weights[mask].sum())
        for name, mask in groups.items()
    }
    total = sum(scores.values())
    if total <= 0:
        return None, 0.0
    colour, score = max(scores.items(), key=lambda item: item[1])
    confidence = min(0.78, score / total)
    return colour, round(confidence, 3)
