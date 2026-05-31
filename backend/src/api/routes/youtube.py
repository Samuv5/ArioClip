"""
YouTube upload endpoints — OAuth + multi-channel upload.
"""
from __future__ import annotations

import json
import os
import pickle
import urllib.parse
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from pydantic import BaseModel

from openai import OpenAI

from ...config import get_config

router = APIRouter(prefix="/api/youtube", tags=["youtube"])

TOKENS_DIR = Path("data/youtube_tokens")
OUTPUT_DIR = Path("data/outputs")

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
REDIRECT_URI = "http://localhost/"

YOUTUBE_CATEGORIES = {
    "Cine y animaciones": "1", "Autos y vehículos": "2", "Música": "10",
    "Mascotas y animales": "15", "Deportes": "17", "Viajes y eventos": "19",
    "Videojuegos": "20", "Gente y blogs": "22", "Comedia": "23",
    "Entretenimiento": "24", "Noticias y política": "25", "Estilo de vida": "26",
    "Educación": "27", "Ciencia y tecnología": "28",
}


# ── helpers ────────────────────────────────────────────────────────

def _client_config() -> dict:
    cfg = get_config()
    cid = cfg.youtube_client_id
    secret = cfg.youtube_client_secret
    if not cid or not secret:
        raise HTTPException(400, "YOUTUBE_CLIENT_ID and YOUTUBE_CLIENT_SECRET must be set in .env")
    return {
        "installed": {
            "client_id": cid,
            "project_id": "supoclip",
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "client_secret": secret,
            "redirect_uris": [REDIRECT_URI],
        }
    }


def _token_path(name: str) -> Path:
    TOKENS_DIR.mkdir(parents=True, exist_ok=True)
    return TOKENS_DIR / f"{name}.pickle"


def _list_channels() -> list[str]:
    if not TOKENS_DIR.exists():
        return []
    return sorted(f.stem for f in TOKENS_DIR.iterdir() if f.suffix == ".pickle")


def _list_videos() -> list[str]:
    if not OUTPUT_DIR.exists():
        return []
    exts = {".mp4", ".avi", ".mov", ".wmv", ".webm", ".mkv"}
    return sorted(f.name for f in OUTPUT_DIR.iterdir() if f.suffix.lower() in exts)


# ── models ──────────────────────────────────────────────────────────

class AuthUrlRequest(BaseModel):
    channel_name: str


class AuthUrlResponse(BaseModel):
    url: str
    message: str


class AuthCallbackRequest(BaseModel):
    channel_name: str
    callback_url: str


class UploadRequest(BaseModel):
    video: str
    title: str
    description: str = ""
    tags: str = ""
    category: str = "Gente y blogs"
    privacy: str = "Privado"
    made_for_kids: str = "No"
    channels: list[str]


class UploadResponse(BaseModel):
    results: list[str]


class GenerateMetadataRequest(BaseModel):
    clip_text: str
    source_title: str
    original_url: str = ""


class GenerateMetadataResponse(BaseModel):
    title: str
    description: str


# ── endpoints ──────────────────────────────────────────────────────

@router.get("/channels")
def get_channels() -> list[str]:
    return _list_channels()


@router.get("/videos")
def get_videos() -> list[str]:
    return _list_videos()


@router.post("/auth-url", response_model=AuthUrlResponse)
def generate_auth_url(body: AuthUrlRequest):
    if not body.channel_name.strip():
        raise HTTPException(400, "channel_name is required")
    flow = Flow.from_client_config(_client_config(), scopes=SCOPES, redirect_uri=REDIRECT_URI)
    auth_url, _ = flow.authorization_url(prompt="consent")
    # stash flow in a module-level dict keyed by channel name
    _active_flows[body.channel_name] = flow
    return AuthUrlResponse(
        url=auth_url,
        message=(
            f"1. Abrí este enlace y autorizá la app.\n"
            f"2. Te va a redirigir a localhost (mostrará error).\n"
            f"3. Copiá la URL COMPLETA de esa página y pegala en /api/youtube/auth-callback"
        ),
    )


_active_flows: dict[str, Flow] = {}


@router.post("/auth-callback")
def auth_callback(body: AuthCallbackRequest):
    flow = _active_flows.pop(body.channel_name, None)
    if not flow:
        raise HTTPException(400, "Generá el enlace de autenticación primero (/api/youtube/auth-url)")

    try:
        if "code=" in body.callback_url:
            parsed = urllib.parse.urlparse(body.callback_url)
            code = urllib.parse.parse_qs(parsed.query).get("code", [None])[0]
            if code:
                flow.fetch_token(code=code)
            else:
                flow.fetch_token(authorization_response=body.callback_url)
        else:
            flow.fetch_token(authorization_response=body.callback_url)

        path = _token_path(body.channel_name)
        with open(path, "wb") as f:
            pickle.dump(flow.credentials, f)
        return {"ok": True, "channels": _list_channels()}
    except Exception as e:
        raise HTTPException(400, f"Error al autenticar: {e}")


@router.delete("/channels/{channel_name}")
def remove_channel(channel_name: str):
    path = _token_path(channel_name)
    if path.exists():
        path.unlink()
    _active_flows.pop(channel_name, None)
    return {"ok": True, "channels": _list_channels()}


@router.post("/upload", response_model=UploadResponse)
def upload_video(body: UploadRequest):
    video_path = OUTPUT_DIR / body.video
    if not video_path.exists():
        raise HTTPException(404, f"Video '{body.video}' no encontrado en {OUTPUT_DIR}")

    cat_id = YOUTUBE_CATEGORIES.get(body.category, "22")
    privacy_map = {"Público": "public", "Oculto": "unlisted", "Privado": "private"}
    privacy = privacy_map.get(body.privacy, "private")
    tags_list = [t.strip() for t in body.tags.split(",") if t.strip()]
    made_for_kids = body.made_for_kids.lower() in ("sí", "si", "yes", "true", "1")

    results = []
    for ch in body.channels:
        token_path = _token_path(ch)
        if not token_path.exists():
            results.append(f"❌ {ch}: canal no autenticado")
            continue

        with open(token_path, "rb") as f:
            creds = pickle.load(f)
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            with open(token_path, "wb") as f:
                pickle.dump(creds, f)

        try:
            youtube = build("youtube", "v3", credentials=creds)
            body_dict: dict[str, Any] = {
                "snippet": {
                    "title": body.title,
                    "description": body.description,
                    "tags": tags_list,
                    "categoryId": cat_id,
                },
                "status": {
                    "privacyStatus": privacy,
                    "selfDeclaredMadeForKids": made_for_kids,
                },
            }
            req = youtube.videos().insert(
                part=",".join(body_dict.keys()),
                body=body_dict,
                media_body=MediaFileUpload(str(video_path), chunksize=-1, resumable=True),
            )
            resp = req.execute()
            results.append(f"✅ {ch}: https://youtube.com/watch?v={resp['id']}")
        except Exception as e:
            results.append(f"❌ {ch}: {e}")

    return UploadResponse(results=results)


@router.post("/generate-metadata", response_model=GenerateMetadataResponse)
def generate_metadata(body: GenerateMetadataRequest):
    cfg = get_config()
    base_url = cfg.openai_base_url or "http://localhost:8080/v1"
    api_key = cfg.openai_api_key or "not-needed"
    client = OpenAI(api_key=api_key, base_url=base_url)
    model_for_api = cfg.llm.removeprefix("openai:")

    prompt = (
        "You are a YouTube Shorts expert. Based on the following clip transcript and source video title, "
        "generate an engaging YouTube title (max 100 chars) and a description (2-3 sentences) "
        "that includes the original video link if provided.\n\n"
        f"Source video title: {body.source_title}\n"
        f"Clip transcript:\n{body.clip_text}\n"
    )
    if body.original_url:
        prompt += f"Original video URL: {body.original_url}\n"

    prompt += (
        "\nRespond ONLY with valid JSON in this exact format, no other text:\n"
        '{"title": "...", "description": "..."}'
    )

    try:
        response = client.chat.completions.create(
            model=model_for_api or "gemma-3-4b-it",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=300,
        )
        raw = response.choices[0].message.content or ""
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        data = json.loads(raw)
        title = (data.get("title") or "").strip()
        desc = (data.get("description") or "").strip()
        if body.original_url and body.original_url not in desc:
            desc += f"\n\nOriginal video: {body.original_url}"
        return GenerateMetadataResponse(title=title, description=desc)
    except Exception as e:
        return GenerateMetadataResponse(
            title=f"Clip from {body.source_title}",
            description=f"Clip from: {body.source_title}\n\n{body.original_url}" if body.original_url else f"Clip from {body.source_title}",
        )
