"""
Face detection and speaker-aware reframing for vertical clip cropping.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import logging
import tempfile
import re

import cv2
import numpy as np

from .ffmpeg_utils import (
    run_ffmpeg_command,
    ffprobe_video_size,
    ffprobe_duration,
    ffmpeg_escape_filter_path,
    ffmpeg_escape_filter_value,
    round_to_even,
    clamp_even,
    count_scene_cuts,
    parse_motion_metadata,
)

logger = logging.getLogger(__name__)


def detect_faces_in_clip(
    video_path: Path, start_time: float, end_time: float
) -> List[Tuple[int, int, int, float]]:
    face_centers = []
    try:
        mp_face_detection = None
        try:
            import mediapipe as mp
            mp_face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0, min_detection_confidence=0.5,
            )
            logger.info("Using MediaPipe face detector")
        except ImportError:
            logger.info("MediaPipe not available, falling back to OpenCV")
        except Exception as e:
            logger.warning(f"MediaPipe face detector failed to initialize: {e}")

        haar_cascade = cv2.CascadeClassifier(
            cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        )
        dnn_net = None
        try:
            prototxt_path = cv2.data.haarcascades.replace(
                "haarcascades", "opencv_face_detector.pbtxt"
            )
            model_path = cv2.data.haarcascades.replace(
                "haarcascades", "opencv_face_detector_uint8.pb"
            )
            import os
            if os.path.exists(prototxt_path) and os.path.exists(model_path):
                dnn_net = cv2.dnn.readNetFromTensorflow(model_path, prototxt_path)
                logger.info("OpenCV DNN face detector loaded as backup")
        except Exception:
            pass

        duration = end_time - start_time
        sample_interval = min(0.5, duration / 10)
        sample_times = []
        current_time = start_time
        while current_time < end_time:
            sample_times.append(current_time)
            current_time += sample_interval
        if duration > 1.0:
            middle_time = start_time + duration / 2
            if middle_time not in sample_times:
                sample_times.append(middle_time)
        sample_times = [t for t in sample_times if t < end_time]

        capture = cv2.VideoCapture(str(video_path))
        if not capture.isOpened():
            logger.warning("Unable to open video for face detection: %s", video_path)
            return []

        for sample_time in sample_times:
            try:
                capture.set(cv2.CAP_PROP_POS_MSEC, max(0.0, sample_time) * 1000.0)
                ok, frame_bgr = capture.read()
                if not ok or frame_bgr is None:
                    continue
                frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                height, width = frame.shape[:2]
                detected_faces = []

                if mp_face_detection is not None:
                    try:
                        results = mp_face_detection.process(frame)
                        if results.detections:
                            for detection in results.detections:
                                bbox = detection.location_data.relative_bounding_box
                                confidence = detection.score[0]
                                x = int(bbox.xmin * width)
                                y = int(bbox.ymin * height)
                                w = int(bbox.width * width)
                                h = int(bbox.height * height)
                                if w > 30 and h > 30:
                                    detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"MediaPipe detection failed for frame at {sample_time}s: {e}")

                if not detected_faces and dnn_net is not None:
                    try:
                        blob = cv2.dnn.blobFromImage(frame_bgr, 1.0, (300, 300), [104, 117, 123])
                        dnn_net.setInput(blob)
                        detections = dnn_net.forward()
                        for i in range(detections.shape[2]):
                            confidence = detections[0, 0, i, 2]
                            if confidence > 0.5:
                                x1 = int(detections[0, 0, i, 3] * width)
                                y1 = int(detections[0, 0, i, 4] * height)
                                x2 = int(detections[0, 0, i, 5] * width)
                                y2 = int(detections[0, 0, i, 6] * height)
                                w = x2 - x1
                                h = y2 - y1
                                if w > 30 and h > 30:
                                    detected_faces.append((x1, y1, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"DNN detection failed for frame at {sample_time}s: {e}")

                if not detected_faces:
                    try:
                        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
                        faces = haar_cascade.detectMultiScale(
                            gray, scaleFactor=1.05, minNeighbors=3,
                            minSize=(40, 40), maxSize=(int(width * 0.7), int(height * 0.7)),
                        )
                        for x, y, w, h in faces:
                            face_area = w * h
                            relative_size = face_area / (width * height)
                            confidence = min(0.9, 0.3 + relative_size * 2)
                            detected_faces.append((x, y, w, h, confidence))
                    except Exception as e:
                        logger.warning(f"Haar cascade detection failed for frame at {sample_time}s: {e}")

                for x, y, w, h, confidence in detected_faces:
                    face_center_x = x + w // 2
                    face_center_y = y + h // 2
                    face_area = w * h
                    frame_area = width * height
                    relative_area = face_area / frame_area
                    if 0.005 < relative_area < 0.3:
                        face_centers.append((face_center_x, face_center_y, face_area, confidence))

            except Exception as e:
                logger.warning(f"Error detecting faces in frame at {sample_time}s: {e}")
                continue

        capture.release()
        if mp_face_detection is not None:
            mp_face_detection.close()

        if len(face_centers) > 2:
            face_centers = filter_face_outliers(face_centers)
        logger.info(f"Detected {len(face_centers)} reliable face centers")
        return face_centers

    except Exception as e:
        logger.error(f"Error in face detection: {e}")
        return []


def filter_face_outliers(
    face_centers: List[Tuple[int, int, int, float]],
) -> List[Tuple[int, int, int, float]]:
    if len(face_centers) < 3:
        return face_centers
    try:
        x_positions = [x for x, y, area, conf in face_centers]
        y_positions = [y for x, y, area, conf in face_centers]
        median_x = np.median(x_positions)
        median_y = np.median(y_positions)
        std_x = np.std(x_positions)
        std_y = np.std(y_positions)
        filtered_faces = []
        for face in face_centers:
            x, y, area, conf = face
            if abs(x - median_x) <= 2 * std_x and abs(y - median_y) <= 2 * std_y:
                filtered_faces.append(face)
        logger.info(f"Filtered {len(face_centers)} -> {len(filtered_faces)} faces (removed outliers)")
        return filtered_faces if filtered_faces else face_centers
    except Exception as e:
        logger.warning(f"Error filtering face outliers: {e}")
        return face_centers


def detect_optimal_crop_region(
    video_path: Path,
    start_time: float,
    end_time: float,
    target_ratio: float = 9 / 16,
) -> Tuple[int, int, int, int]:
    try:
        original_width, original_height = ffprobe_video_size(video_path)
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))

        face_centers = detect_faces_in_clip(video_path, start_time, end_time)

        if face_centers:
            total_weight = sum(area * confidence for _, _, area, confidence in face_centers)
            if total_weight > 0:
                weighted_x = sum(x * area * confidence for x, y, area, confidence in face_centers) / total_weight
                weighted_y = sum(y * area * confidence for x, y, area, confidence in face_centers) / total_weight
                weighted_y = max(0, weighted_y - new_height * 0.1)
                x_offset = max(0, min(int(weighted_x - new_width // 2), original_width - new_width))
                y_offset = max(0, min(int(weighted_y - new_height // 2), original_height - new_height))
                logger.info(f"Face-centered crop: {len(face_centers)} faces detected")
            else:
                x_offset = (original_width - new_width) // 2 if original_width > new_width else 0
                y_offset = (original_height - new_height) // 2 if original_height > new_height else 0
        else:
            x_offset = (original_width - new_width) // 2 if original_width > new_width else 0
            y_offset = (original_height - new_height) // 2 if original_height > new_height else 0

        x_offset = round_to_even(x_offset)
        y_offset = round_to_even(y_offset)
        return (x_offset, y_offset, new_width, new_height)

    except Exception as e:
        logger.error(f"Error in crop detection: {e}")
        original_width, original_height = ffprobe_video_size(video_path)
        if original_width / original_height > target_ratio:
            new_width = round_to_even(int(original_height * target_ratio))
            new_height = round_to_even(original_height)
        else:
            new_width = round_to_even(original_width)
            new_height = round_to_even(int(original_width / target_ratio))
        x_offset = round_to_even((original_width - new_width) // 2) if original_width > new_width else 0
        y_offset = round_to_even((original_height - new_height) // 2) if original_height > new_height else 0
        return (x_offset, y_offset, new_width, new_height)


def smooth_values(values: List[float], window: int = 15) -> List[float]:
    if not values:
        return []
    smoothed: List[float] = []
    half = window // 2
    for idx in range(len(values)):
        start = max(0, idx - half)
        end = min(len(values), idx + half + 1)
        smoothed.append(sum(values[start:end]) / (end - start))
    return smoothed


def build_speaker_timeline_from_motion(
    times: List[float], left_values: List[float], right_values: List[float],
    min_duration: float = 1.0,
) -> List[Dict[str, Any]]:
    if not times or len(left_values) != len(right_values):
        return []

    def normalize(values: List[float]) -> List[float]:
        mean_value = sum(values) / max(len(values), 1)
        return [value / mean_value if mean_value > 0 else 0.0 for value in values]

    left = smooth_values(normalize(left_values))
    right = smooth_values(normalize(right_values))
    if not left or not right:
        return []

    margin = 1.15
    current = 0 if left[0] >= right[0] else 1
    speakers: List[int] = []
    for left_value, right_value in zip(left, right):
        if current == 0 and right_value > left_value * margin:
            current = 1
        elif current == 1 and left_value > right_value * margin:
            current = 0
        speakers.append(current)

    segments: List[Dict[str, Any]] = []
    idx = 0
    while idx < len(speakers):
        end_idx = idx
        while end_idx + 1 < len(speakers) and speakers[end_idx + 1] == speakers[idx]:
            end_idx += 1
        seg_start = times[idx]
        seg_end = times[min(end_idx + 1, len(times) - 1)]
        if seg_end <= seg_start:
            seg_end = seg_start + 0.05
        segments.append({
            "start": seg_start, "end": seg_end,
            "speaker": "left" if speakers[idx] == 0 else "right",
        })
        idx = end_idx + 1

    merged: List[Dict[str, Any]] = []
    for segment in segments:
        if merged and segment["end"] - segment["start"] < min_duration:
            merged[-1]["end"] = segment["end"]
            continue
        if merged and merged[-1]["speaker"] == segment["speaker"]:
            merged[-1]["end"] = segment["end"]
            continue
        merged.append(segment)
    return merged


def cluster_two_face_regions(
    face_centers: List[Tuple[int, int, int, float]], width: int, height: int,
) -> Optional[Dict[str, Dict[str, int]]]:
    if len(face_centers) < 2:
        return None
    median_x = float(np.median([face[0] for face in face_centers]))
    left_faces = [face for face in face_centers if face[0] <= median_x]
    right_faces = [face for face in face_centers if face[0] > median_x]
    if not left_faces or not right_faces:
        return None

    def region(faces: List[Tuple[int, int, int, float]]) -> Dict[str, int]:
        center_x = int(np.median([face[0] for face in faces]))
        center_y = int(np.median([face[1] for face in faces]))
        face_size = int(np.sqrt(max(1, float(np.median([face[2] for face in faces])))))
        roi_w = max(80, int(face_size * 1.4))
        roi_h = max(70, int(face_size * 0.9))
        roi_x = clamp_even(center_x - roi_w // 2, 0, max(0, width - roi_w))
        roi_y = clamp_even(center_y, 0, max(0, height - roi_h))
        tile_w = min(width, max(160, int(face_size * 2.8)))
        tile_h = min(height, max(160, int(face_size * 2.4)))
        tile_x = clamp_even(center_x - tile_w // 2, 0, max(0, width - tile_w))
        tile_y = clamp_even(center_y - int(tile_h * 0.42), 0, max(0, height - tile_h))
        return {
            "center_x": center_x, "center_y": center_y,
            "roi_x": roi_x, "roi_y": roi_y,
            "roi_w": round_to_even(min(roi_w, width - roi_x)),
            "roi_h": round_to_even(min(roi_h, height - roi_y)),
            "tile_x": tile_x, "tile_y": tile_y,
            "tile_w": round_to_even(min(tile_w, width - tile_x)),
            "tile_h": round_to_even(min(tile_h, height - tile_y)),
        }

    left = region(left_faces)
    right = region(right_faces)
    if abs(right["center_x"] - left["center_x"]) < width * 0.15:
        return None
    return {"left": left, "right": right}


def build_pan_expression(
    timeline: List[Dict[str, Any]], left_x: int, right_x: int
) -> str:
    if not timeline:
        return str(left_x)

    def x_for(speaker: str) -> int:
        return left_x if speaker == "left" else right_x

    expression = str(x_for(timeline[-1]["speaker"]))
    for segment in reversed(timeline[:-1]):
        expression = (
            f"if(lt(t\\,{segment['end']:.4f})\\,{x_for(segment['speaker'])}\\,{expression})"
        )
    return expression


def detect_speaker_reframe_plan(
    clip_path: Path, output_format: str,
) -> Optional[Dict[str, Any]]:
    try:
        width, height = ffprobe_video_size(clip_path)
        if width / max(height, 1) <= 1.2:
            return None
        scene_cuts = count_scene_cuts(clip_path)
        if scene_cuts > 2:
            logger.info("Skipping speaker reframe: %d scene cuts detected", scene_cuts)
            return None
        duration = ffprobe_duration(clip_path)
        face_centers = detect_faces_in_clip(clip_path, 0, min(duration, 12.0))
        regions = cluster_two_face_regions(face_centers, width, height)
        if not regions:
            return None
        crop_w = round_to_even(min(width, int(height * 9 / 16)))
        left_x = clamp_even(regions["left"]["center_x"] - crop_w // 2, 0, max(0, width - crop_w))
        right_x = clamp_even(regions["right"]["center_x"] - crop_w // 2, 0, max(0, width - crop_w))

        if output_format == "vertical_split":
            return {"mode": "split", "width": width, "height": height, "regions": regions}

        with tempfile.TemporaryDirectory(prefix="supoclip_motion_") as motion_dir:
            left_motion = Path(motion_dir) / "left.txt"
            right_motion = Path(motion_dir) / "right.txt"
            left_reg = regions["left"]
            right_reg = regions["right"]
            filter_complex = (
                f"[0:v]split=2[l][r];"
                f"[l]crop={left_reg['roi_w']}:{left_reg['roi_h']}:{left_reg['roi_x']}:{left_reg['roi_y']},"
                f"format=gray,tblend=all_mode=difference,signalstats,"
                f"metadata=mode=print:key=lavfi.signalstats.YAVG:file={ffmpeg_escape_filter_path(left_motion)}[lo];"
                f"[r]crop={right_reg['roi_w']}:{right_reg['roi_h']}:{right_reg['roi_x']}:{right_reg['roi_y']},"
                f"format=gray,tblend=all_mode=difference,signalstats,"
                f"metadata=mode=print:key=lavfi.signalstats.YAVG:file={ffmpeg_escape_filter_path(right_motion)}[ro]"
            )
            result = run_ffmpeg_command(
                [
                    "ffmpeg", "-y", "-i", str(clip_path),
                    "-filter_complex", filter_complex,
                    "-map", "[lo]", "-f", "null", "-",
                    "-map", "[ro]", "-f", "null", "-",
                ],
                timeout=300,
            )
            if result.returncode != 0:
                return None
            times, left_values = parse_motion_metadata(left_motion)
            _, right_values = parse_motion_metadata(right_motion)
            timeline = build_speaker_timeline_from_motion(times, left_values, right_values)
            if len(timeline) < 2:
                return None

        return {
            "mode": "pan", "width": width, "height": height,
            "crop_w": crop_w, "crop_h": height,
            "x_expression": build_pan_expression(timeline, left_x, right_x),
            "timeline": timeline,
        }
    except Exception as exc:
        logger.warning("Speaker reframe planning failed: %s", exc)
        return None


def detect_auto_center_plan(clip_path: Path) -> Optional[Dict[str, Any]]:
    try:
        width, height = ffprobe_video_size(clip_path)
        if width / max(height, 1) <= 1.2:
            return None
        duration = ffprobe_duration(clip_path)
        if duration <= 2:
            return None
        crop_w = round_to_even(min(width, int(height * 9 / 16)))
        if crop_w >= width:
            return None
        timed_samples = _sample_face_trace(clip_path, 0, duration)
        if len(timed_samples) < 4:
            return None
        x_expression = _build_trace_x_expression(timed_samples, crop_w, width)
        if not x_expression:
            return None
        return {"crop_w": crop_w, "crop_h": height, "x_expression": x_expression}
    except Exception as exc:
        logger.warning("Auto-center plan failed: %s", exc)
        return None


def _sample_face_trace(
    video_path: Path, start_time: float, end_time: float,
) -> List[Tuple[float, int]]:
    cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        return []
    duration = end_time - start_time
    interval = max(0.5, duration / 20)
    samples = []
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
    t = start_time
    while t < end_time:
        capture.set(cv2.CAP_PROP_POS_MSEC, t * 1000)
        ok, frame = capture.read()
        if not ok or frame is None:
            t += interval
            continue
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=3, minSize=(30, 30))
        if len(faces) > 0:
            x, y, w, h = faces[0]
            samples.append((t, x + w // 2))
        t += interval
    capture.release()
    return samples


def _build_trace_x_expression(
    samples: List[Tuple[float, int]], crop_w: int, frame_width: int,
) -> str:
    if not samples:
        return ""
    clamped = []
    for t, cx in samples:
        x_offset = max(0, min(cx - crop_w // 2, frame_width - crop_w))
        x_offset = round_to_even(x_offset)
        clamped.append((t, x_offset))
    clamped.sort(key=lambda s: s[0])
    last_x = clamped[-1][1]
    expression = str(last_x)
    for t, x_offset in reversed(clamped[:-1]):
        expression = f"if(lt(t\\,{t:.4f})\\,{x_offset}\\,{expression})"
    return expression


def build_static_vertical_filter(input_path: Path, width: int, height: int) -> str:
    duration = ffprobe_duration(input_path)
    crop_x, crop_y, crop_w, crop_h = detect_optimal_crop_region(
        input_path, 0, min(duration, 12.0)
    )
    return f"crop={crop_w}:{crop_h}:{crop_x}:{crop_y},scale=1080:1920:flags=lanczos,setsar=1"


def render_reframed_clip_ffmpeg(
    input_path: Path, output_path: Path, output_format: str,
    ass_path: Optional[Path] = None, ass_fonts_dir: Optional[Path] = None,
) -> Tuple[bool, int, int]:
    from .ffmpeg_utils import ffmpeg_escape_filter_path, ffmpeg_escape_filter_value, run_ffmpeg_command, round_to_even

    width, height = ffprobe_video_size(input_path)
    if output_format == "original":
        import shutil
        shutil.copyfile(input_path, output_path)
        return True, round_to_even(width), round_to_even(height)

    plan = (
        detect_speaker_reframe_plan(input_path, output_format)
        if output_format in {"vertical_pan", "vertical_split"}
        else None
    )
    if not plan and output_format == "vertical":
        plan = detect_auto_center_plan(input_path)

    def _append_subtitles(filt: str) -> str:
        if not ass_path:
            return filt
        sub_filter = f"subtitles=filename={ffmpeg_escape_filter_path(ass_path)}"
        if ass_fonts_dir:
            sub_filter += f":fontsdir={ffmpeg_escape_filter_value(str(ass_fonts_dir))}"
        if filt.startswith("["):
            if filt.rstrip().endswith("[v]"):
                filt = filt.rstrip()[:-3]
            return filt + "," + sub_filter + ",setsar=1[v]"
        if filt.rstrip().endswith(",setsar=1"):
            filt = filt.rstrip()[:-len(",setsar=1")]
        return f"{filt},{sub_filter},setsar=1"

    if plan and "x_expression" in plan:
        video_filter = (
            f"crop={plan['crop_w']}:{plan['crop_h']}:x='{plan['x_expression']}':y=0,"
            "scale=1080:1920:flags=lanczos,setsar=1"
        )
        video_filter = _append_subtitles(video_filter)
    elif plan and plan["mode"] == "split":
        left = plan["regions"]["left"]
        right = plan["regions"]["right"]
        video_filter = _append_subtitles(
            f"[0:v]split=2[l][r];"
            f"[l]crop={left['tile_w']}:{left['tile_h']}:{left['tile_x']}:{left['tile_y']},"
            f"scale=1080:960:flags=lanczos,setsar=1[lv];"
            f"[r]crop={right['tile_w']}:{right['tile_h']}:{right['tile_x']}:{right['tile_y']},"
            f"scale=1080:960:flags=lanczos,setsar=1[rv];"
            "[lv][rv]vstack,setsar=1[v]"
        )
        command = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", str(input_path),
            "-filter_complex", video_filter, "-map", "[v]", "-map", "0:a?",
            "-c:v", "hevc_nvenc", "-preset", "p4", "-rc:v", "vbr",
            "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(output_path),
        ]
        return run_ffmpeg_command(command).returncode == 0, 1080, 1920
    elif output_format == "vertical_blur":
        video_filter = _append_subtitles(
            "[0:v]split=2[bg][fg];"
            "[bg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,boxblur=20:5[blurred];"
            "[fg]scale=1080:-2:force_original_aspect_ratio=decrease[scaled];"
            "[blurred][scaled]overlay=(W-w)/2:(H-h)/2[v]"
        )
        command = [
            "ffmpeg", "-y", "-hwaccel", "cuda", "-i", str(input_path),
            "-filter_complex", video_filter, "-map", "[v]", "-map", "0:a?",
            "-c:v", "hevc_nvenc", "-preset", "p4", "-rc:v", "vbr",
            "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(output_path),
        ]
        return run_ffmpeg_command(command).returncode == 0, 1080, 1920
    else:
        video_filter = build_static_vertical_filter(input_path, width, height)

    command = [
        "ffmpeg", "-y", "-hwaccel", "cuda", "-i", str(input_path),
        "-vf", video_filter,
        "-c:v", "hevc_nvenc", "-preset", "p4", "-rc:v", "vbr",
        "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output_path),
    ]
    return run_ffmpeg_command(command).returncode == 0, 1080, 1920


def burn_ass_subtitles_ffmpeg(
    input_path: Path, ass_path: Path, output_path: Path,
    fonts_dir: Optional[Path] = None,
) -> bool:
    from .ffmpeg_utils import ffmpeg_escape_filter_path, ffmpeg_escape_filter_value, run_ffmpeg_command

    subtitles_filter = f"subtitles=filename={ffmpeg_escape_filter_path(ass_path)}"
    if fonts_dir:
        subtitles_filter += f":fontsdir={ffmpeg_escape_filter_value(str(fonts_dir))}"
    video_filter = f"{subtitles_filter},setsar=1"
    command = [
        "ffmpeg", "-y", "-hwaccel", "cuda", "-i", str(input_path),
        "-vf", video_filter,
        "-c:v", "hevc_nvenc", "-preset", "p4", "-rc:v", "vbr",
        "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        str(output_path),
    ]
    return run_ffmpeg_command(command).returncode == 0
