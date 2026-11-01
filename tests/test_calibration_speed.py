import pytest

from traffic_surveillance.analytics.speed import SpeedEstimator
from traffic_surveillance.domain.models import TimestampQuality
from traffic_surveillance.vision.calibration import HomographyProjector


def test_homography_projects_image_point_to_metric_ground_coordinates() -> None:
    projector = HomographyProjector(
        [[2.0, 0.0, 0.0], [0.0, 3.0, 0.0], [0.0, 0.0, 1.0]]
    )
    projected = projector.project((10.0, 10.0))
    assert projected.x_m == pytest.approx(20.0)
    assert projected.y_m == pytest.approx(30.0)


def test_singular_homography_is_rejected() -> None:
    with pytest.raises(ValueError, match="singular"):
        HomographyProjector([[1, 0, 0], [2, 0, 0], [0, 0, 1]])


def test_speed_requires_verified_calibration_and_source_pts() -> None:
    projector = HomographyProjector([[1, 0, 0], [0, 1, 0], [0, 0, 1]])
    estimator = SpeedEstimator(projector, calibration_verified=True)
    assert estimator.update(7, (0, 0), 0.0, TimestampQuality.SOURCE_PTS) is None

    measurement = estimator.update(7, (10, 0), 1.0, TimestampQuality.SOURCE_PTS)
    assert measurement is not None
    assert measurement.speed_kmh == pytest.approx(36.0)
    assert measurement.valid_for_enforcement

    untrusted = SpeedEstimator(projector, calibration_verified=True)
    untrusted.update(8, (0, 0), 0.0, TimestampQuality.ARRIVAL_MONOTONIC)
    measurement = untrusted.update(8, (10, 0), 1.0, TimestampQuality.ARRIVAL_MONOTONIC)
    assert measurement is not None
    assert not measurement.valid_for_enforcement
