from datetime import UTC, datetime
from time import monotonic

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
    assert "bbox" in vehicle["trajectory"][0]
    assert vehicle["first_seen_at"]
    assert vehicle["last_seen_at"]
    assert vehicle["timestamp_basis"] == "analysis_observed_utc"
    assert vehicle["manual_review_required"] is True
    assert vehicle["vehicle_type"] == "CAR"
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


class WeakCustomClassifierDetector(MovingVehicleDetector):
    def classify_vehicle_crop(self, crop):
        return {
            "custom_make_model": {
                "label": "Uncertain Make",
                "confidence": 0.2,
            },
            "vehicle_color_model": {
                "label": "blue",
                "confidence": 0.86,
                "top3": [{"label": "blue", "confidence": 0.86}],
            },
            "make_model_model": {
                "label": "Toyota Camry 2012",
                "confidence": 0.93,
                "make": "Toyota",
                "model": "Camry",
                "year": "2012",
                "top3": [],
            },
        }


def test_pretrained_make_model_is_used_when_custom_classifier_is_uncertain(tmp_path):
    source = tmp_path / "sample.mp4"
    output = tmp_path / "processed.mp4"
    create_test_video(source)

    summary = VideoLabProcessor(WeakCustomClassifierDetector()).run(
        source,
        output,
        line_position=0.5,
        max_width=960,
    )

    vehicle = next(item for item in summary["tracks"] if item["track_id"] == 42)
    assert vehicle["make"] == "Toyota"
    assert vehicle["model"] == "Camry"
    assert vehicle["vehicle_year_estimate"] == "2012"
    assert vehicle["make_model_status"] == "candidate_from_stanford_cars_model"


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


class FakeLivePhoneSource:
    def __init__(self, frame_count=6):
        self._frames = [
            np.zeros((240, 320, 3), dtype=np.uint8)
            for _ in range(frame_count)
        ]
        self._index = 0
        self._closed = False
        self.received_frames = frame_count
        self.dropped_frames = frame_count * 2

    @property
    def closed(self):
        return self._closed

    def read_frame(self, timeout=1.0):
        if self._index >= len(self._frames):
            self._closed = True
            return None
        frame = self._frames[self._index]
        self._index += 1
        return frame, monotonic(), datetime.now(UTC).isoformat(timespec="milliseconds")


def test_live_mode_emits_track_identity_updates_without_waiting_for_final_report(tmp_path):
    source = FakeLivePhoneSource()
    updates = []
    output = tmp_path / "live-output.mp4"

    summary = VideoLabProcessor(MovingVehicleDetector()).run(
        source,
        output,
        line_position=0.5,
        max_width=640,
        live_duration_seconds=None,
        realtime_mode=True,
        record_output=True,
        on_progress=updates.append,
    )

    live_updates = [item for item in updates if item.get("current_tracks")]
    assert len(live_updates) >= 2
    latest = live_updates[-1]["current_tracks"]
    assert latest[0]["track_id"] == 77 or latest[0]["track_id"] == 42
    assert {item["track_id"] for item in latest} == {42, 77}
    assert all("frames_seen" in item and "last_seen_seconds" in item for item in latest)
    assert all("last_seen_at" in item and "last_bbox" in item for item in latest)
    assert updates[-1]["inference_latency_ms"] >= 0
    assert updates[-1]["frame_age_ms"] >= 0
    assert summary["frames_processed"] == 6
    assert summary["output_video_available"] is True
    assert output.is_file()
    assert summary["recording"]["enabled"] is True
    assert summary["recording"]["video_available"] is True
    assert summary["input_frames_received"] == 6
    assert summary["input_frames_dropped"] == 12
    assert summary["tracks"][0]["last_seen_seconds"] >= summary["tracks"][-1]["last_seen_seconds"]



def test_live_session_classifies_vehicle_attributes_after_stop_without_blocking_frame_updates(
    tmp_path,
):
    source = FakeLivePhoneSource(frame_count=6)
    updates = []
    output = tmp_path / "live-attributes.mp4"

    summary = VideoLabProcessor(WeakCustomClassifierDetector()).run(
        source,
        output,
        line_position=0.5,
        max_width=640,
        realtime_mode=True,
        record_output=True,
        on_progress=updates.append,
    )

    vehicle = next(track for track in summary["tracks"] if track["track_id"] == 42)
    assert any(item.get("current_tracks") for item in updates)
    assert vehicle["vehicle_color"] == "blue"
    assert vehicle["vehicle_color_method"] == "learned_efficientnet_b4"
    assert vehicle["make"] == "Toyota"
    assert vehicle["model"] == "Camry"
    assert vehicle["manual_review_required"] is True
    assert "المراجعة اليدوية" in vehicle["manual_review_note"]
    assert summary["attribute_processing_seconds"] >= 0
    assert summary["output_video_available"] is True
