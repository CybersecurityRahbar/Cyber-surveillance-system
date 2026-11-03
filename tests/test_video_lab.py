import cv2
import numpy as np

from traffic_surveillance.domain.models import BoundingBox, Detection
from traffic_surveillance.lab.video_processor import VideoLabProcessor


class MovingVehicleDetector:
    def __init__(self):
        self.index = 0

    def detect_and_track(self, frame):
        self.index += 1
        foot_y = 70 if self.index < 5 else 190
        return [
            Detection(
                label="car",
                confidence=0.96,
                box=BoundingBox(
                    x1=80,
                    y1=foot_y - 45,
                    x2=155,
                    y2=foot_y,
                ),
                track_id=42,
            ),
            Detection(
                label="person",
                confidence=0.91,
                box=BoundingBox(x1=190, y1=70, x2=220, y2=145),
                track_id=77,
            ),
        ]


def create_test_video(path):
    writer = cv2.VideoWriter(
        str(path),
        cv2.VideoWriter_fourcc(*"mp4v"),
        10.0,
        (320, 240),
    )
    assert writer.isOpened()
    for index in range(10):
        frame = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(
            frame,
            f"TEST {index}",
            (20, 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.7,
            (255, 255, 255),
            1,
        )
        writer.write(frame)
    writer.release()


def test_lab_processes_video_tracks_vehicle_and_writes_annotated_output(tmp_path):
    source = tmp_path / "sample.mp4"
    output = tmp_path / "processed.mp4"
    create_test_video(source)

    progress_updates = []
    previews = []
    crossings = []

    summary = VideoLabProcessor(MovingVehicleDetector()).run(
        source,
        output,
        line_position=0.5,
        max_width=960,
        on_progress=progress_updates.append,
        on_preview=previews.append,
        on_crossing=crossings.append,
    )

    assert output.is_file()
    assert output.stat().st_size > 1000
    assert summary["frames_processed"] == 10
    assert summary["unique_vehicle_tracks"] == 1
    assert summary["unique_person_tracks"] == 1
    assert summary["class_counts"]["CAR"] == 1
    assert len(summary["tracks"]) == 2
    vehicle = next(item for item in summary["tracks"] if item["track_id"] == 42)
    person = next(item for item in summary["tracks"] if item["track_id"] == 77)
    assert vehicle["object_type"] == "vehicle"
    assert vehicle["frames_seen"] == 10
    assert vehicle["trajectory"]
    assert "vehicle_color" in vehicle
    assert vehicle["make_model_status"] == "model_not_configured_or_no_confident_result"
    assert person["object_type"] == "person"
    assert person["class_label"] == "PERSON"
    assert summary["line_crossings"]["down"] == 1
    assert summary["line_crossings"]["up"] == 0
    assert summary["processing_fps"] > 0
    assert previews
    assert previews[0].startswith(b"\xff\xd8")
    assert len(crossings) == 1
    assert progress_updates[-1]["progress"] == 100.0


class RelabelledVehicleDetector:
    def __init__(self):
        self.index = 0

    def detect_and_track(self, frame):
        self.index += 1
        label = "car" if self.index % 2 else "truck"
        return [
            Detection(
                label=label,
                confidence=0.9,
                box=BoundingBox(x1=80, y1=80, x2=155, y2=170),
                track_id=42,
            )
        ]


def test_vehicle_id_is_counted_once_when_detector_class_label_changes(tmp_path):
    source = tmp_path / "sample.mp4"
    output = tmp_path / "processed.mp4"
    create_test_video(source)

    summary = VideoLabProcessor(RelabelledVehicleDetector()).run(
        source,
        output,
        line_position=0.5,
        max_width=960,
    )

    assert summary["unique_vehicle_tracks"] == 1
    assert summary["class_counts"] == {"CAR": 1}
    assert summary["tracks"][0]["class_label"] == "CAR"
    assert output.is_file()


def test_vehicle_colour_estimator_keeps_white_and_black_pixels():
    from traffic_surveillance.domain.models import BoundingBox
    from traffic_surveillance.vision.appearance import estimate_vehicle_color

    white_frame = np.full((100, 100, 3), 255, dtype=np.uint8)
    black_frame = np.zeros((100, 100, 3), dtype=np.uint8)
    box = BoundingBox(x1=5, y1=5, x2=95, y2=95)

    white, white_confidence = estimate_vehicle_color(white_frame, box)
    black, black_confidence = estimate_vehicle_color(black_frame, box)

    assert white == "white"
    assert white_confidence > 0
    assert black == "black"
    assert black_confidence > 0
