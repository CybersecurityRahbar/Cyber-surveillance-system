from collections import defaultdict, deque
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Callable

from traffic_surveillance.analytics.line_crossing import DirectedLineCounter
from traffic_surveillance.domain.models import Detection, TimestampQuality

VEHICLE_CLASSES = {"car", "motorcycle", "motorbike", "bus", "truck", "bicycle"}
PERSON_CLASSES = {"person"}
CLASS_LABELS = {
    "car": "CAR",
    "motorcycle": "MOTORCYCLE",
    "motorbike": "MOTORCYCLE",
    "bus": "BUS",
    "truck": "TRUCK",
    "bicycle": "BICYCLE",
    "person": "PERSON",
}


class VideoLabProcessor:
    """Analyze one local file or one live source and render a radar-style MP4."""

    def __init__(self, detector) -> None:
        self.detector = detector

    def run(
        self,
        source: str | int | Path,
        output_path: str | Path,
        *,
        line_position: float = 0.65,
        max_width: int = 1280,
        live_duration_seconds: int | None = None,
        stop_event: Event | None = None,
        on_progress: Callable[[dict], None] | None = None,
        on_preview: Callable[[bytes], None] | None = None,
        on_crossing: Callable[[dict], None] | None = None,
    ) -> dict:
        import cv2

        try:
            import av
        except ImportError as exc:
            raise RuntimeError(
                "PyAV is required for media timestamp decoding. Install with: "
                "pip install -e '.[video,vision]'"
            ) from exc

        if not 0.1 <= line_position <= 0.9:
            raise ValueError("line_position must be between 0.1 and 0.9.")
        if max_width not in {960, 1280, 1920}:
            raise ValueError("max_width must be 960, 1280 or 1920.")

        destination = Path(output_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        is_webcam = isinstance(source, int)
        container = None
        capture = None
        writer = None
        decoded_frames = None
        start_clock = monotonic()
        started_at = datetime.now(UTC)
        first_media_time = None
        last_media_time = None
        fps_source = 25.0
        total_frames = None
        frame_index = 0
        processed_frames = 0
        preview_frames = 0
        frame_size = None
        line_counter = None
        line_y = None

        unique_by_class: dict[str, set[int]] = defaultdict(set)
        current_by_class: dict[str, set[int]] = defaultdict(set)
        unique_vehicle_keys: set[tuple[str, int]] = set()
        unique_person_ids: set[int] = set()
        track_trails: dict[int, deque] = defaultdict(lambda: deque(maxlen=18))
        crossing_counts = {"down": 0, "up": 0}
        crossing_keys: set[tuple[int, str]] = set()
        timestamp_qualities: set[str] = set()

        try:
            if is_webcam:
                capture = cv2.VideoCapture(source)
                if not capture.isOpened():
                    raise RuntimeError(f"Could not open server camera index {source}.")
                fps_source = float(capture.get(cv2.CAP_PROP_FPS) or 25.0)
                if fps_source <= 0:
                    fps_source = 25.0
            else:
                open_options = {}
                if isinstance(source, str) and source.lower().startswith(("rtsp://", "rtsps://")):
                    open_options = {
                        "rtsp_transport": "tcp",
                        "rw_timeout": "5000000",
                        "max_delay": "500000",
                    }
                container = av.open(
                    str(source),
                    mode="r",
                    options=open_options,
                    timeout=(5.0, 5.0),
                )
                video_streams = [item for item in container.streams if item.type == "video"]
                if not video_streams:
                    raise RuntimeError("The selected source does not contain a video stream.")
                stream = video_streams[0]
                if stream.average_rate:
                    fps_source = float(stream.average_rate)
                elif stream.guessed_rate:
                    fps_source = float(stream.guessed_rate)
                if fps_source <= 0:
                    fps_source = 25.0
                total_frames = stream.frames or None
                decoded_frames = iter(container.decode(stream))

            while True:
                if stop_event is not None and stop_event.is_set():
                    break
                if live_duration_seconds is not None and monotonic() - start_clock >= live_duration_seconds:
                    break

                if is_webcam:
                    ok, image = capture.read()
                    if not ok:
                        break
                    media_time = monotonic() - start_clock
                    timestamp_quality = TimestampQuality.ARRIVAL_MONOTONIC
                else:
                    try:
                        frame = next(decoded_frames)
                    except StopIteration:
                        break
                    if frame.pts is not None and frame.time_base:
                        media_time = float(frame.pts * frame.time_base)
                        timestamp_quality = TimestampQuality.SOURCE_PTS
                    else:
                        media_time = frame_index / fps_source
                        timestamp_quality = TimestampQuality.MEDIA_TIME_ESTIMATED
                    image = frame.to_ndarray(format="bgr24")

                if first_media_time is None:
                    first_media_time = media_time
                last_media_time = media_time
                timestamp_qualities.add(timestamp_quality.value)

                height, width = image.shape[:2]
                if width > max_width:
                    scale = max_width / width
                    image = cv2.resize(
                        image,
                        (max_width, round(height * scale)),
                        interpolation=cv2.INTER_AREA,
                    )
                    height, width = image.shape[:2]

                if writer is None:
                    frame_size = (width, height)
                    line_y = int(height * line_position)
                    line_counter = DirectedLineCounter(
                        (0.0, float(line_y)),
                        (float(width - 1), float(line_y)),
                    )
                    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
                    writer = cv2.VideoWriter(str(destination), fourcc, fps_source, frame_size)
                    if not writer.isOpened():
                        raise RuntimeError(
                            "Could not initialize MP4 writer. Check OpenCV video codec support."
                        )

                detections: list[Detection] = self.detector.detect_and_track(image)
                current_by_class.clear()
                display_detections: list[tuple[Detection, str]] = []

                for detection in detections:
                    label = detection.label.strip().lower()
                    display_label = CLASS_LABELS.get(label, label.upper()[:18])
                    display_detections.append((detection, display_label))
                    track_id = detection.track_id
                    if track_id is None:
                        continue

                    current_by_class[label].add(track_id)
                    if label in VEHICLE_CLASSES:
                        unique_by_class[label].add(track_id)
                        unique_vehicle_keys.add((label, track_id))
                        foot = (
                            (detection.box.x1 + detection.box.x2) / 2.0,
                            detection.box.y2,
                        )
                        crossing = line_counter.update(track_id, foot)
                        track_trails[track_id].append((int(foot[0]), int(foot[1])))
                        if crossing is not None:
                            direction = (
                                "down"
                                if crossing.direction == "negative_to_positive"
                                else "up"
                            )
                            key = (track_id, direction)
                            if key not in crossing_keys:
                                crossing_keys.add(key)
                                crossing_counts[direction] += 1
                                if on_crossing is not None:
                                    on_crossing(
                                        {
                                            "track_id": track_id,
                                            "class": label,
                                            "direction": direction,
                                            "frame_index": frame_index,
                                            "media_time_seconds": media_time,
                                            "timestamp_quality": timestamp_quality.value,
                                        }
                                    )
                    elif label in PERSON_CLASSES:
                        unique_person_ids.add(track_id)

                annotated = self._draw_frame(
                    cv2=cv2,
                    image=image,
                    detections=display_detections,
                    trails=track_trails,
                    line_y=line_y,
                    frame_index=frame_index,
                    fps_source=fps_source,
                    processing_fps=processed_frames / max(monotonic() - start_clock, 1e-6),
                    unique_vehicle_tracks=len(unique_vehicle_keys),
                    unique_person_tracks=len(unique_person_ids),
                    crossing_counts=crossing_counts,
                )
                writer.write(annotated)
                processed_frames += 1

                if on_preview is not None and (
                    processed_frames % 2 == 0 or processed_frames == 1
                ):
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        annotated,
                        [int(cv2.IMWRITE_JPEG_QUALITY), 78],
                    )
                    if ok:
                        on_preview(encoded.tobytes())
                        preview_frames += 1

                if on_progress is not None and (
                    processed_frames == 1 or processed_frames % 5 == 0
                ):
                    if total_frames:
                        percent = min(99.0, processed_frames * 100.0 / total_frames)
                    elif live_duration_seconds:
                        percent = min(
                            99.0,
                            (monotonic() - start_clock) * 100.0 / live_duration_seconds,
                        )
                    else:
                        percent = 0.0
                    on_progress(
                        {
                            "progress": round(percent, 1),
                            "frames_processed": processed_frames,
                            "total_frames": total_frames,
                            "processing_fps": round(
                                processed_frames / max(monotonic() - start_clock, 1e-6), 2
                            ),
                            "source_fps": round(fps_source, 2),
                            "class_counts": {
                                CLASS_LABELS.get(label, label.upper()): len(track_ids)
                                for label, track_ids in unique_by_class.items()
                            },
                            "current_counts": {
                                CLASS_LABELS.get(label, label.upper()): len(track_ids)
                                for label, track_ids in current_by_class.items()
                            },
                            "unique_vehicle_tracks": len(unique_vehicle_keys),
                            "unique_person_tracks": len(unique_person_ids),
                            "line_crossings": dict(crossing_counts),
                        }
                    )
                frame_index += 1

        finally:
            if writer is not None:
                writer.release()
            if capture is not None:
                capture.release()
            if container is not None:
                container.close()

        if processed_frames == 0:
            raise RuntimeError(
                "No video frames were decoded. Check the file/stream, codec and permissions."
            )

        elapsed = max(monotonic() - start_clock, 1e-6)
        media_duration = (
            max(0.0, last_media_time - first_media_time)
            if first_media_time is not None and last_media_time is not None
            else 0.0
        )
        class_counts = {
            CLASS_LABELS.get(label, label.upper()): len(track_ids)
            for label, track_ids in unique_by_class.items()
        }
        result = {
            "frames_processed": processed_frames,
            "total_frames": total_frames,
            "source_fps": round(fps_source, 2),
            "processing_fps": round(processed_frames / elapsed, 2),
            "processing_seconds": round(elapsed, 2),
            "media_duration_seconds": round(media_duration, 2),
            "unique_vehicle_tracks": len(unique_vehicle_keys),
            "unique_person_tracks": len(unique_person_ids),
            "class_counts": class_counts,
            "line_crossings": dict(crossing_counts),
            "timestamp_qualities": sorted(timestamp_qualities),
            "speed_status": "requires_camera_calibration",
            "preview_frames_sent": preview_frames,
            "output_width": frame_size[0] if frame_size else 0,
            "output_height": frame_size[1] if frame_size else 0,
            "stopped_by_operator": bool(stop_event and stop_event.is_set()),
            "session_started_at": started_at.isoformat(),
        }
        if on_progress is not None:
            on_progress(
                {
                    "progress": 100.0,
                    "frames_processed": processed_frames,
                    "total_frames": total_frames,
                    "processing_fps": result["processing_fps"],
                    "source_fps": result["source_fps"],
                    "class_counts": class_counts,
                    "current_counts": {},
                    "unique_vehicle_tracks": len(unique_vehicle_keys),
                    "unique_person_tracks": len(unique_person_ids),
                    "line_crossings": dict(crossing_counts),
                }
            )
        return result

    @staticmethod
    def _draw_frame(
        *,
        cv2,
        image,
        detections,
        trails,
        line_y,
        frame_index,
        fps_source,
        processing_fps,
        unique_vehicle_tracks,
        unique_person_tracks,
        crossing_counts,
    ):
        height, width = image.shape[:2]
        green = (70, 255, 120)
        dark = (15, 24, 28)
        muted = (170, 190, 184)
        cv2.line(image, (0, line_y), (width - 1, line_y), green, 2, cv2.LINE_AA)

        for detection, display_label in detections:
            box = detection.box
            x1, y1 = int(box.x1), int(box.y1)
            x2, y2 = int(box.x2), int(box.y2)
            cv2.rectangle(image, (x1, y1), (x2, y2), green, 2, cv2.LINE_AA)
            corner = max(8, min(x2 - x1, y2 - y1) // 5)
            for x, y, sx, sy in (
                (x1, y1, 1, 1),
                (x2, y1, -1, 1),
                (x1, y2, 1, -1),
                (x2, y2, -1, -1),
            ):
                cv2.line(image, (x, y), (x + sx * corner, y), green, 4, cv2.LINE_AA)
                cv2.line(image, (x, y), (x, y + sy * corner), green, 4, cv2.LINE_AA)

            identity = (
                f"ID {detection.track_id:04d}"
                if detection.track_id is not None
                else "UNTRACKED"
            )
            text = f"{identity} | {display_label} | {detection.confidence:.0%}"
            (text_width, text_height), _ = cv2.getTextSize(
                text, cv2.FONT_HERSHEY_SIMPLEX, 0.48, 1
            )
            label_top = max(0, y1 - text_height - 12)
            cv2.rectangle(
                image,
                (x1, label_top),
                (min(width - 1, x1 + text_width + 10), y1),
                green,
                -1,
            )
            cv2.putText(
                image,
                text,
                (x1 + 5, y1 - 6),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.48,
                dark,
                1,
                cv2.LINE_AA,
            )
            foot = ((x1 + x2) // 2, y2)
            cv2.circle(image, foot, 4, green, -1, cv2.LINE_AA)
            if detection.track_id is not None:
                trail = list(trails.get(detection.track_id, []))
                for index in range(1, len(trail)):
                    cv2.line(image, trail[index - 1], trail[index], green, 2, cv2.LINE_AA)

        overlay = image.copy()
        cv2.rectangle(overlay, (12, 12), (min(width - 12, 365), 118), dark, -1)
        cv2.addWeighted(overlay, 0.78, image, 0.22, 0, image)
        cv2.putText(
            image,
            "TRAFFIC RADAR / SINGLE CAMERA LAB",
            (24, 37),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            green,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"FRAME {frame_index + 1:06d}   SOURCE {fps_source:.1f} FPS",
            (24, 62),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            muted,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"VEHICLES {unique_vehicle_tracks}   PEOPLE {unique_person_tracks}",
            (24, 86),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            green,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"LINE DOWN {crossing_counts['down']}   UP {crossing_counts['up']}",
            (24, 107),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.43,
            muted,
            1,
            cv2.LINE_AA,
        )
        cv2.putText(
            image,
            f"AI {processing_fps:.1f} FPS",
            (max(12, width - 150), 30),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.48,
            green,
            1,
            cv2.LINE_AA,
        )
        return image
