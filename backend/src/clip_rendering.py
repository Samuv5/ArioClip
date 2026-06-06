"""
Clip rendering orchestration: create, optimize, merge, split, add b-roll, transitions.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional, Callable
import logging
import uuid
import shutil
import subprocess
import tempfile
import json
import re

from .ffmpeg_utils import (
    run_ffmpeg_command,
    ffprobe_has_audio,
    ffprobe_video_size,
    ffprobe_duration,
    ffmpeg_escape_filter_path,
    ffmpeg_escape_filter_value,
    parse_timestamp_to_seconds,
    seconds_to_mmss,
    VALID_OUTPUT_FORMATS,
    get_available_transitions,
    apply_transition_effect,
)
from .subtitle_utils import (
    load_cached_transcript_data,
    get_words_in_range,
    get_absolute_words_in_range,
    build_transcript_ass_subtitles,
    extend_keep_ranges_to_sentence_boundary,
    ass_fonts_dir,
    cache_transcript_data,
    format_transcript_for_analysis,
)
from .face_detection import (
    render_reframed_clip_ffmpeg,
    detect_auto_center_plan,
    detect_speaker_reframe_plan,
)
from .config import get_config
from .transcriber import transcribe as whisperx_transcribe
from .clip_cleanup import DEFAULT_FILTERED_WORDS, clip_cleanup_enabled, normalize_clip_cleanup_settings
from .clip_source_map import normalize_source_ranges, save_clip_source_ranges
from .caption_templates import get_template, CAPTION_TEMPLATES
from .font_registry import FONTS_DIR, find_font_path, get_font_family_name

from .transcriber import transcribe as whisperx_transcribe

logger = logging.getLogger(__name__)


class VideoProcessor:
    def __init__(
        self,
        font_family: str = "THEBOLDFONT",
        font_size: int = 24,
        font_color: str = "#FFFFFF",
    ):
        self.font_family = font_family
        self.font_size = font_size
        self.font_color = font_color
        resolved_font = find_font_path(font_family, allow_all_user_fonts=True)
        if not resolved_font:
            resolved_font = find_font_path("TikTokSans-Regular")
        if not resolved_font:
            resolved_font = find_font_path("THEBOLDFONT")
        self.font_path = str(resolved_font) if resolved_font else ""

    def get_optimal_encoding_settings(
        self, target_quality: str = "high"
    ) -> Dict[str, Any]:
        settings = {
            "high": {
                "codec": "hevc_nvenc", "audio_codec": "aac", "audio_bitrate": "256k",
                "preset": "p6",
                "ffmpeg_params": [
                    "-rc:v", "vbr", "-cq", "18", "-b:v", "0",
                    "-pix_fmt", "yuv420p", "-movflags", "+faststart", "-sws_flags", "lanczos",
                ],
            },
            "medium": {
                "codec": "hevc_nvenc", "audio_codec": "aac", "audio_bitrate": "192k",
                "preset": "p4",
                "ffmpeg_params": [
                    "-rc:v", "vbr", "-cq", "23", "-b:v", "0", "-pix_fmt", "yuv420p",
                ],
            },
        }
        return settings.get(target_quality, settings["high"])


def get_video_transcript(video_path: Path, speech_model: str = "small") -> str:
    logger.info(f"Getting transcript for: {video_path} (model={speech_model})")
    try:
        transcript = whisperx_transcribe(video_path, speech_model)
        formatted_lines = format_transcript_for_analysis(transcript)
        cache_transcript_data(video_path, transcript)
        result = "\n".join(formatted_lines)
        logger.info(f"Transcript formatted: {len(formatted_lines)} segments, {len(result)} chars")
        return result
    except Exception as e:
        logger.error(f"Error in transcription: {e}")
        raise


def render_source_ranges_ffmpeg(
    video_path: Path,
    keep_ranges: List[Tuple[float, float]],
    output_path: Path,
) -> bool:
    keep_ranges = normalize_source_ranges(keep_ranges)
    if not keep_ranges:
        return False

    if len(keep_ranges) == 1:
        start, end = keep_ranges[0]
        command = [
            "ffmpeg", "-y", "-hwaccel", "cuda",
            "-ss", f"{start:.3f}", "-i", str(video_path),
            "-t", f"{end - start:.3f}",
            "-c:v", "hevc_nvenc", "-preset", "p2",
            "-rc:v", "vbr", "-cq", "18", "-b:v", "0",
            "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart", str(output_path),
        ]
        return run_ffmpeg_command(command).returncode == 0

    has_audio = ffprobe_has_audio(video_path)
    filter_parts: List[str] = []
    concat_inputs: List[str] = []
    for idx, (start, end) in enumerate(keep_ranges):
        filter_parts.append(
            f"[0:v]trim=start={start:.3f}:end={end:.3f},setpts=PTS-STARTPTS[v{idx}]"
        )
        concat_inputs.append(f"[v{idx}]")
        if has_audio:
            filter_parts.append(
                f"[0:a]atrim=start={start:.3f}:end={end:.3f},asetpts=PTS-STARTPTS[a{idx}]"
            )
            concat_inputs.append(f"[a{idx}]")

    if has_audio:
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(keep_ranges)}:v=1:a=1[v][a]")
        map_args = ["-map", "[v]", "-map", "[a]"]
    else:
        filter_parts.append(f"{''.join(concat_inputs)}concat=n={len(keep_ranges)}:v=1:a=0[v]")
        map_args = ["-map", "[v]"]

    command = [
        "ffmpeg", "-y", "-hwaccel", "cuda", "-i", str(video_path),
        "-filter_complex", ";".join(filter_parts),
        *map_args,
        "-c:v", "hevc_nvenc", "-preset", "p2",
        "-rc:v", "vbr", "-cq", "18", "-b:v", "0", "-pix_fmt", "yuv420p",
    ]
    if has_audio:
        command.extend(["-c:a", "aac", "-b:a", "192k"])
    command.extend(["-movflags", "+faststart", str(output_path)])
    return run_ffmpeg_command(command, timeout=1800).returncode == 0


def _normalize_cleanup_token(value: str) -> str:
    return re.sub(r"[^a-z0-9']+", "", value.lower())


def _build_cleanup_phrases(
    remove_filler_words: bool, filtered_words: Optional[List[str]]
) -> List[List[str]]:
    raw_phrases: List[str] = []
    if remove_filler_words:
        raw_phrases.extend(DEFAULT_FILTERED_WORDS)
    raw_phrases.extend(filtered_words or [])
    normalized_phrases: List[List[str]] = []
    seen: set[Tuple[str, ...]] = set()
    for phrase in raw_phrases:
        tokens = [
            _normalize_cleanup_token(part)
            for part in phrase.split()
            if _normalize_cleanup_token(part)
        ]
        if not tokens:
            continue
        key = tuple(tokens)
        if key in seen:
            continue
        seen.add(key)
        normalized_phrases.append(tokens)
    normalized_phrases.sort(key=len, reverse=True)
    return normalized_phrases


def _merge_intervals(intervals: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not intervals:
        return []
    merged: List[Tuple[float, float]] = []
    for start, end in sorted(intervals):
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
            continue
        merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    return merged


def build_clip_keep_ranges(
    video_path: Path,
    clip_start: float,
    clip_end: float,
    cleanup_settings: Optional[Dict[str, Any]] = None,
) -> List[Tuple[float, float]]:
    if clip_end <= clip_start:
        return []
    settings = cleanup_settings or {}
    if not clip_cleanup_enabled(settings):
        return [(clip_start, clip_end)]
    transcript_data = load_cached_transcript_data(video_path)
    if not transcript_data or not transcript_data.get("words"):
        return [(clip_start, clip_end)]
    relevant_words = get_absolute_words_in_range(transcript_data, clip_start, clip_end)
    if not relevant_words:
        return [(clip_start, clip_end)]

    removal_intervals: List[Tuple[float, float]] = []
    pause_threshold_seconds = max(0.25, float(settings.get("pause_threshold_ms", 900)) / 1000.0)
    cut_long_pauses = bool(settings.get("cut_long_pauses"))

    if cut_long_pauses:
        leading_gap = relevant_words[0]["start"] - clip_start
        if leading_gap >= pause_threshold_seconds:
            removal_intervals.append((clip_start, relevant_words[0]["start"]))
        for current, nxt in zip(relevant_words, relevant_words[1:]):
            gap = nxt["start"] - current["end"]
            if gap >= pause_threshold_seconds:
                removal_intervals.append((current["end"], nxt["start"]))
        trailing_gap = clip_end - relevant_words[-1]["end"]
        if trailing_gap >= pause_threshold_seconds:
            removal_intervals.append((relevant_words[-1]["end"], clip_end))

    phrase_tokens = _build_cleanup_phrases(
        bool(settings.get("remove_filler_words")),
        settings.get("filtered_words"),
    )
    if phrase_tokens:
        normalized_words = [
            _normalize_cleanup_token(word["text"]) for word in relevant_words
        ]
        idx = 0
        while idx < len(relevant_words):
            matched_length = 0
            for phrase in phrase_tokens:
                end_idx = idx + len(phrase)
                if end_idx > len(normalized_words):
                    continue
                if normalized_words[idx:end_idx] == phrase:
                    matched_length = len(phrase)
                    break
            if matched_length:
                removal_intervals.append((
                    relevant_words[idx]["start"],
                    relevant_words[idx + matched_length - 1]["end"],
                ))
                idx += matched_length
                continue
            idx += 1

    merged_removals = _merge_intervals(removal_intervals)
    if not merged_removals:
        return [(clip_start, clip_end)]

    keep_ranges: List[Tuple[float, float]] = []
    cursor = clip_start
    for removal_start, removal_end in merged_removals:
        if removal_start - cursor >= 0.12:
            keep_ranges.append((cursor, removal_start))
        cursor = max(cursor, removal_end)
    if clip_end - cursor >= 0.12:
        keep_ranges.append((cursor, clip_end))

    total_kept = sum(max(0.0, end - start) for start, end in keep_ranges)
    if not keep_ranges or total_kept < 0.5:
        return [(clip_start, clip_end)]
    return keep_ranges


def build_keep_ranges_from_source_ranges(
    video_path: Path,
    source_ranges: List[Tuple[float, float]],
    cleanup_settings: Optional[Dict[str, Any]] = None,
) -> List[Tuple[float, float]]:
    normalized_ranges = normalize_source_ranges(source_ranges)
    if not normalized_ranges:
        return []
    keep_ranges: List[Tuple[float, float]] = []
    for range_start, range_end in normalized_ranges:
        keep_ranges.extend(build_clip_keep_ranges(video_path, range_start, range_end, cleanup_settings))
    return normalize_source_ranges(keep_ranges)


def create_optimized_clip(
    video_path: Path,
    start_time: float,
    end_time: float,
    output_path: Path,
    add_subtitles: bool = True,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    output_format: str = "vertical",
    keep_ranges: Optional[List[Tuple[float, float]]] = None,
) -> bool:
    try:
        if keep_ranges:
            effective_keep_ranges = normalize_source_ranges(keep_ranges)
        else:
            effective_keep_ranges = [
                (max(start_time, start), min(end_time, end))
                for start, end in [(start_time, end_time)]
                if min(end_time, end) - max(start_time, start) > 0.05
            ]
        effective_keep_ranges = extend_keep_ranges_to_sentence_boundary(
            video_path, effective_keep_ranges,
        )
        duration = sum(end - start for start, end in effective_keep_ranges)
        if duration <= 0:
            logger.error(f"Invalid clip duration: {duration:.1f}s")
            return False

        keep_original = output_format == "original"
        logger.info(
            f"Creating clip: {start_time:.1f}s - {end_time:.1f}s ({duration:.1f}s) "
            f"subtitles={add_subtitles} template '{caption_template}' format={'original' if keep_original else 'vertical'}"
        )

        if not add_subtitles and keep_original and len(effective_keep_ranges) == 1:
            fast_path_start, fast_path_end = effective_keep_ranges[0]
            result = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-ss", str(fast_path_start), "-i", str(video_path),
                    "-t", str(fast_path_end - fast_path_start),
                    "-c", "copy", "-movflags", "+faststart",
                    str(output_path),
                ],
                capture_output=True, text=True, timeout=300,
            )
            if result.returncode != 0:
                logger.error(f"ffmpeg stream copy failed: {result.stderr}")
                return False
            logger.info(f"Successfully created clip (stream copy): {output_path}")
            return True

        with tempfile.TemporaryDirectory(prefix="supoclip_render_") as temp_dir:
            temp_root = Path(temp_dir)
            source_clip_path = temp_root / "source.mp4"
            framed_clip_path = temp_root / "framed.mp4"
            ass_path = temp_root / "captions.ass"

            if not render_source_ranges_ffmpeg(video_path, effective_keep_ranges, source_clip_path):
                raise RuntimeError("ffmpeg source-range render failed")

            reframe_format = output_format if output_format in VALID_OUTPUT_FORMATS else "vertical"
            ass_fonts_path = (
                ass_fonts_dir(font_family or get_template(caption_template)["font_family"])
                if add_subtitles else None
            )

            ass_path_actual = (
                ass_path
                if add_subtitles and build_transcript_ass_subtitles(
                    video_path, start_time, end_time,
                    1080, 1920, ass_path,
                    font_family, font_size, font_color, caption_template,
                    effective_keep_ranges,
                )
                else None
            )

            framed_ok, target_width, target_height = render_reframed_clip_ffmpeg(
                source_clip_path, framed_clip_path, reframe_format,
                ass_path=ass_path_actual, ass_fonts_dir=ass_fonts_path,
            )
            if not framed_ok:
                raise RuntimeError("ffmpeg reframe render failed")

            shutil.move(str(framed_clip_path), str(output_path))
            logger.info(f"Successfully created clip with ffmpeg: {output_path}")
            return True

    except Exception as e:
        logger.error(f"Failed to create clip: {e}")
        return False


def create_clips_from_segments(
    video_path: Path,
    segments: List[Dict[str, Any]],
    output_dir: Path,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    output_format: str = "vertical",
    add_subtitles: bool = True,
    cleanup_settings: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    logger.info(
        f"Creating {len(segments)} clips subtitles={add_subtitles} template '{caption_template}'"
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    clips_info = []

    for i, segment in enumerate(segments):
        try:
            logger.info(
                f"Processing segment {i + 1}: start='{segment.get('start_time')}', end='{segment.get('end_time')}'"
            )
            provided_keep_ranges = normalize_source_ranges(segment.get("keep_ranges"))
            provided_source_ranges = normalize_source_ranges(segment.get("source_ranges"))
            if provided_keep_ranges:
                start_seconds = provided_keep_ranges[0][0]
                end_seconds = provided_keep_ranges[-1][1]
            elif provided_source_ranges:
                start_seconds = provided_source_ranges[0][0]
                end_seconds = provided_source_ranges[-1][1]
            else:
                start_seconds = parse_timestamp_to_seconds(segment["start_time"])
                end_seconds = parse_timestamp_to_seconds(segment["end_time"])

            duration = end_seconds - start_seconds
            if duration <= 0:
                logger.warning(f"Skipping clip {i + 1}: invalid duration {duration:.1f}s")
                continue

            clip_filename = (
                f"clip_{i + 1}_{segment['start_time'].replace(':', '')}-"
                f"{segment['end_time'].replace(':', '')}_{uuid.uuid4().hex[:12]}.mp4"
            )
            clip_path = output_dir / clip_filename

            if provided_keep_ranges:
                keep_ranges = provided_keep_ranges
            elif provided_source_ranges:
                keep_ranges = build_keep_ranges_from_source_ranges(video_path, provided_source_ranges, cleanup_settings)
            else:
                keep_ranges = build_clip_keep_ranges(video_path, start_seconds, end_seconds, cleanup_settings)
            keep_ranges = extend_keep_ranges_to_sentence_boundary(video_path, keep_ranges)

            success = create_optimized_clip(
                video_path, start_seconds, end_seconds, clip_path,
                add_subtitles, font_family, font_size, font_color,
                caption_template, output_format, keep_ranges,
            )

            if success:
                save_clip_source_ranges(clip_path, keep_ranges)
                cleaned_duration = sum(end - start for start, end in keep_ranges)
                clip_info = {
                    "clip_id": i + 1, "filename": clip_filename,
                    "path": str(clip_path),
                    "start_time": segment["start_time"], "end_time": segment["end_time"],
                    "duration": cleaned_duration,
                    "text": segment["text"],
                    "relevance_score": segment["relevance_score"],
                    "reasoning": segment["reasoning"],
                    "virality_score": segment.get("virality_score", 0),
                    "hook_score": segment.get("hook_score", 0),
                    "engagement_score": segment.get("engagement_score", 0),
                    "value_score": segment.get("value_score", 0),
                    "shareability_score": segment.get("shareability_score", 0),
                    "hook_type": segment.get("hook_type"),
                    "keep_ranges": keep_ranges,
                }
                clips_info.append(clip_info)
                logger.info(f"Created clip {i + 1}: {cleaned_duration:.1f}s")
            else:
                logger.error(f"Failed to create clip {i + 1}")

        except Exception as e:
            logger.error(f"Error processing clip {i + 1}: {e}")

    logger.info(f"Successfully created {len(clips_info)}/{len(segments)} clips")
    return clips_info


def create_clips_with_transitions(
    video_path: Path,
    segments: List[Dict[str, Any]],
    output_dir: Path,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    output_format: str = "vertical",
    add_subtitles: bool = True,
    cleanup_settings: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    logger.info(
        f"Creating {len(segments)} standalone clips subtitles={add_subtitles} template '{caption_template}'"
    )
    return create_clips_from_segments(
        video_path, segments, output_dir,
        font_family, font_size, font_color, caption_template,
        output_format, add_subtitles, cleanup_settings,
    )


def detect_audio_peak_times(video_path: Path, max_peaks: int = 8) -> List[float]:
    result = run_ffmpeg_command(
        [
            "ffmpeg", "-i", str(video_path), "-vn",
            "-af", "astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level",
            "-f", "null", "-",
        ],
        timeout=600,
    )
    if result.returncode != 0:
        return []
    current_time: Optional[float] = None
    samples: List[Tuple[float, float]] = []
    for line in result.stderr.splitlines():
        time_match = re.search(r"pts_time:([0-9.]+)", line)
        if time_match:
            current_time = float(time_match.group(1))
            continue
        rms_match = re.search(r"lavfi\.astats\.Overall\.RMS_level=([-0-9.]+)", line)
        if rms_match and current_time is not None:
            try:
                samples.append((current_time, float(rms_match.group(1))))
            except ValueError:
                pass
            current_time = None
    if not samples:
        return []
    samples.sort(key=lambda item: item[1], reverse=True)
    peaks: List[float] = []
    for timestamp, _ in samples:
        if all(abs(timestamp - existing) >= 4.0 for existing in peaks):
            peaks.append(timestamp)
        if len(peaks) >= max_peaks:
            break
    return sorted(peaks)


def build_clip_signal_summary(video_path: Path, transcript: str) -> str:
    from .subtitle_utils import parse_transcript_lines

    transcript_lines = parse_transcript_lines(transcript)
    if not transcript_lines:
        return ""

    trigger_pattern = re.compile(
        r"\b(wait|what|no way|seriously|actually|but|however|because|mistake|secret|"
        r"wild|crazy|insane|never|always|nobody|everybody|why|how|haha|laugh|lol|damn|"
        r"shit|fuck)\b", re.IGNORECASE,
    )
    candidates: List[Tuple[float, Dict[str, Any], str]] = []
    audio_peaks = detect_audio_peak_times(video_path)

    for idx, line in enumerate(transcript_lines):
        text = line["text"]
        score = 0.0
        reasons: List[str] = []
        if trigger_pattern.search(text):
            score += 2.0; reasons.append("trigger phrase")
        if "?" in text:
            score += 1.5; reasons.append("question/hook")
        if "!" in text:
            score += 1.0; reasons.append("emphatic delivery")
        if re.search(r"\b(I|we)\s+(thought|realized|found|learned|made|lost|won)\b", text, re.I):
            score += 1.0; reasons.append("story turn")
        if len(text.split()) <= 8:
            score += 0.5; reasons.append("short punchy line")

        previous_line = transcript_lines[idx - 1] if idx > 0 else None
        next_line = transcript_lines[idx + 1] if idx + 1 < len(transcript_lines) else None
        if previous_line and line["start"] - previous_line["end"] >= 1.0:
            score += 1.0; reasons.append("pause before line")
        if previous_line and previous_line.get("speaker") and line.get("speaker"):
            if previous_line["speaker"] != line["speaker"] and line["end"] - line["start"] <= 6:
                score += 1.25; reasons.append("rapid speaker turn")
        if next_line and next_line.get("speaker") and line.get("speaker"):
            if next_line["speaker"] != line["speaker"] and next_line["end"] - line["start"] <= 10:
                score += 1.0; reasons.append("back-and-forth")
        if any(line["start"] <= peak <= line["end"] for peak in audio_peaks):
            score += 1.25; reasons.append("audio energy peak")

        if score > 0:
            candidates.append((score, line, ", ".join(reasons)))

    candidates.sort(key=lambda item: item[0], reverse=True)
    summary_lines = ["Deterministic clip-worthiness signals to consider before ranking:"]
    for score, line, reason in candidates[:12]:
        summary_lines.append(
            f"- [{line['start_label']} - {line['end_label']}] score={score:.1f}: {reason}; {line['text']}"
        )
    return "\n".join(summary_lines)


def insert_broll_into_clip(
    main_clip_path: Path, broll_path: Path, insert_time: float, broll_duration: float,
    output_path: Path, transition_duration: float = 0.3,
) -> bool:
    try:
        main_duration = ffprobe_duration(main_clip_path)
        source_broll_duration = ffprobe_duration(broll_path)
        target_width, target_height = ffprobe_video_size(main_clip_path)
        insert_time = max(0.0, min(insert_time, max(0.0, main_duration - 0.5)))
        actual_broll_duration = min(
            max(0.0, broll_duration), source_broll_duration,
            max(0.0, main_duration - insert_time),
        )
        if actual_broll_duration <= 0.05:
            return False
        broll_end_time = insert_time + actual_broll_duration
        fade_duration = min(max(0.0, transition_duration), max(0.0, actual_broll_duration / 3))
        filter_parts: List[str] = []
        concat_labels: List[str] = []
        segment_count = 0
        if insert_time > 0.05:
            filter_parts.append(f"[0:v]trim=start=0:end={insert_time:.3f},setpts=PTS-STARTPTS[vpre]")
            concat_labels.append("[vpre]"); segment_count += 1
        broll_filter = (
            f"[1:v]trim=start=0:end={actual_broll_duration:.3f},setpts=PTS-STARTPTS,"
            f"{resize_for_916_filter(target_width, target_height)}"
        )
        if fade_duration > 0:
            broll_filter += (
                f",fade=t=in:st=0:d={fade_duration:.3f},"
                f"fade=t=out:st={max(0.0, actual_broll_duration - fade_duration):.3f}:d={fade_duration:.3f}"
            )
        filter_parts.append(f"{broll_filter}[vbroll]")
        concat_labels.append("[vbroll]"); segment_count += 1
        if main_duration - broll_end_time > 0.05:
            filter_parts.append(
                f"[0:v]trim=start={broll_end_time:.3f}:end={main_duration:.3f},setpts=PTS-STARTPTS[vpost]"
            )
            concat_labels.append("[vpost]"); segment_count += 1
        if segment_count > 1:
            filter_parts.append(f"{''.join(concat_labels)}concat=n={segment_count}:v=1:a=0[v]")
            video_label = "[v]"
        else:
            video_label = concat_labels[0]

        command = [
            "ffmpeg", "-y", "-hwaccel", "cuda",
            "-i", str(main_clip_path), "-i", str(broll_path),
            "-filter_complex", ";".join(filter_parts),
            "-map", video_label, "-map", "0:a?",
            "-c:v", "hevc_nvenc", "-preset", "p4",
            "-rc:v", "vbr", "-cq", "20", "-b:v", "0", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            str(output_path),
        ]
        return run_ffmpeg_command(command).returncode == 0
    except Exception as e:
        logger.error(f"Error inserting B-roll: {e}")
        return False


def apply_broll_to_clip(
    clip_path: Path, broll_suggestions: List[Dict[str, Any]], output_path: Path
) -> bool:
    if not broll_suggestions:
        return False
    try:
        sorted_suggestions = sorted(broll_suggestions, key=lambda x: x.get("timestamp", 0), reverse=True)
        current_clip_path = clip_path
        temp_paths = []
        for i, suggestion in enumerate(sorted_suggestions):
            broll_path = suggestion.get("local_path")
            if not broll_path or not Path(broll_path).exists():
                continue
            timestamp = suggestion.get("timestamp", 0)
            duration = suggestion.get("duration", 3.0)
            temp_output = output_path.parent / f"temp_broll_{i}.mp4" if i < len(sorted_suggestions) - 1 else output_path
            temp_paths.append(temp_output)
            success = insert_broll_into_clip(current_clip_path, Path(broll_path), timestamp, duration, temp_output)
            if success:
                current_clip_path = temp_output
        for temp_path in temp_paths:
            if temp_path.exists() and temp_path != output_path:
                try: temp_path.unlink()
                except Exception: pass
        return True
    except Exception as e:
        logger.error(f"Error applying B-roll to clip: {e}")
        return False


# Backward compatibility
def get_video_transcript_with_assemblyai(path: Path) -> str:
    return get_video_transcript(path)


def create_9_16_clip(
    video_path: Path, start_time: float, end_time: float,
    output_path: Path, subtitle_text: str = "",
) -> bool:
    return create_optimized_clip(
        video_path, start_time, end_time, output_path, add_subtitles=bool(subtitle_text),
    )
