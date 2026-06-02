"""
Basic FFmpeg/FFprobe wrappers and video processing helpers.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import logging
import subprocess
import re

logger = logging.getLogger(__name__)

VALID_OUTPUT_FORMATS = {"vertical", "vertical_pan", "vertical_split", "vertical_blur", "original"}
CLIP_END_SENTENCE_EXTENSION_SECONDS = 3.0
CLIP_END_PADDING_SECONDS = 0.35
SENTENCE_END_RE = re.compile(r"""[.!?]["')\]}]*$""")


def run_ffmpeg_command(command: List[str], timeout: int = 900) -> subprocess.CompletedProcess:
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        logger.error("Command failed: %s\n%s", " ".join(command), result.stderr[-4000:])
    return result


def ffprobe_has_audio(video_path: Path) -> bool:
    result = run_ffmpeg_command(
        [
            "ffprobe", "-v", "error", "-select_streams", "a:0",
            "-show_entries", "stream=codec_type", "-of", "csv=p=0",
            str(video_path),
        ],
        timeout=60,
    )
    return result.returncode == 0 and "audio" in result.stdout


def ffprobe_video_size(video_path: Path) -> Tuple[int, int]:
    result = run_ffmpeg_command(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height", "-of", "csv=s=x:p=0",
            str(video_path),
        ],
        timeout=60,
    )
    if result.returncode != 0 or "x" not in result.stdout:
        raise RuntimeError(f"Unable to read video size for {video_path}")
    width, height = result.stdout.strip().split("x", 1)
    return int(width), int(height)


def ffprobe_duration(video_path: Path) -> float:
    result = run_ffmpeg_command(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path),
        ],
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Unable to read duration for {video_path}")
    try:
        return max(0.0, float(result.stdout.strip()))
    except ValueError as exc:
        raise RuntimeError(f"Invalid duration for {video_path}") from exc


def ffmpeg_escape_filter_path(path: Path) -> str:
    return (
        str(path)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(" ", "\\ ")
    )


def ffmpeg_escape_filter_value(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace(" ", "\\ ")
    )


def round_to_even(value: int) -> int:
    return value - (value % 2)


def clamp_even(value: int, minimum: int, maximum: int) -> int:
    if maximum < minimum:
        return round_to_even(minimum)
    return round_to_even(max(minimum, min(value, maximum)))


def parse_timestamp_to_seconds(timestamp_str: str) -> float:
    try:
        timestamp_str = timestamp_str.strip()
        if ":" in timestamp_str:
            parts = timestamp_str.split(":")
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return float(timestamp_str)
    except (ValueError, IndexError) as e:
        logger.error(f"Failed to parse timestamp '{timestamp_str}': {e}")
        return 0.0


def seconds_to_mmss(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    minutes = total // 60
    secs = total % 60
    return f"{minutes:02d}:{secs:02d}"


def format_ms_to_timestamp(ms: int) -> str:
    seconds = ms // 1000
    minutes = seconds // 60
    seconds = seconds % 60
    return f"{minutes:02d}:{seconds:02d}"


def get_scaled_font_size(base_font_size: int, video_width: int) -> int:
    scaled_size = int(base_font_size * (video_width / 720))
    return max(24, min(120, scaled_size))


def get_subtitle_max_width(video_width: int) -> int:
    horizontal_padding = max(40, int(video_width * 0.06))
    return max(200, video_width - (horizontal_padding * 2))


def get_safe_vertical_position(
    video_height: int, text_height: int, position_y: float
) -> int:
    min_top_padding = max(40, int(video_height * 0.05))
    min_bottom_padding = max(120, int(video_height * 0.10))
    desired_y = int(video_height * position_y - text_height // 2)
    max_y = video_height - min_bottom_padding - text_height
    return max(min_top_padding, min(desired_y, max_y))


def resize_for_916_filter(target_width: int, target_height: int) -> str:
    return (
        f"scale={target_width}:{target_height}:force_original_aspect_ratio=increase:"
        f"flags=lanczos,crop={target_width}:{target_height},setsar=1"
    )


def get_available_transitions() -> List[str]:
    transitions_dir = Path(__file__).parent.parent / "transitions"
    if not transitions_dir.exists():
        logger.warning("Transitions directory not found")
        return []
    transition_files = [str(f) for f in transitions_dir.glob("*.mp4")]
    logger.info(f"Found {len(transition_files)} transition files")
    return transition_files


def count_scene_cuts(video_path: Path, threshold: float = 0.35) -> int:
    result = run_ffmpeg_command(
        [
            "ffmpeg", "-i", str(video_path),
            "-filter:v", f"select='gt(scene,{threshold})',showinfo",
            "-f", "null", "-",
        ],
        timeout=300,
    )
    if result.returncode != 0:
        return 0
    return len(re.findall(r"pts_time:", result.stderr))


def parse_motion_metadata(path: Path) -> Tuple[List[float], List[float]]:
    times: List[float] = []
    values: List[float] = []
    current_time: Optional[float] = None
    for line in path.read_text(errors="ignore").splitlines():
        time_match = re.search(r"pts_time:([0-9.]+)", line)
        if time_match:
            current_time = float(time_match.group(1))
            continue
        value_match = re.search(r"lavfi\.signalstats\.YAVG=([0-9.]+)", line)
        if value_match and current_time is not None:
            times.append(current_time)
            values.append(float(value_match.group(1)))
            current_time = None
    return times, values


def apply_transition_effect(
    clip1_path: Path, clip2_path: Path, transition_path: Path, output_path: Path
) -> bool:
    """Apply transition effect between two clips using a transition video."""
    try:
        clip1_duration = ffprobe_duration(clip1_path)
        clip2_duration = ffprobe_duration(clip2_path)
        transition_duration = min(1.5, clip1_duration, clip2_duration)
        if transition_duration <= 0:
            logger.warning("Transition duration is zero, skipping transition effect")
            return False

        width, height = ffprobe_video_size(clip2_path)
        clip1_tail_start = max(0.0, clip1_duration - transition_duration)
        filter_parts = [
            (
                f"[0:v]trim=start={clip1_tail_start:.3f}:end={clip1_duration:.3f},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos[v0]"
            ),
            (
                f"[1:v]trim=start=0:end={transition_duration:.3f},"
                f"setpts=PTS-STARTPTS,scale={width}:{height}:flags=lanczos[v1]"
            ),
            (
                f"[v0][v1]xfade=transition=fade:duration={transition_duration:.3f}:"
                "offset=0[vintro]"
            ),
        ]
        if clip2_duration - transition_duration > 0.05:
            filter_parts.extend(
                [
                    (
                        f"[1:v]trim=start={transition_duration:.3f}:end={clip2_duration:.3f},"
                        "setpts=PTS-STARTPTS[vrem]"
                    ),
                    "[vintro][vrem]concat=n=2:v=1:a=0[v]",
                ]
            )
            video_label = "[v]"
        else:
            video_label = "[vintro]"

        command = [
            "ffmpeg",
            "-y",
            "-hwaccel",
            "cuda",
            "-i",
            str(clip1_path),
            "-i",
            str(clip2_path),
            "-filter_complex",
            ";".join(filter_parts),
            "-map",
            video_label,
            "-map",
            "1:a?",
            "-c:v",
            "hevc_nvenc",
            "-preset",
            "p4",
            "-rc:v",
            "vbr",
            "-cq",
            "20",
            "-b:v",
            "0",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        success = run_ffmpeg_command(command).returncode == 0
        if success:
            logger.info("Applied transition effect: %s", output_path)
        return success

    except Exception as e:
        logger.error(f"Error applying transition effect: {e}")
        return False
