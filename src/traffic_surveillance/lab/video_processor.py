from collections import defaultdict, deque
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from threading import Event
from time import monotonic

from traffic_surveillance.analytics.line_crossing import DirectedLineCounter
from traffic_surveillance.domain.models import Detection, TimestampQuality
from traffic_surveillance.vision.appearance import estimate_vehicle_color

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
        show_hud: bool = False,
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
        last_preview_at = 0.0
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
        track_records: dict[int, dict] = {}

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
                if (
                    live_duration_seconds is not None
                    and monotonic() - start_clock >= live_duration_seconds
                ):
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

                    object_type = (
                        "vehicle" if label in VEHICLE_CLASSES
                        else "person" if label in PERSON_CLASSES
                        else "other"
                    )
                    if object_type in {"vehicle", "person"}:
                        record = track_records.setdefault(
                            track_id,
                            {
                                "track_id": track_id,
                                "object_type": object_type,
                                "class_label": display_label,
                                "first_frame_index": frame_index,
                                "last_frame_index": frame_index,
                                "first_seen_seconds": round(media_time, 3),
                                "last_seen_seconds": round(media_time, 3),
                                "frames_seen": 0,
                                "confidence_sum": 0.0,
                                "confidence_max": 0.0,
                                "first_bbox": detection.box.model_dump(),
                                "last_bbox": detection.box.model_dump(),
                                "trajectory": [],
                                "line_crossings": [],
                                "_colour_votes": {},
                                "_colour_confidence_sum": 0.0,
                                "_colour_samples": 0,
                                "_make_model_votes": {},
                                "_make_model_samples": 0,
                                "_make_model_attempts": 0,
                            },
                        )
                        record["frames_seen"] += 1
                        record["last_frame_index"] = frame_index
                        record["last_seen_seconds"] = round(media_time, 3)
                        record["confidence_sum"] += detection.confidence
                        record["confidence_max"] = max(
                            record["confidence_max"], detection.confidence
                        )
                        record["last_bbox"] = detection.box.model_dump()
                        if frame_index % 3 == 0 and len(record["trajectory"]) < 240:
                            record["trajectory"].append(
                                {
                                    "frame": frame_index,
                                    "time": round(media_time, 3),
                                    "x": round((detection.box.x1 + detection.box.x2) / 2, 1),
                                    "y": round((detection.box.y1 + detection.box.y2) / 2, 1),
                                }
                            )
                        if object_type == "vehicle" and frame_index % 10 == 0:
                            colour, colour_confidence = estimate_vehicle_color(
                                image, detection.box
                            )
                            if colour and colour_confidence >= 0.22:
                                votes = record["_colour_votes"]
                                votes[colour] = votes.get(colour, 0) + colour_confidence
                                record["_colour_confidence_sum"] += colour_confidence
                                record["_colour_samples"] += 1

                        if (
                            object_type == "vehicle"
                            and frame_index % 15 == 0
                            and record.get("_make_model_attempts", 0) < 5
                        ):
                            record["_make_model_attempts"] = (
                                record.get("_make_model_attempts", 0) + 1
                            )
                            classifier = getattr(self.detector, "classify_vehicle", None)
                            prediction = (
                                classifier(image, detection.box)
                                if callable(classifier)
                                else None
                            )
                            if prediction and prediction.get("confidence", 0.0) >= 0.45:
                                votes = record.setdefault("_make_model_votes", {})
                                name = str(prediction["label"])
                                votes[name] = votes.get(name, 0.0) + float(
                                    prediction["confidence"]
                                )
                                record["_make_model_samples"] = (
                                    record.get("_make_model_samples", 0) + 1
                                )

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
                                if track_id in track_records:
                                    track_records[track_id]["line_crossings"].append(
                                        {
                                            "direction": direction,
                                            "frame_index": frame_index,
                                            "time_seconds": round(media_time, 3),
                                        }
                                    )
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
                    show_hud=show_hud,
                )
                writer.write(annotated)
                processed_frames += 1

                preview_clock = monotonic()
                if on_preview is not None and (
                    processed_frames == 1 or preview_clock - last_preview_at >= 1.0 / 12.0
                ):
                    ok, encoded = cv2.imencode(
                        ".jpg",
                        annotated,
                        [int(cv2.IMWRITE_JPEG_QUALITY), 68],
                    )
                    if ok:
                        on_preview(encoded.tobytes())
                        preview_frames += 1
                        last_preview_at = preview_clock

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
                            "current_tracks": [
                                {
                                    "track_id": item.track_id,
                                    "class_label": display_label,
                                    "object_type": (
                                        "vehicle" if item.label.lower() in VEHICLE_CLASSES
                                        else "person" if item.label.lower() in PERSON_CLASSES
                                        else "other"
                                    ),
                                    "confidence": round(item.confidence, 3),
                                }
                                for item, display_label in display_detections
                                if item.track_id is not None
                            ],
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
        track_reports = []
        for record in track_records.values():
            colour_votes = record.pop("_colour_votes")
            colour_total = sum(colour_votes.values())
            if colour_total:
                colour, winning_vote = max(colour_votes.items(), key=lambda item: item[1])
                record["vehicle_color"] = colour
                record["vehicle_color_confidence"] = round(
                    winning_vote / max(1, record["_colour_samples"]), 3
                )
            else:
                record["vehicle_color"] = None
                record["vehicle_color_confidence"] = 0.0
            colour_samples = record.pop("_colour_samples")
            record.pop("_colour_confidence_sum")
            model_votes = record.pop("_make_model_votes", {})
            model_total = sum(model_votes.values())
            if model_total:
                model_label, model_score = max(
                    model_votes.items(), key=lambda item: item[1]
                )
                parts = model_label.replace("_", " ").replace("-", " ").split()
                record["make"] = parts[0] if parts else None
                record["model"] = " ".join(parts[1:]) if len(parts) > 1 else None
                record["make_model"] = model_label
                record["make_model_confidence"] = round(
                    model_score / max(1, record.pop("_make_model_samples", 1)), 3
                )
                record["make_model_status"] = "classified_by_configured_model"
                record["make_model_samples"] = record.pop("_make_model_samples", 0)
                record["make_model_attempts"] = record.pop("_make_model_attempts", 0)
            else:
                record["make"] = None
                record["model"] = None
                record["make_model"] = None
                record["make_model_confidence"] = 0.0
                record["make_model_status"] = "model_not_configured_or_no_confident_result"
                record["make_model_samples"] = record.pop("_make_model_samples", 0)
                record["make_model_attempts"] = record.pop("_make_model_attempts", 0)
            record["average_confidence"] = round(
                record.pop("confidence_sum") / max(1, record["frames_seen"]), 3
            )
            record["confidence_max"] = round(record["confidence_max"], 3)
            record["duration_seconds"] = round(
                max(0.0, record["last_seen_seconds"] - record["first_seen_seconds"]), 3
            )
            record["vehicle_color_samples"] = colour_samples
            track_reports.append(record)
        track_reports.sort(key=lambda item: (item["first_seen_seconds"], item["track_id"]))

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
            "tracks": track_reports,
            "track_reports_count": len(track_reports),
            "vehicle_attribute_status": "estimated_colour_only_make_model_not_configured",
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
                    "current_tracks": [],
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
        show_hud=False,
    ):
        height, width = image.shape[:2]
        vehicle_green = (74, 236, 126)
        person_blue = (255, 142, 64)
        muted = (196, 211, 218)
        cv2.line(image, (0, line_y), (width - 1, line_y), (74, 210, 128), 1, cv2.LINE_AA)

        for detection, display_label in detections:
            box = detection.box
            x1 = max(0, min(width - 1, int(box.x1)))
            y1 = max(0, min(height - 1, int(box.y1)))
            x2 = max(x1 + 1, min(width - 1, int(box.x2)))
            y2 = max(y1 + 1, min(height - 1, int(box.y2)))
            is_person = display_label == "PERSON"
            accent = person_blue if is_person else vehicle_green
            cv2.rectangle(image, (x1, y1), (x2, y2), accent, 2, cv2.LINE_AA)

            corner = max(5, min(x2 - x1, y2 - y1) // 7)
            for x, y, sx, sy in (
                (x1, y1, 1, 1),
                (x2, y1, -1, 1),
                (x1, y2, 1, -1),
                (x2, y2, -1, -1),
            ):
                cv2.line(image, (x, y), (x + sx * corner, y), accent, 2, cv2.LINE_AA)
                cv2.line(image, (x, y), (x, y + sy * corner), accent, 2, cv2.LINE_AA)

            identity = f"#{detection.track_id}" if detection.track_id is not None else "#—"
            label = "PERSON" if is_person else display_label
            text = f"{identity}  {label}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            scale = 0.34
            thickness = 1
            (text_width, text_height), baseline = cv2.getTextSize(
                text, font, scale, thickness
            )
            pad_x, pad_y = 4, 3
            pill_width = min(width - 1, text_width + pad_x * 2)
            label_left = min(max(0, x1), max(0, width - pill_width - 1))
            label_top = y1 - text_height - baseline - pad_y * 2 - 2
            if label_top < 0:
                label_top = min(height - text_height - baseline - pad_y * 2, y1 + 2)
            label_right = min(width - 1, label_left + pill_width)
            label_bottom = min(height - 1, label_top + text_height + baseline + pad_y * 2)
            overlay = image.copy()
            cv2.rectangle(
                overlay,
                (label_left, label_top),
                (label_right, label_bottom),
                accent,
                -1,
            )
            cv2.addWeighted(overlay, 0.72, image, 0.28, 0, image)
            cv2.putText(
                image,
                text,
                (label_left + pad_x, label_top + text_height + pad_y),
                font,
                scale,
                (8, 20, 20),
                thickness,
                cv2.LINE_AA,
            )

            foot = ((x1 + x2) // 2, y2)
            cv2.circle(image, foot, 3, accent, -1, cv2.LINE_AA)
            if detection.track_id is not None:
                trail = list(trails.get(detection.track_id, []))
                for index in range(1, len(trail)):
                    cv2.line(
                        image,
                        trail[index - 1],
                        trail[index],
                        accent,
                        1,
                        cv2.LINE_AA,
                    )

        if show_hud:
            hud_width = min(178, max(130, width // 6))
            hud_height = 58
            overlay = image.copy()
            cv2.rectangle(overlay, (10, 10), (10 + hud_width, 10 + hud_height), (9, 20, 26), -1)
            cv2.addWeighted(overlay, 0.34, image, 0.66, 0, image)
            cv2.putText(
                image,
                "TRAFFIC / LIVE",
                (17, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.34,
                vehicle_green,
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                f"FRAME {frame_index + 1}  {processing_fps:.1f} FPS",
                (17, 40),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.30,
                muted,
                1,
                cv2.LINE_AA,
            )
            cv2.putText(
                image,
                f"VEH {unique_vehicle_tracks}  PPL {unique_person_tracks}",
                (17, 54),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.30,
                muted,
                1,
                cv2.LINE_AA,
            )
        return image
