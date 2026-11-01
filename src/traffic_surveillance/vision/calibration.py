from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Projection:
    x_m: float
    y_m: float


class HomographyProjector:
    """Project image coordinates onto a calibrated planar road surface."""

    def __init__(self, matrix: list[list[float]] | np.ndarray) -> None:
        value = np.asarray(matrix, dtype=np.float64)
        if value.shape != (3, 3) or not np.isfinite(value).all():
            raise ValueError("Homography must be a finite 3x3 matrix.")
        if abs(float(np.linalg.det(value))) < 1e-10:
            raise ValueError("Homography matrix is singular.")
        self._matrix = value

    @property
    def matrix(self) -> np.ndarray:
        return self._matrix.copy()

    def project(self, point: tuple[float, float]) -> Projection:
        vector = self._matrix @ np.array([point[0], point[1], 1.0], dtype=np.float64)
        denominator = float(vector[2])
        if abs(denominator) < 1e-10:
            raise ValueError("Point projects to infinity under this homography.")
        return Projection(float(vector[0] / denominator), float(vector[1] / denominator))

    @classmethod
    def fit_ransac(
        cls,
        image_points: list[tuple[float, float]],
        ground_points_m: list[tuple[float, float]],
        *,
        reprojection_threshold_m: float = 0.25,
    ) -> tuple["HomographyProjector", list[bool]]:
        """Fit pixel-to-ground homography; RANSAC threshold is measured in ground units."""
        if len(image_points) != len(ground_points_m) or len(image_points) < 4:
            raise ValueError("At least four paired image/ground points are required.")
        if reprojection_threshold_m <= 0:
            raise ValueError("reprojection_threshold_m must be positive.")
        try:
            import cv2
        except ImportError as exc:
            raise RuntimeError(
                "OpenCV is required for RANSAC fitting. Install the 'vision' extra."
            ) from exc

        source = np.asarray(image_points, dtype=np.float32)
        destination = np.asarray(ground_points_m, dtype=np.float32)
        matrix, mask = cv2.findHomography(
            source,
            destination,
            method=cv2.RANSAC,
            ransacReprojThreshold=reprojection_threshold_m,
        )
        if matrix is None or mask is None:
            raise ValueError("Could not estimate a valid homography from these points.")
        return cls(matrix), [bool(value) for value in mask.ravel()]
