from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import shutil
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

from .config import get_config

logger = logging.getLogger(__name__)

LLAMA_BIN = "/home/samuel/llama/build/bin/llama-server"
LLAMA_MODEL = "/mnt/82F4CC78F4CC6FC9/lmodels/gemma-3-4b-it.Q5_K_S.gguf"
LLAMA_LOG = "/home/samuel/supoclip/llama-server.log"
LLAMA_HEALTH_URL = "http://localhost:8080/v1/models"


class WhisperXWord:
    def __init__(self, word: str, start: float, end: float, confidence: float = 1.0, speaker: Optional[str] = None):
        self.text = word
        self.start = int(start * 1000)
        self.end = int(end * 1000)
        self.confidence = confidence
        self.speaker = speaker


class WhisperXUtterance:
    def __init__(self, text: str, start: float, end: float, words: List[WhisperXWord], speaker: Optional[str] = None):
        self.text = text
        self.start = int(start * 1000)
        self.end = int(end * 1000)
        self.speaker = speaker
        self.words = words


class WhisperXTranscript:
    def __init__(self, segments: List[dict], language: str = "en"):
        self.text = " ".join(seg["text"].strip() for seg in segments if seg.get("text"))
        self.language = language
        self.words: List[WhisperXWord] = []
        self.utterances: List[WhisperXUtterance] = []
        for seg in segments:
            seg_words: List[WhisperXWord] = []
            for w in seg.get("words", []):
                if "start" not in w or "end" not in w:
                    continue
                word_obj = WhisperXWord(
                    word=w.get("word", w.get("text", "")).strip(),
                    start=float(w["start"]),
                    end=float(w["end"]),
                    confidence=w.get("score", 1.0),
                )
                seg_words.append(word_obj)
                self.words.append(word_obj)
            utt = WhisperXUtterance(
                text=seg.get("text", ""),
                start=seg["start"],
                end=seg["end"],
                words=seg_words,
                speaker=seg.get("speaker"),
            )
            self.utterances.append(utt)

    def __getattr__(self, name: str) -> Any:
        return None


def _prepare_audio(video_path: Path) -> Path:
    audio_path = video_path.with_name(f"{video_path.stem}.whisperx.mp3")
    if audio_path.exists() and audio_path.stat().st_size > 0:
        return audio_path
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        str(audio_path),
    ]
    logger.info("Extracting audio for transcription: %s", audio_path)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
    if result.returncode != 0 or not audio_path.exists() or audio_path.stat().st_size == 0:
        logger.warning("ffmpeg audio extraction failed; falling back to source video")
        return video_path
    return audio_path


def _find_whisperx_binary() -> str:
    wx = shutil.which("whisperx")
    if wx:
        return wx
    fallback = "/home/samuel/.local/bin/whisperx"
    if Path(fallback).exists():
        return fallback
    raise RuntimeError("whisperx not found on PATH or at ~/.local/bin/whisperx")


def _stop_llama_server() -> None:
    import psutil
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            if any("llama-server" in p for p in cmdline):
                logger.info("Stopping llama-server (pid %d) to free GPU for whisperx", proc.info["pid"])
                proc.send_signal(signal.SIGTERM)
                proc.wait(timeout=15)
                logger.info("llama-server stopped")
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass

    # give GPU a moment to fully release
    time.sleep(1)


def _start_llama_server() -> bool:
    logger.info("Starting llama-server...")
    log_fd = os.open(LLAMA_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND)
    try:
        proc = subprocess.Popen(
            [
                LLAMA_BIN,
                "-m", LLAMA_MODEL,
                "--host", "0.0.0.0",
                "--port", "8080",
                "--fit", "on",
                "--fit-ctx", "24576",
                "-c", "24576",
                "--cache-type-k", "q8_0",
                "--cache-type-v", "q8_0",
                "-fa", "on",
                "-ub", "1024",
                "-b", "2048",
            ],
            stdout=log_fd,
            stderr=log_fd,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )
    finally:
        os.close(log_fd)

    # poll until ready (max 120s)
    for _ in range(60):
        try:
            r = subprocess.run(
                ["curl", "-sf", LLAMA_HEALTH_URL],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                logger.info("llama-server is ready")
                return True
        except Exception:
            pass
        time.sleep(2)

    logger.error("llama-server failed to start — check %s", LLAMA_LOG)
    return False


def transcribe(video_path: Path, speech_model: str = "base") -> WhisperXTranscript:
    cfg = get_config()
    model = cfg.whisperx_model or speech_model or "small"
    audio_path = _prepare_audio(video_path)
    whisperx_bin = _find_whisperx_binary()
    output_dir = Path(cfg.temp_dir) / "whisperx_outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_name = audio_path.stem
    json_path = output_dir / f"{base_name}.json"

    _stop_llama_server()
    try:
        cmd = [
            whisperx_bin,
            str(audio_path),
            "--model", model,
            "--output_format", "json",
            "--output_dir", str(output_dir),
            "--device", "cuda",
            "--compute_type", "float16",
        ]
        logger.info("Running whisperx on CUDA: %s", " ".join(cmd))
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
        if result.returncode != 0:
            logger.error("whisperx failed: %s", result.stderr[-2000:])
            raise RuntimeError(f"whisperx transcription failed: {result.stderr[-500:]}")
        if not json_path.exists():
            alt_path = output_dir / f"{base_name}.json"
            if alt_path.exists():
                json_path = alt_path
            else:
                logger.error("whisperx JSON output not found at %s", json_path)
                raise RuntimeError(f"whisperx JSON output not found; stderr: {result.stderr[-500:]}")
        with open(json_path) as f:
            data = json.load(f)
        transcript = WhisperXTranscript(segments=data.get("segments", []), language=data.get("language", "en"))
        logger.info("whisperx transcription complete: %d words, %d segments", len(transcript.words), len(transcript.utterances))
        return transcript
    finally:
        restarted = _start_llama_server()
        if not restarted:
            logger.critical("Failed to restart llama-server after transcription!")
        files_to_clean = list(output_dir.glob(f"{base_name}.*"))
        for p in files_to_clean:
            try:
                p.unlink()
            except Exception:
                pass
