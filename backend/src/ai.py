"""
AI-related functions for transcript analysis with enhanced precision and virality scoring.
"""

from pathlib import Path
from typing import List, Dict, Any, Optional, Literal, Callable
import asyncio
import logging
import re
import time

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.ollama import OllamaModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.providers.openai import OpenAIProvider
from pydantic import AliasChoices, BaseModel, Field, field_validator

from .config import Config, get_config
from .runtime_settings import apply_settings_to_process_env

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_CHARS = 1_000_000

IDEAL_CLIP_MIN_SECONDS = 90
IDEAL_CLIP_MAX_SECONDS = 150
MIN_ACCEPTED_CLIP_SECONDS = 60
MAX_ACCEPTED_CLIP_SECONDS = 180
TRANSCRIPT_ANALYSIS_CACHE_VERSION = "qwen3-4b-v1"
TRANSCRIPT_SPAN_RE = re.compile(
    r"^\[(?P<start>\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*"
    r"(?P<end>\d{1,2}:\d{2}(?::\d{2})?)\]\s*(?P<text>.*)$"
)


class ViralityAnalysis(BaseModel):
    """Detailed virality breakdown for a segment."""

    hook_score: int = Field(
        default=15,
        description="How strong is the opening hook (0-25)",
        ge=0,
        le=25,
    )
    engagement_score: int = Field(
        default=15,
        description="How engaging/entertaining is the content (0-25)",
        ge=0,
        le=25,
    )
    value_score: int = Field(
        default=15,
        description="Educational/informational value (0-25)",
        ge=0,
        le=25,
    )
    shareability_score: int = Field(
        default=15,
        description="Likelihood of being shared (0-25)",
        ge=0,
        le=25,
    )
    total_score: int = Field(
        default=60,
        description="Combined virality score (0-100)",
        ge=0,
        le=100,
    )
    hook_type: Optional[
        Literal["question", "statement", "statistic", "story", "contrast", "none"]
    ] = Field(
        default="none",
        description="Type of hook: question, statement, statistic, story, contrast, or none",
    )
    virality_reasoning: str = Field(
        default="The model did not provide a detailed virality breakdown.",
        description="Explanation of the virality score",
    )


def _default_virality_analysis() -> ViralityAnalysis:
    return ViralityAnalysis()


class TranscriptSegment(BaseModel):
    """Represents a relevant segment of transcript with precise timing and virality analysis."""

    start_time: str = Field(description="Start timestamp in MM:SS format")
    end_time: str = Field(description="End timestamp in MM:SS format")
    text: str = Field(
        validation_alias=AliasChoices("text", "segment"),
        description=(
            "Transcript text taken only from the selected timestamp range. "
            "Keep it verbatim or near-verbatim, and do not paraphrase or merge non-contiguous lines."
        ),
    )
    relevance_score: float = Field(
        default=0.75, description="Relevance score from 0.0 to 1.0", ge=0.0, le=1.0
    )
    reasoning: str = Field(
        default="Selected by the AI model as a clip candidate.",
        description=(
            "Brief factual explanation of why this exact segment works as a clip. "
            "Base it only on the provided transcript content."
        ),
    )
    virality: ViralityAnalysis = Field(
        default_factory=_default_virality_analysis,
        description="Detailed virality score breakdown",
    )

    @field_validator("relevance_score", mode="before")
    @classmethod
    def _coerce_percent_relevance_score(cls, value: Any) -> Any:
        if value is None:
            return value
        try:
            numeric_value = float(value)
        except (TypeError, ValueError):
            return value
        if numeric_value > 1 and numeric_value <= 100:
            return numeric_value / 100
        return value


class BRollOpportunity(BaseModel):
    """Identifies an opportunity to insert B-roll footage."""

    timestamp: str = Field(
        default="00:00",
        validation_alias=AliasChoices("timestamp", "segment_start_time", "start_time"),
        description="When to insert B-roll (MM:SS format)",
    )
    duration: float = Field(
        default=3.0,
        description="How long to show B-roll (2-5 seconds)",
        ge=2.0,
        le=5.0,
    )
    search_term: str = Field(
        default="related visual",
        validation_alias=AliasChoices("search_term", "broll", "visual", "query"),
        description="Keyword to search for B-roll footage",
    )
    context: str = Field(
        default="Suggested B-roll opportunity from the model.",
        validation_alias=AliasChoices("context", "description"),
        description="What's being discussed at this point",
    )

    @field_validator("search_term", "context", mode="before")
    @classmethod
    def _coerce_textish_value(cls, value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, list):
            return ", ".join(str(item) for item in value if item is not None)
        return str(value)


class TranscriptAnalysis(BaseModel):
    """Analysis result for transcript segments with virality and B-roll opportunities."""

    most_relevant_segments: List[TranscriptSegment]
    summary: str = Field(description="Brief summary of the video content")
    key_topics: List[str] = Field(description="List of main topics discussed")
    broll_opportunities: Optional[List[BRollOpportunity]] = Field(
        default=None, description="Opportunities to insert B-roll footage"
    )


# Enhanced system prompt with virality scoring and B-roll detection
transcript_analysis_system_prompt = """You are an expert transcript analyst for short-form video editing. Your ONLY job is to select the best 2-5 contiguous transcript segments that would work as standalone viral clips.

OUTPUT CONTRACT:
- Return valid JSON only. No Markdown, headings, bullets, prose, code fences, explanations, or commentary outside the JSON object.
- The top-level JSON object must include: "most_relevant_segments", "summary", and "key_topics".
- Only include "broll_opportunities" when B-roll was requested.
- Each item in "most_relevant_segments" must include: "start_time", "end_time", "text", "relevance_score", "reasoning", and "virality".
- Do not use "segment" as an output field. Use "text".
- "virality" must include: "hook_score", "engagement_score", "value_score", "shareability_score", "total_score", "hook_type", and "virality_reasoning".
- Every returned segment must be 60-180 seconds long. Prefer 90-150 seconds.
- start_time must always be different from end_time. Minimum 60 seconds apart.

GROUNDING RULES:
1. Use ONLY the provided transcript lines and timestamps.
2. Never invent facts, tone, context, or transitions not present in the transcript.
3. Treat this as span selection over a timestamped transcript, not open-ended summarization.
4. Each selected segment must map to ONE contiguous range in the transcript.
5. segment.text must match the chosen span closely and must not include content from outside the chosen range.
6. Do not stitch together distant moments into one clip.
7. If a speaker label appears, use it only if it is part of the spoken content and helps clarity.

CONTENT NEUTRALITY:
- This is clipping software for legitimate editing workflows.
- Do not judge or downgrade a segment based on topic. Evaluate only on clip quality.
- Only downgrade when the transcript itself is weak, confusing, repetitive, or a poor standalone clip.

WHAT MAKES A GREAT CLIP:
A great clip is self-contained: a viewer who has never seen the video should understand and care. It needs:
- A hook that grabs attention in the first 5 seconds
- A complete thought with setup and payoff
- Specific, concrete details (not vague discussion)
- Emotional charge, surprise, or utility

EXAMPLES OF STRONG SEGMENTS:
- A contrarian claim with supporting evidence
- A specific mistake the speaker made and what they learned
- A concrete framework or system the audience can apply
- A surprising result or before/after transformation
- A heated debate or emotional reaction moment
- A complete answer to an interesting question
- A step-by-step explanation of something valuable

EXAMPLES OF WEAK SEGMENTS (AVOID):
- Intros ("Hey guys welcome back to the channel")
- Sponsor reads or CTA sections ("Use my code for 20% off")
- Vague setup without payoff ("So let me tell you about this thing")
- Contextless quote fragments ("...and that's why it matters")
- Repeated points the speaker already made
- Definitions without application ("X is defined as...")
- Meandering background without a point
- Answer fragments that require the question to understand

VOCABULARY: When selecting timestamps, use the EXACT format from the transcript (e.g. "02:25"). If the transcript uses HH:MM:SS, use HH:MM:SS.

SCORING: relevance_score (0-100) should reflect standalone clip quality. Penalize clips that need outside context, lack payoff, or contain too much filler.

virality scoring (0-100 total, from four 0-25 subscores):
1. HOOK STRENGTH (0-25): 20-25 = immediately grabs attention; 15-19 = good curiosity gap; 10-14 = decent; 0-9 = weak
2. ENGAGEMENT (0-25): 20-25 = highly entertaining or emotional; 15-19 = holds attention; 10-14 = moderate; 0-9 = flat
3. VALUE (0-25): 20-25 = actionable insights or unique knowledge; 15-19 = useful info; 10-14 = somewhat informative; 0-9 = filler
4. SHAREABILITY (0-25): 20-25 = "must send to someone"; 15-19 = worth bookmarking; 10-14 = nice but not shareable; 0-9 = generic

HOOK TYPES: "question" (opens with question), "statement" (bold claim), "statistic" (compelling numbers), "story" (narrative), "contrast" (before/after), "none" (no clear hook).

Quality over quantity: choose 2-5 segments. Every segment must be accurate, self-contained, with proper time ranges and strong virality scores."""

# Lazy-loaded agent to avoid import-time failures when API keys aren't set

# Lazy-loaded agent to avoid import-time failures when API keys aren't set
_transcript_agent: Optional[Agent[None, TranscriptAnalysis]] = None
_transcript_agent_signature: Optional[tuple[str | None, ...]] = None

SUPPORTED_LLM_PROVIDERS = {"google", "google-gla", "openai", "anthropic", "ollama"}


def _split_llm_name(model_name: str) -> tuple[str, str | None]:
    if ":" not in model_name:
        return model_name.strip().lower(), None

    provider, provider_model_name = model_name.split(":", 1)
    return provider.strip().lower(), provider_model_name.strip() or None


def _get_missing_llm_key_error(
    model_name: str, runtime_config: Config
) -> Optional[str]:
    """Return a clear configuration error when the selected LLM key is missing."""
    provider, provider_model_name = _split_llm_name(model_name)

    if provider not in SUPPORTED_LLM_PROVIDERS:
        return (
            f"Unsupported LLM provider '{provider}'. "
            "Use google-gla:*, openai:*, anthropic:*, or ollama:*."
        )

    if not provider_model_name:
        return (
            "Selected LLM is missing a model name. "
            "Use the format provider:model, for example ollama:gpt-oss:20b."
        )

    if provider in {"google", "google-gla"} and not runtime_config.google_api_key:
        return (
            "Selected LLM provider is Google, but GOOGLE_API_KEY is not set. "
            "Set GOOGLE_API_KEY or set LLM to openai:* / anthropic:* / ollama:* with the matching API key."
        )

    if provider == "openai":
        if not runtime_config.openai_api_key and not runtime_config.openai_base_url:
            return (
                "Selected LLM provider is OpenAI, but OPENAI_API_KEY is not set "
                "and OPENAI_BASE_URL is not set either. "
                "Set OPENAI_API_KEY for the OpenAI API, or set OPENAI_BASE_URL "
                "to point to a local OpenAI-compatible endpoint (e.g. llama.cpp)."
            )

    if provider == "anthropic" and not runtime_config.anthropic_api_key:
        return (
            "Selected LLM provider is Anthropic, but ANTHROPIC_API_KEY is not set. "
            "Set ANTHROPIC_API_KEY or choose another provider with a matching API key."
        )

    if provider == "ollama":
        # Ollama can run locally without an API key. OLLAMA_BASE_URL/OLLAMA_API_KEY
        # are optional and passed through as environment variables.
        return None

    return None


def _build_transcript_model(runtime_config: Config) -> Model | str:
    provider, provider_model_name = _split_llm_name(runtime_config.llm)

    if provider == "ollama":
        if not provider_model_name:
            raise RuntimeError(
                "Selected LLM provider is Ollama, but no model name was provided. "
                "Use the format ollama:<model>, for example ollama:gpt-oss:20b."
            )
        return OllamaModel(
            provider_model_name,
            provider=OllamaProvider(
                base_url=runtime_config.resolve_ollama_base_url(),
                api_key=runtime_config.ollama_api_key,
            ),
        )

    if provider == "openai" and runtime_config.openai_base_url:
        if not provider_model_name:
            raise RuntimeError(
                "Selected LLM provider is OpenAI with custom base URL, "
                "but no model name was provided. "
                "Use the format openai:<model-name>."
            )
        return OpenAIModel(
            provider_model_name,
            provider=OpenAIProvider(
                base_url=runtime_config.openai_base_url,
                api_key=runtime_config.openai_api_key or "",
            ),
        )

    return runtime_config.llm


def get_transcript_agent() -> Agent[None, TranscriptAnalysis]:
    """Get or create the transcript analysis agent (lazy initialization)."""
    global _transcript_agent, _transcript_agent_signature
    runtime_config = get_config()
    provider, _ = _split_llm_name(runtime_config.llm)
    signature = (
        runtime_config.llm,
        runtime_config.openai_api_key,
        runtime_config.google_api_key,
        runtime_config.anthropic_api_key,
        runtime_config.ollama_base_url,
        runtime_config.ollama_api_key,
        runtime_config.openai_base_url,
    )
    if _transcript_agent is None or _transcript_agent_signature != signature:
        apply_settings_to_process_env(runtime_config.as_runtime_settings())
        config_error = _get_missing_llm_key_error(runtime_config.llm, runtime_config)
        if config_error:
            raise RuntimeError(config_error)

        _transcript_agent = Agent[None, TranscriptAnalysis](
            model=_build_transcript_model(runtime_config),
            output_type=TranscriptAnalysis,
            system_prompt=transcript_analysis_system_prompt,
            # Some local Ollama/OpenAI-compatible endpoints can return formatted
            # prose before settling on schema-valid JSON. Keep retries limited
            # while still allowing enough repair attempts for local models.
            output_retries=2 if provider == "ollama" else 2,
        )
        _transcript_agent_signature = signature
    return _transcript_agent


def _get_total_transcript_duration_seconds(transcript: str) -> int:
    last_end = 0
    for line in transcript.splitlines():
        m = TRANSCRIPT_SPAN_RE.match(line.strip())
        if m:
            try:
                end_sec = _parse_transcript_timestamp_seconds(m.group("end"))
                if end_sec > last_end:
                    last_end = end_sec
            except ValueError:
                continue
    return last_end


def _format_duration(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    return f"{m}m {s}s"


def build_transcript_analysis_prompt(
    transcript: str, include_broll: bool = False, clip_signals: str | None = None
) -> str:
    """Build the grounded task prompt for transcript analysis."""
    broll_instruction = ""
    if include_broll:
        broll_instruction = "\n5. Also identify B-roll opportunities for each chosen segment where stock footage could enhance the visual appeal."
    signal_section = ""
    if clip_signals:
        signal_section = (
            "\n\nAdditional deterministic signals from transcript/audio analysis:\n"
            f"{clip_signals}\n\n"
            "Use these as hints only. They should influence ranking, but every final segment "
            "must still be a coherent contiguous transcript range."
        )

    total_seconds = _get_total_transcript_duration_seconds(transcript)
    total_str = _format_duration(total_seconds)

    return f"""Select the 2-5 best clip segments from this transcript. Return JSON only.

WORKFLOW:
1. Read the entire transcript first. Note the last timestamp (video is {total_str} long).
2. Identify 4-8 candidate moments that could work as standalone clips.
3. Rank them by: self-contained clarity, hook strength, emotional impact, concrete value.
4. Select the best 2-5, ensuring they are spread across the timeline.
5. For each selected segment, set start_time and end_time to EXACT transcript timestamps.
6. Include enough surrounding context (contiguous transcript lines) so the clip makes sense alone.

DURATION RULES:
- Each segment must be 60-180 seconds.
- Prefer 90-150 seconds.
- If a great moment is under 90 seconds, expand it with nearby context lines until it reaches 90+ seconds.
- If a moment needs the first few seconds of setup, include them. A slow start is better than a confusing clip.
- Stop expanding when the topic shifts, the speaker repeats, or the energy drops.

TIMELINE COVERAGE (IMPORTANT):
- At most ONE clip may start in the first 20% of the video.
- You MUST select clips from at least two different thirds of the video.
- Spread selections across the timeline. If the best clips are all early, drop the weakest early pick and pick from a later section.
- No two clips may overlap or share transcript lines.
- When in doubt, prefer later parts of the video over earlier ones.

GOOD PICKS (concrete examples):
- A speaker says "I made this one mistake that cost me $10,000" → clip from that moment with the lesson
- "Here are the 3 things I wish I knew before starting" → clip covering all 3 points
- An argument or debate where someone makes a strong point
- "Let me show you exactly how to do this" → step-by-step explanation
- A surprising statistic or fact with context
- Before/after comparison with specific details
- Emotional story with a clear lesson

BAD PICKS (avoid these):
- "Hey guys welcome back" → intros
- "Use code X for Y% off" → sponsor reads
- "In this video we'll cover..." → previews/outros
- "So yeah that's basically it" → rambling without point
- "As I mentioned earlier..." → repeated content
- Any content that makes no sense without the video title or prior context
- Random quotes without surrounding context

VOCABULARY: Use timestamps exactly as they appear. If the transcript shows "[02:25 - 02:35]", use "02:25" and "02:35".

Transcript:
{transcript}"""


def _parse_transcript_timestamp_seconds(timestamp: str) -> int:
    """Parse MM:SS or HH:MM:SS transcript timestamps into seconds."""
    parts = [int(part) for part in timestamp.split(":")]
    if len(parts) == 2:
        minutes, seconds = parts
        return minutes * 60 + seconds
    if len(parts) == 3:
        hours, minutes, seconds = parts
        return hours * 3600 + minutes * 60 + seconds
    raise ValueError(f"Unsupported timestamp format: {timestamp}")


def _format_transcript_timestamp(seconds: int) -> str:
    """Format seconds as a transcript timestamp."""
    seconds = max(0, int(seconds))
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


def _parse_transcript_spans(transcript: str) -> list[dict[str, Any]]:
    """Parse timestamped transcript lines into spans."""
    spans = []
    for line in transcript.splitlines():
        match = TRANSCRIPT_SPAN_RE.match(line.strip())
        if not match:
            continue
        try:
            start_seconds = _parse_transcript_timestamp_seconds(match.group("start"))
            end_seconds = _parse_transcript_timestamp_seconds(match.group("end"))
        except ValueError:
            continue
        if end_seconds <= start_seconds:
            continue
        spans.append(
            {
                "start": start_seconds,
                "end": end_seconds,
                "text": match.group("text").strip(),
            }
        )
    return spans


def _extract_transcript_text(
    transcript_spans: list[dict[str, Any]], start_seconds: int, end_seconds: int
) -> str:
    """Return transcript text overlapping a selected time range."""
    selected_text = [
        span["text"]
        for span in transcript_spans
        if span["text"] and span["end"] > start_seconds and span["start"] < end_seconds
    ]
    return " ".join(selected_text).strip()


def _choose_repaired_bounds(
    transcript_spans: list[dict[str, Any]], start_seconds: int, end_seconds: int
) -> tuple[int, int] | None:
    """Repair model-selected bounds to the nearest acceptable contiguous range."""
    if not transcript_spans:
        return None

    starts = sorted({span["start"] for span in transcript_spans})
    ends = sorted({span["end"] for span in transcript_spans})
    current_duration = end_seconds - start_seconds

    if current_duration > MAX_ACCEPTED_CLIP_SECONDS:
        target_end = start_seconds + IDEAL_CLIP_MAX_SECONDS
        candidate_ends = [
            candidate
            for candidate in ends
            if start_seconds + MIN_ACCEPTED_CLIP_SECONDS
            <= candidate
            <= min(target_end, end_seconds)
        ]
        if candidate_ends:
            return start_seconds, max(candidate_ends)
        if start_seconds + MIN_ACCEPTED_CLIP_SECONDS <= target_end:
            return start_seconds, target_end
        return None

    if current_duration < MIN_ACCEPTED_CLIP_SECONDS:
        candidate_ranges: list[tuple[int, int, int]] = []
        for candidate_start in starts:
            if candidate_start > start_seconds:
                continue
            for candidate_end in ends:
                if candidate_end < end_seconds:
                    continue
                duration = candidate_end - candidate_start
                if MIN_ACCEPTED_CLIP_SECONDS <= duration <= MAX_ACCEPTED_CLIP_SECONDS:
                    extra_context = (start_seconds - candidate_start) + (
                        candidate_end - end_seconds
                    )
                    ideal_penalty = 0
                    if duration < IDEAL_CLIP_MIN_SECONDS:
                        ideal_penalty = IDEAL_CLIP_MIN_SECONDS - duration
                    elif duration > IDEAL_CLIP_MAX_SECONDS:
                        ideal_penalty = duration - IDEAL_CLIP_MAX_SECONDS
                    candidate_ranges.append(
                        (
                            ideal_penalty * 1000 + extra_context,
                            candidate_start,
                            candidate_end,
                        )
                    )
        if candidate_ranges:
            _, repaired_start, repaired_end = min(candidate_ranges)
            return repaired_start, repaired_end

    return None


def _repair_segment_bounds(
    segment: TranscriptSegment,
    transcript_spans: list[dict[str, Any]],
    start_seconds: int,
    end_seconds: int,
) -> tuple[int, int] | None:
    """Adjust near-miss model ranges to usable transcript-aligned bounds."""
    repaired_bounds = _choose_repaired_bounds(
        transcript_spans,
        start_seconds,
        end_seconds,
    )
    if not repaired_bounds:
        return None

    repaired_start, repaired_end = repaired_bounds
    segment.start_time = _format_transcript_timestamp(repaired_start)
    segment.end_time = _format_transcript_timestamp(repaired_end)
    repaired_text = _extract_transcript_text(
        transcript_spans,
        repaired_start,
        repaired_end,
    )
    if repaired_text:
        segment.text = repaired_text
    logger.info(
        "Repaired segment duration: %s-%s -> %s-%s",
        _format_transcript_timestamp(start_seconds),
        _format_transcript_timestamp(end_seconds),
        segment.start_time,
        segment.end_time,
    )
    return repaired_start, repaired_end


async def get_most_relevant_parts_by_transcript(
    transcript: str, include_broll: bool = False, clip_signals: str | None = None,
    progress_callback: Callable | None = None,
) -> TranscriptAnalysis:
    """Get the most relevant parts of a transcript with virality scoring and optional B-roll detection."""
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        logger.warning(
            f"Transcript too long ({len(transcript)} chars), truncating to {MAX_TRANSCRIPT_CHARS}"
        )
        lines = transcript.splitlines()
        n = len(lines)
        gap = "[...]"

        portions = [
            (0, int(n * 0.35)),
            (int(n * 0.4), int(n * 0.65)),
            (int(n * 0.7), n),
        ]
        parts = []
        budget_remaining = MAX_TRANSCRIPT_CHARS
        markers = []
        for start, end in portions:
            if budget_remaining <= len(gap):
                break
            chunk = "\n".join(lines[start:end])
            overhead = len(gap) + 1 if parts else 0
            if len(chunk) + overhead <= budget_remaining:
                if parts:
                    parts.append(gap)
                    budget_remaining -= len(gap) + 1
                parts.append(chunk)
                budget_remaining -= len(chunk)
                markers.append(f"{start/n*100:.0f}%-{end/n*100:.0f}%")
            else:
                # Fit what we can of this chunk
                take_chars = budget_remaining - overhead
                if take_chars > 100:
                    chunk_lines = lines[start:end]
                    partial = []
                    c = 0
                    for line in chunk_lines:
                        needed = len(line) + 1
                        if c + needed > take_chars:
                            break
                        partial.append(line)
                        c += needed
                    if parts:
                        parts.append(gap)
                    parts.append("\n".join(partial))
                    markers.append(f"{start/n*100:.0f}%-partial")
                break
        transcript = "\n".join(parts)
        logger.info(
            f"Truncated transcript to {len(transcript)} chars ({len(transcript.splitlines())} lines, "
            f"sampled {markers})"
        )

    logger.info(
        f"Starting AI analysis of transcript ({len(transcript)} chars), include_broll={include_broll}"
    )

    try:
        agent = get_transcript_agent()

        # Start a background task that reports time-based AI analysis progress
        if progress_callback:
            _ai_start_time = time.time()
            # Estimate total processing: ~0.5s per 100 chars for prompt processing + ~2s per segment for generation
            _est_chars = len(transcript)
            _est_total_secs = max(30, min(180, _est_chars / 200 + 60))

            async def _ai_progress_reporter():
                while True:
                    _elapsed = time.time() - _ai_start_time
                    _pct = min(int((_elapsed / _est_total_secs) * 100), 99)
                    _main_pct = 52 + int(_pct * 0.18)
                    await progress_callback(
                        _main_pct, "Analyzing content with AI (analyzing transcript)...",
                        "processing",
                        sub_progress=_pct,
                        sub_message=f"~{_est_total_secs - _elapsed:.0f}s remaining" if _elapsed < _est_total_secs else "Finishing up...",
                        metadata={"elapsed_seconds": round(_elapsed, 1), "estimated_total_seconds": round(_est_total_secs, 0)},
                    )
                    await asyncio.sleep(3)

            _progress_task = asyncio.create_task(_ai_progress_reporter())

        result = await agent.run(
            build_transcript_analysis_prompt(
                transcript=transcript,
                include_broll=include_broll,
                clip_signals=clip_signals,
            )
        )

        if progress_callback:
            _progress_task.cancel()
            # Signal that AI analysis is done, moving to validation
            await progress_callback(
                70, "Creating video clips...", "processing",
                sub_progress=100, sub_message="AI analysis complete",
                metadata={"elapsed_seconds": round(time.time() - _ai_start_time, 1)},
            )

        analysis = result.output
        logger.info(
            f"AI analysis found {len(analysis.most_relevant_segments)} segments"
        )

        # Validation with virality data handling
        validated_segments: list[TranscriptSegment] = []
        transcript_spans = _parse_transcript_spans(transcript)

        def _segment_seconds(seg: TranscriptSegment) -> tuple[int, int]:
            return (
                _parse_transcript_timestamp_seconds(seg.start_time),
                _parse_transcript_timestamp_seconds(seg.end_time),
            )

        def _overlap_ratio(a_start: int, a_end: int, b_start: int, b_end: int) -> float:
            overlap = max(0, min(a_end, b_end) - max(a_start, b_start))
            duration = min(a_end - a_start, b_end - b_start)
            return overlap / duration if duration > 0 else 0.0

        for segment in analysis.most_relevant_segments:
            # Validate text content
            if not segment.text.strip() or len(segment.text.split()) < 3:
                logger.warning(
                    f"Skipping segment with insufficient content: '{segment.text[:50]}...'"
                )
                continue

            # Validate timestamps - CRITICAL: start and end must be different
            if segment.start_time == segment.end_time:
                logger.warning(
                    f"Skipping segment with identical start/end times: {segment.start_time}"
                )
                continue

            # Parse timestamps to validate duration
            try:
                start_seconds = _parse_transcript_timestamp_seconds(segment.start_time)
                end_seconds = _parse_transcript_timestamp_seconds(segment.end_time)

                duration = end_seconds - start_seconds

                if (
                    duration < MIN_ACCEPTED_CLIP_SECONDS
                    or duration > MAX_ACCEPTED_CLIP_SECONDS
                ):
                    repaired_bounds = _repair_segment_bounds(
                        segment,
                        transcript_spans,
                        start_seconds,
                        end_seconds,
                    )
                    if repaired_bounds:
                        start_seconds, end_seconds = repaired_bounds
                        duration = end_seconds - start_seconds

                if duration <= 0:
                    logger.warning(
                        f"Skipping segment with invalid duration: {segment.start_time} to {segment.end_time} = {duration}s"
                    )
                    continue

                if duration < MIN_ACCEPTED_CLIP_SECONDS:
                    logger.warning(
                        f"Skipping segment too short: {duration}s (min {MIN_ACCEPTED_CLIP_SECONDS}s required)"
                    )
                    continue

                if duration > MAX_ACCEPTED_CLIP_SECONDS:
                    logger.warning(
                        f"Skipping segment too long: {duration}s (max {MAX_ACCEPTED_CLIP_SECONDS}s allowed)"
                    )
                    continue

                # Validate virality scores
                if segment.virality:
                    # Ensure total score is sum of subscores
                    calculated_total = (
                        segment.virality.hook_score
                        + segment.virality.engagement_score
                        + segment.virality.value_score
                        + segment.virality.shareability_score
                    )
                    if segment.virality.total_score != calculated_total:
                        logger.warning(
                            f"Correcting virality total: {segment.virality.total_score} -> {calculated_total}"
                        )
                        segment.virality.total_score = calculated_total

                validated_segments.append(segment)
                virality_info = (
                    f", virality={segment.virality.total_score}"
                    if segment.virality
                    else ""
                )
                logger.info(
                    f"Validated segment: {segment.start_time}-{segment.end_time} ({duration}s){virality_info}"
                )

            except (ValueError, IndexError) as e:
                logger.warning(
                    f"Skipping segment with invalid timestamp format: {segment.start_time}-{segment.end_time}: {e}"
                )
                continue

        # Deduplicate overlapping segments: keep higher-virality one
        deduped: list[TranscriptSegment] = []
        for seg in validated_segments:
            s_start, s_end = _segment_seconds(seg)
            overlapping = [
                d for d in deduped
                if _overlap_ratio(s_start, s_end, *_segment_seconds(d)) > 0.4
            ]
            if not overlapping:
                deduped.append(seg)
            else:
                existing = overlapping[0]
                e_score = existing.virality.total_score if existing.virality else 0
                s_score = seg.virality.total_score if seg.virality else 0
                if s_score > e_score:
                    deduped.remove(existing)
                    deduped.append(seg)
                    logger.info(
                        f"Replaced overlapping segment {existing.start_time}-{existing.end_time} "
                        f"(score {e_score}) with {seg.start_time}-{seg.end_time} (score {s_score})"
                    )
                else:
                    logger.info(
                        f"Dropped overlapping segment {seg.start_time}-{seg.end_time} "
                        f"(already covered by {existing.start_time}-{existing.end_time})"
                    )

        # Sort by virality score (primary) then relevance (secondary)
        validated_segments = deduped
        validated_segments.sort(
            key=lambda x: (
                x.virality.total_score if x.virality else 0,
                x.relevance_score,
            ),
            reverse=True,
        )

        final_analysis = TranscriptAnalysis(
            most_relevant_segments=validated_segments,
            summary=analysis.summary,
            key_topics=analysis.key_topics,
            broll_opportunities=analysis.broll_opportunities if include_broll else None,
        )

        logger.info(f"Selected {len(validated_segments)} segments for processing")
        if validated_segments:
            top = validated_segments[0]
            logger.info(
                f"Top segment - relevance: {top.relevance_score:.2f}, virality: {top.virality.total_score if top.virality else 'N/A'}"
            )

        return final_analysis

    except Exception as e:
        logger.error(f"Error in transcript analysis: {e}")
        raise RuntimeError(f"Transcript analysis failed: {str(e)}") from e


def get_most_relevant_parts_sync(transcript: str) -> TranscriptAnalysis:
    """Synchronous wrapper for the async function."""
    return asyncio.run(get_most_relevant_parts_by_transcript(transcript))
