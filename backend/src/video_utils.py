"""
Utility functions for video-related operations.
Re-exports from split modules: ffmpeg_utils, subtitle_utils, face_detection, clip_rendering.
"""

from .ffmpeg_utils import (
    run_ffmpeg_command,
    ffprobe_has_audio,
    ffprobe_video_size,
    ffprobe_duration,
    ffmpeg_escape_filter_path,
    ffmpeg_escape_filter_value,
    round_to_even,
    clamp_even,
    parse_timestamp_to_seconds,
    seconds_to_mmss,
    format_ms_to_timestamp,
    get_scaled_font_size,
    get_subtitle_max_width,
    get_safe_vertical_position,
    resize_for_916_filter,
    VALID_OUTPUT_FORMATS,
    CLIP_END_SENTENCE_EXTENSION_SECONDS,
    CLIP_END_PADDING_SECONDS,
    SENTENCE_END_RE,
    get_available_transitions,
    count_scene_cuts,
    parse_motion_metadata,
)

from .subtitle_utils import (
    ass_timestamp,
    hex_to_ass_color,
    escape_ass_text,
    ass_font_name,
    ass_fonts_dir,
    word_ends_sentence,
    cache_transcript_data,
    load_cached_transcript_data,
    _serialize_transcript_word,
    get_words_in_range,
    get_absolute_words_in_range,
    get_words_for_keep_ranges,
    extend_keep_ranges_to_sentence_boundary,
    build_transcript_ass_subtitles,
    format_transcript_for_analysis,
    parse_transcript_lines,
    TRANSCRIPT_CACHE_SCHEMA_VERSION,
)

from .face_detection import (
    detect_optimal_crop_region,
    detect_faces_in_clip,
    filter_face_outliers,
    smooth_values,
    build_speaker_timeline_from_motion,
    cluster_two_face_regions,
    build_pan_expression,
    detect_speaker_reframe_plan,
    detect_auto_center_plan,
    _sample_face_trace,
    _build_trace_x_expression,
    build_static_vertical_filter,
    render_reframed_clip_ffmpeg,
    burn_ass_subtitles_ffmpeg,
)

from .clip_rendering import (
    VideoProcessor,
    render_source_ranges_ffmpeg,
    get_video_transcript,
    build_clip_keep_ranges,
    build_keep_ranges_from_source_ranges,
    create_optimized_clip,
    create_clips_from_segments,
    create_clips_with_transitions,
    detect_audio_peak_times,
    build_clip_signal_summary,
    get_video_transcript_with_assemblyai,
    create_9_16_clip,
    insert_broll_into_clip,
    apply_broll_to_clip,
)
