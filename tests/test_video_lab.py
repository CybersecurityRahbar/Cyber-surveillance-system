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
            )
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
    assert summary["class_counts"]["CAR"] == 1
    assert summary["line_crossings"]["down"] == 1
    assert summary["line_crossings"]["up"] == 0
    assert summary["processing_fps"] > 0
    assert previews
    assert previews[0].startswith(b"\xff\xd8")
    assert len(crossings) == 1
    assert progress_updates[-1]["progress"] == 100.0
