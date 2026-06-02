"""
ASS subtitle generation and transcript word query utilities.
"""

from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import logging
import json
import re

from .ffmpeg_utils import (
    ffprobe_duration,
    format_ms_to_timestamp,
    get_scaled_font_size,
    SENTENCE_END_RE,
    CLIP_END_SENTENCE_EXTENSION_SECONDS,
    CLIP_END_PADDING_SECONDS,
)
from .font_registry import FONTS_DIR, find_font_path, get_font_family_name
from .caption_templates import get_template

logger = logging.getLogger(__name__)

TRANSCRIPT_CACHE_SCHEMA_VERSION = 2


def ass_timestamp(seconds: float) -> str:
    seconds = max(0.0, seconds)
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds - (hours * 3600) - (minutes * 60)
    return f"{hours}:{minutes:02d}:{secs:05.2f}"


def hex_to_ass_color(
    value: Optional[str], fallback: str = "#FFFFFF", include_alpha: bool = True
) -> str:
    value = (value or fallback).strip()
    if value.startswith("#"):
        value = value[1:]
    alpha = 0
    if len(value) == 8:
        css_alpha = int(value[6:8], 16)
        alpha = 255 - css_alpha
        value = value[:6]
    if len(value) != 6:
        value = fallback.lstrip("#")
        if len(value) == 8:
            css_alpha = int(value[6:8], 16)
            alpha = 255 - css_alpha
            value = value[:6]
    red, green, blue = value[0:2], value[2:4], value[4:6]
    alpha_part = f"{alpha:02X}" if include_alpha else "00"
    return f"&H{alpha_part}{blue}{green}{red}&"


def escape_ass_text(value: str) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("{", "\\{")
        .replace("}", "\\}")
        .replace("\n", " ")
        .strip()
    )


def ass_font_name(font_family: str) -> str:
    font_path = find_font_path(font_family, allow_all_user_fonts=True)
    if font_path:
        return get_font_family_name(Path(font_path)) or Path(font_path).stem
    return font_family or "Arial"


def ass_fonts_dir(font_family: str) -> Optional[Path]:
    font_path = find_font_path(font_family, allow_all_user_fonts=True)
    if font_path:
        return font_path.parent
    return FONTS_DIR if FONTS_DIR.exists() else None


def word_ends_sentence(text: str) -> bool:
    return bool(SENTENCE_END_RE.search((text or "").strip()))


def cache_transcript_data(video_path: Path, transcript) -> None:
    cache_path = video_path.with_suffix(".transcript_cache.json")
    words_data = []
    if transcript.words:
        words_data = [_serialize_transcript_word(word) for word in transcript.words]
    utterances_data = []
    if getattr(transcript, "utterances", None):
        utterances_data = [
            {
                "text": utterance.text,
                "start": utterance.start,
                "end": utterance.end,
                "speaker": getattr(utterance, "speaker", None),
                "words": [
                    _serialize_transcript_word(word)
                    for word in getattr(utterance, "words", []) or []
                ],
            }
            for utterance in transcript.utterances
        ]
    cache_data = {
        "version": TRANSCRIPT_CACHE_SCHEMA_VERSION,
        "words": words_data,
        "utterances": utterances_data,
        "text": transcript.text,
    }
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)
    logger.info(f"Cached {len(words_data)} words to {cache_path}")


def load_cached_transcript_data(video_path: Path) -> Optional[Dict]:
    cache_path = video_path.with_suffix(".transcript_cache.json")
    if not cache_path.exists():
        return None
    try:
        with open(cache_path, "r") as f:
            payload = json.load(f)
            if "version" not in payload:
                payload["version"] = TRANSCRIPT_CACHE_SCHEMA_VERSION
                payload.setdefault("utterances", [])
            return payload
    except Exception as e:
        logger.warning(f"Failed to load transcript cache: {e}")
        return None


def _serialize_transcript_word(word) -> Dict[str, Any]:
    return {
        "text": word.text,
        "start": word.start,
        "end": word.end,
        "confidence": word.confidence if hasattr(word, "confidence") else 1.0,
        "speaker": getattr(word, "speaker", None),
    }


def get_words_in_range(
    transcript_data: Dict, clip_start: float, clip_end: float
) -> List[Dict]:
    if not transcript_data or not transcript_data.get("words"):
        return []
    clip_start_ms = int(clip_start * 1000)
    clip_end_ms = int(clip_end * 1000)
    relevant_words = []
    for word_data in transcript_data["words"]:
        word_start = word_data["start"]
        word_end = word_data["end"]
        if word_start < clip_end_ms and word_end > clip_start_ms:
            relative_start = max(0, (word_start - clip_start_ms) / 1000.0)
            relative_end = min(
                (clip_end_ms - clip_start_ms) / 1000.0,
                (word_end - clip_start_ms) / 1000.0,
            )
            if relative_end > relative_start:
                relevant_words.append({
                    "text": word_data["text"],
                    "start": relative_start,
                    "end": relative_end,
                    "confidence": word_data.get("confidence", 1.0),
                })
    return relevant_words


def get_absolute_words_in_range(
    transcript_data: Dict, clip_start: float, clip_end: float
) -> List[Dict[str, Any]]:
    if not transcript_data or not transcript_data.get("words"):
        return []
    clip_start_ms = int(clip_start * 1000)
    clip_end_ms = int(clip_end * 1000)
    relevant_words: List[Dict[str, Any]] = []
    for word_data in transcript_data["words"]:
        word_start = int(word_data["start"])
        word_end = int(word_data["end"])
        overlap_start = max(word_start, clip_start_ms)
        overlap_end = min(word_end, clip_end_ms)
        if overlap_end <= overlap_start:
            continue
        relevant_words.append({
            "text": word_data["text"],
            "start": overlap_start / 1000.0,
            "end": overlap_end / 1000.0,
            "confidence": word_data.get("confidence", 1.0),
        })
    return relevant_words


def get_words_for_keep_ranges(
    transcript_data: Dict, keep_ranges: List[Tuple[float, float]]
) -> List[Dict[str, Any]]:
    if not transcript_data or not transcript_data.get("words") or not keep_ranges:
        return []
    relevant_words: List[Dict[str, Any]] = []
    timeline_offset = 0.0
    for keep_start, keep_end in keep_ranges:
        range_words = get_absolute_words_in_range(transcript_data, keep_start, keep_end)
        for word in range_words:
            relevant_words.append({
                "text": word["text"],
                "start": timeline_offset + (word["start"] - keep_start),
                "end": timeline_offset + (word["end"] - keep_start),
                "confidence": word.get("confidence", 1.0),
            })
        timeline_offset += keep_end - keep_start
    return relevant_words


def extend_keep_ranges_to_sentence_boundary(
    video_path: Path,
    keep_ranges: List[Tuple[float, float]],
    max_extension_seconds: float = CLIP_END_SENTENCE_EXTENSION_SECONDS,
    padding_seconds: float = CLIP_END_PADDING_SECONDS,
) -> List[Tuple[float, float]]:
    from .clip_source_map import normalize_source_ranges
    normalized = normalize_source_ranges(keep_ranges)
    if not normalized:
        return []
    last_start, last_end = normalized[-1]
    transcript_data = load_cached_transcript_data(video_path)
    if not transcript_data or not transcript_data.get("words"):
        return normalized
    try:
        source_duration = ffprobe_duration(video_path)
    except Exception:
        source_duration = None
    cap_end = last_end + max(0.0, max_extension_seconds)
    if source_duration is not None:
        cap_end = min(cap_end, source_duration)
    if cap_end <= last_end:
        return normalized
    nearby_words = get_absolute_words_in_range(
        transcript_data, max(0.0, last_end - 6.0), cap_end,
    )
    if not nearby_words:
        return normalized
    boundary_words = [
        word for word in nearby_words if float(word["start"]) <= last_end + 0.05
    ]
    last_boundary_word = boundary_words[-1] if boundary_words else None
    if (
        last_boundary_word
        and float(last_boundary_word["end"]) <= last_end + 0.05
        and word_ends_sentence(str(last_boundary_word.get("text", "")))
    ):
        return normalized
    extended_end = last_end
    for word in nearby_words:
        word_end = float(word["end"])
        if word_end <= last_end + 0.05:
            continue
        extended_end = max(extended_end, word_end)
        if word_ends_sentence(str(word.get("text", ""))):
            extended_end += max(0.0, padding_seconds)
            break
    if extended_end <= last_end:
        return normalized
    if source_duration is not None:
        extended_end = min(extended_end, source_duration)
    extended_end = min(extended_end, cap_end + max(0.0, padding_seconds))
    if extended_end - last_start <= 0.05:
        return normalized
    return [*normalized[:-1], (last_start, extended_end)]


def _animation_speed_ms(speed: float, base_ms: int) -> int:
    return max(50, int(base_ms / max(0.1, speed)))


def _resolve_position(
    template: dict,
    video_height: int,
    subtitle_y: Optional[int] = None,
) -> int:
    from .caption_templates import POSITION_Y_MAP
    position_name = template.get("position", "bottom")
    pos_y = float(template.get("position_y", 0.75))
    if position_name in POSITION_Y_MAP and subtitle_y is None:
        pos_y = POSITION_Y_MAP[position_name]
    if subtitle_y is not None:
        return int(video_height * (100 - subtitle_y) / 100)
    return int(video_height * pos_y)


CHUNK_SIZES: dict[str, int] = {
    "none": 4,
    "fade": 4,
    "pop": 3,
    "karaoke": 3,
    "slide_up": 5,
    "slide_down": 5,
    "slide_left": 5,
    "slide_right": 5,
    "typewriter": 6,
    "scale_in": 3,
    "reveal": 4,
    "bounce": 3,
}


def build_transcript_ass_subtitles(
    video_path: Path,
    clip_start: float,
    clip_end: float,
    video_width: int,
    video_height: int,
    output_ass_path: Path,
    font_family: str = "THEBOLDFONT",
    font_size: int = 24,
    font_color: str = "#FFFFFF",
    caption_template: str = "default",
    keep_ranges: Optional[List[Tuple[float, float]]] = None,
    subtitle_y: Optional[int] = None,
) -> bool:
    transcript_data = load_cached_transcript_data(video_path)
    if not transcript_data or not transcript_data.get("words"):
        logger.warning("No cached transcript data available for ASS subtitles")
        return False

    template = get_template(caption_template)
    effective_font_family = font_family or template["font_family"]
    effective_font_size = int(template["font_size"]) if font_size <= 0 else int(font_size)
    effective_font_color = font_color or template["font_color"]
    animation = template.get("animation", "none")

    if keep_ranges:
        relevant_words = get_words_for_keep_ranges(transcript_data, keep_ranges)
    else:
        relevant_words = get_words_in_range(transcript_data, clip_start, clip_end)
    if not relevant_words:
        logger.warning("No words found in clip timerange for ASS subtitles")
        return False

    chunk_size = CHUNK_SIZES.get(animation, 4)
    if caption_template == "minimal":
        chunk_size = 6
    if animation in {"typewriter", "bounce"}:
        chunk_size = max(3, chunk_size)

    primary = hex_to_ass_color(effective_font_color)
    highlight = hex_to_ass_color(template.get("highlight_color"), "#FFD700")
    outline = hex_to_ass_color(template.get("stroke_color") or "#000000", "#000000")
    back_color = hex_to_ass_color(template.get("background_color"), "#00000080")
    font_px = get_scaled_font_size(effective_font_size, video_width)
    outline_px = int(template.get("stroke_width", 2) or 0)
    anim_speed = float(template.get("animation_speed", 1.0))
    uppercase = bool(template.get("uppercase", False))

    stroke_color_hex = template.get("stroke_color") or "#000000"
    shadow_enabled = template.get("shadow", False)
    if shadow_enabled:
        shadow_px = int(template.get("shadow_offset_x", 2))
    else:
        shadow_px = 0

    letter_spacing = int(template.get("letter_spacing", 0))
    y_pos = _resolve_position(template, video_height, subtitle_y)
    margin = int(video_width * 0.06)
    font_name = ass_font_name(effective_font_family)
    bg = template.get("background") and template.get("background_color")
    border_style = 3 if bg else 1

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {video_width}
PlayResY: {video_height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_px},{primary},&H000000FF,{outline},{back_color},1,0,0,0,100,100,{letter_spacing},0,{border_style},{outline_px},{shadow_px},5,{margin},{margin},{margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""

    events: List[str] = []
    cx = video_width // 2

    def _word_text(w: dict) -> str:
        t = escape_ass_text(w["text"])
        return t.upper() if uppercase else t

    for chunk_start in range(0, len(relevant_words), chunk_size):
        chunk = relevant_words[chunk_start : chunk_start + chunk_size]
        chunk_end = float(chunk[-1]["end"])
        chunk_text = " ".join(_word_text(w) for w in chunk)
        base_prefix = f"{{\\pos({cx},{y_pos})}}"

        # --- karaoke (word-by-word highlight) ---
        if animation == "karaoke":
            for idx, word in enumerate(chunk):
                w_start = float(word["start"])
                w_end = float(chunk[idx + 1]["start"]) if idx + 1 < len(chunk) else chunk_end
                if w_end <= w_start:
                    w_end = w_start + 0.05
                parts = []
                for p_idx, p_word in enumerate(chunk):
                    txt = _word_text(p_word)
                    if p_idx == idx:
                        parts.append(f"{{\\c{highlight}}}{txt}{{\\c{primary}}}")
                    else:
                        parts.append(txt)
                line = " ".join(parts)
                events.append(
                    f"Dialogue: 0,{ass_timestamp(w_start)},{ass_timestamp(w_end)},Default,,0,0,0,,{base_prefix}{line}"
                )

        # --- typewriter (word fades in + scale pop) ---
        elif animation == "typewriter":
            for idx, word in enumerate(chunk):
                w_start = float(word["start"])
                w_end = float(chunk[idx + 1]["start"]) if idx + 1 < len(chunk) else chunk_end
                if w_end <= w_start:
                    w_end = w_start + 0.3
                txt = _word_text(word)
                fade_ms = _animation_speed_ms(anim_speed, 120)
                effect = (
                    f"{{\\pos({cx},{y_pos})}}"
                    f"{{\\alpha&HFF&\\t(0,{fade_ms},\\alpha&H00&)}}"
                    f"{{\\fscx130\\fscy130\\t(0,{fade_ms},\\fscx100\\fscy100)}}"
                )
                events.append(
                    f"Dialogue: 0,{ass_timestamp(w_start)},{ass_timestamp(w_end)},Default,,0,0,0,,{effect}{txt}"
                )

        # --- slide animations ---
        elif animation == "slide_up":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            from_y = y_pos + int(video_height * 0.04)
            fade_in = _animation_speed_ms(anim_speed, 120)
            dur = int((end - start) * 1000)
            move_dur = min(_animation_speed_ms(anim_speed, 350), int(dur * 0.6))
            effect = (
                f"{{\\move({cx},{from_y},{cx},{y_pos},0,{move_dur})}}"
                f"{{\\fad({fade_in},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{effect}{chunk_text}"
            )

        elif animation == "slide_down":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            from_y = y_pos - int(video_height * 0.04)
            fade_in = _animation_speed_ms(anim_speed, 120)
            dur = int((end - start) * 1000)
            move_dur = min(_animation_speed_ms(anim_speed, 350), int(dur * 0.6))
            effect = (
                f"{{\\move({cx},{from_y},{cx},{y_pos},0,{move_dur})}}"
                f"{{\\fad({fade_in},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{effect}{chunk_text}"
            )

        elif animation == "slide_left":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            from_x = video_width + int(video_width * 0.05)
            move_ms = _animation_speed_ms(anim_speed, 300)
            fade_in = _animation_speed_ms(anim_speed, 80)
            effect = (
                f"{{\\move({from_x},{y_pos},{cx},{y_pos},0,{move_ms})}}"
                f"{{\\fad({fade_in},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{effect}{chunk_text}"
            )

        elif animation == "slide_right":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            from_x = -int(video_width * 0.05)
            move_ms = _animation_speed_ms(anim_speed, 300)
            fade_in = _animation_speed_ms(anim_speed, 80)
            effect = (
                f"{{\\move({from_x},{y_pos},{cx},{y_pos},0,{move_ms})}}"
                f"{{\\fad({fade_in},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{effect}{chunk_text}"
            )

        # --- scale_in (zoom from small to normal) ---
        elif animation == "scale_in":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            grow_ms = _animation_speed_ms(anim_speed, 350)
            fade_in = _animation_speed_ms(anim_speed, 100)
            effect = (
                f"{{\\fscx10\\fscy10\\t(0,{grow_ms},\\fscx105\\fscy105)"
                f"\\t({grow_ms},{grow_ms + 150},\\fscx100\\fscy100)}}"
                f"{{\\fad({fade_in},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{base_prefix}{effect}{chunk_text}"
            )

        # --- reveal (horizontal scale + clip) ---
        elif animation == "reveal":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            reveal_ms = _animation_speed_ms(anim_speed, 400)
            clip_w = int(video_width * 0.45)
            x1 = cx - clip_w
            x2 = cx + clip_w
            effect = (
                f"{{\\clip({cx},{y_pos - 60},{cx},{y_pos + 60})"
                f"\\t(0,{reveal_ms},\\clip({x1},{y_pos - 60},{x2},{y_pos + 60}))}}"
                f"{{\\fscx0\\t(0,{reveal_ms},\\fscx100)}}"
                f"{{\\fad({_animation_speed_ms(anim_speed, 80)},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{base_prefix}{effect}{chunk_text}"
            )

        # --- bounce (overshoot + settle) ---
        elif animation == "bounce":
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            dur = int((end - start) * 1000)
            t1 = int(dur * 0.35)
            t2 = int(dur * 0.6)
            t3 = int(dur * 0.8)
            bounce_prefix = (
                f"{{\\fscx50\\fscy50"
                f"\\t(0,{t1},\\fscx115\\fscy115)"
                f"\\t({t1},{t2},\\fscx90\\fscy90)"
                f"\\t({t2},{t3},\\fscx105\\fscy105)"
                f"\\t({t3},{dur},\\fscx100\\fscy100)}}"
                f"{{\\fad({_animation_speed_ms(anim_speed, 80)},0)}}"
            )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{base_prefix}{bounce_prefix}{chunk_text}"
            )

        # --- standard animations (none, fade, pop) ---
        else:
            start = float(chunk[0]["start"])
            end = float(chunk_end)
            if end <= start:
                end = start + 0.05
            effect_prefix = base_prefix
            if animation == "fade":
                effect_prefix = f"{base_prefix}{{\\fad(150,150)}}"
            elif animation == "pop":
                effect_prefix = (
                    f"{base_prefix}{{\\fscx92\\fscy92\\t(0,140,\\fscx108\\fscy108)"
                    "\\t(140,260,\\fscx100\\fscy100)}}"
                )
            events.append(
                f"Dialogue: 0,{ass_timestamp(start)},{ass_timestamp(end)},Default,,0,0,0,,{effect_prefix}{chunk_text}"
            )

    output_ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    logger.info("Wrote ASS subtitles: %s (%d events)", output_ass_path, len(events))
    return True


def format_transcript_for_analysis(transcript) -> List[str]:
    utterances = getattr(transcript, "utterances", None) or []
    if utterances:
        formatted_lines = []
        for utterance in utterances:
            start_time = format_ms_to_timestamp(utterance.start)
            end_time = format_ms_to_timestamp(utterance.end)
            speaker = getattr(utterance, "speaker", None)
            speaker_prefix = f"Speaker {speaker}: " if speaker else ""
            formatted_lines.append(
                f"[{start_time} - {end_time}] {speaker_prefix}{utterance.text}"
            )
        return formatted_lines

    formatted_lines = []
    words = getattr(transcript, "words", None) or []
    if not words:
        return formatted_lines

    logger.info(f"Processing {len(words)} words with precise timing")
    current_segment = []
    current_start = None
    segment_word_count = 0
    max_words_per_segment = 8

    for word in words:
        if current_start is None:
            current_start = word.start
        current_segment.append(word.text)
        segment_word_count += 1

        if (
            segment_word_count >= max_words_per_segment
            or word.text.endswith(".")
            or word.text.endswith("!")
            or word.text.endswith("?")
        ):
            if current_segment:
                start_time = format_ms_to_timestamp(current_start)
                end_time = format_ms_to_timestamp(word.end)
                text = " ".join(current_segment)
                formatted_lines.append(f"[{start_time} - {end_time}] {text}")
            current_segment = []
            current_start = None
            segment_word_count = 0

    if current_segment and current_start is not None:
        start_time = format_ms_to_timestamp(current_start)
        end_time = format_ms_to_timestamp(words[-1].end)
        text = " ".join(current_segment)
        formatted_lines.append(f"[{start_time} - {end_time}] {text}")

    return formatted_lines


def parse_transcript_lines(transcript: str) -> List[Dict[str, Any]]:
    lines: List[Dict[str, Any]] = []
    pattern = re.compile(
        r"^\[(?P<start>\d{1,3}:\d{2})\s*-\s*(?P<end>\d{1,3}:\d{2})\]\s*(?P<text>.*)$"
    )
    for raw_line in transcript.splitlines():
        match = pattern.match(raw_line.strip())
        if not match:
            continue
        text = match.group("text").strip()
        speaker = None
        speaker_match = re.match(r"Speaker\s+([^:]+):\s*(.*)$", text)
        if speaker_match:
            speaker = speaker_match.group(1).strip()
            text = speaker_match.group(2).strip()
        lines.append({
            "start": parse_timestamp_to_seconds(match.group("start")),
            "end": parse_timestamp_to_seconds(match.group("end")),
            "start_label": match.group("start"),
            "end_label": match.group("end"),
            "speaker": speaker,
            "text": text,
        })
    return lines
