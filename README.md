<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/Samuv5/ArioClip/main/assets/social-preview.svg">
  <img src="assets/social-preview.svg" alt="ArioClip Banner" width="100%">
</picture>

<div align="center">

# 🎬 ArioClip

### AI-Powered Video Clipping — Transform Long Content into Viral Shorts

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL%20v3-blue.svg)](https://www.gnu.org/licenses/agpl-3.0)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://python.org)
[![Next.js](https://img.shields.io/badge/Next.js-15-000000?logo=nextdotjs&logoColor=white)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

**[Quickstart](#quickstart)** ·
**[Features](#features)** ·
**[Architecture](#architecture)** ·
**[Self-Hosting](#self-hosting)** ·
**[Contributing](#contributing)**

<br>

> **ArioClip** is a self-hostable, open-source alternative to OpusClip.  
> Drop in a YouTube link or upload a video — AI finds the best moments, generates vertical clips with face-tracking, syncs subtitles, and scores each segment by virality.

</div>

<br>

---

## ✨ Features

| | Feature | Description |
|---|---|---|
| 🎯 | **AI Segment Selection** | Pydantic AI analyzes transcripts to pick 3–7 viral moments (10–45s) |
| 🎭 | **Face-Aware Cropping** | MediaPipe → OpenCV DNN → Haar cascade fallback chain keeps faces centered |
| 📝 | **Word-Synced Subtitles** | WhisperX word timestamps → styled captions with animations |
| 📊 | **Virality Scoring** | Each clip scored on hook, engagement, value & shareability (0–100) |
| 🎨 | **Caption Templates** | Customizable animated templates with multiple styles |
| 🎬 | **Transition Effects** | Optional intro/outro effects between clips |
| 🖼️ | **B-Roll Overlays** | Pexels integration for stock footage overlays |
| 📤 | **YouTube Upload** | Multi-channel OAuth upload directly from the app |
| ⚡ | **Real-Time Progress** | SSE stream from worker → frontend status updates |
| 🔒 | **Self-Hosted** | Full control — no data ever leaves your infrastructure |

<br>

## 🚀 Quickstart

### Prerequisites

- Python 3.11+, Node.js 20+, ffmpeg
- PostgreSQL 15+, Redis 7+
- One AI provider key: OpenAI, Google AI, Anthropic, or [llama.cpp](https://github.com/ggml-org/llama.cpp) with a GGUF model
- (Optional) [AssemblyAI](https://assemblyai.com) API key for cloud transcription
- (Optional) [Pexels](https://pexels.com) API key for B-roll footage

### 1. Clone & Configure

```bash
git clone https://github.com/Samuv5/ArioClip.git
cd ArioClip
cp .env.example .env
# Edit .env with your API keys
```

### 2. Start Services

**Option A — Docker (easiest):**

```bash
docker compose up -d --build
```

**Option B — Local:**

```bash
# Terminal 1: Backend
cd backend && uv venv .venv && source .venv/bin/activate && uv sync
uvicorn src.main:app --host 0.0.0.0 --port 8000

# Terminal 2: Worker
cd backend && source .venv/bin/activate
arq src.workers.tasks.WorkerSettings

# Terminal 3: Frontend
cd frontend && npm install && npm run dev

# (Ensure PostgreSQL & Redis are running locally)
```

### 3. Open & Create

Visit **[http://localhost:3107](http://localhost:3107)** → Sign in → Paste a YouTube URL → Watch AI work its magic.

<br>

## 🏗️ Architecture

```
User → Frontend (Next.js 15) ──→ Backend API (FastAPI) ──→ Redis Queue ──→ Worker
                                        ↓                                     │
                                 PostgreSQL ◄──────────────────────────────────┘
```

| Layer | Tech | Role |
|-------|------|------|
| **Frontend** | Next.js 15, React 19, TailwindCSS v4, ShadCN UI | User interface, auth, real-time progress |
| **API** | FastAPI, SQLAlchemy (raw SQL) | REST endpoints, task lifecycle, media serving |
| **Worker** | ARQ (async Redis queue) | Video download, transcription, AI analysis, clip rendering |
| **Database** | PostgreSQL 15 | Tasks, clips, users, sessions |
| **Queue** | Redis 7 | Job queue, progress pub/sub |
| **LLM** | llama.cpp / OpenAI / Google / Anthropic | AI clip selection + virality scoring |

### Processing Pipeline

```
Input (YouTube URL / Upload)
        │
        ▼
Download (yt-dlp/upload) ────→ WhisperX (local transcription)
        │                              │
        │                              ▼
        │                       AI Segment Selection
        │                              │
        ▼                              ▼
  Face Detection ←────────── Clip Rendering (MoviePy)
  (MediaPipe/DNN/Haar)              │
                                    │
                                    ▼
                           Vertical 9:16 clips +
                           Word-synced subtitles +
                           Virality scores
```

<br>

## 🖥️ Self-Hosting Guide

### Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `ASSEMBLY_AI_API_KEY` | ✗ | Cloud transcription (alternative to local WhisperX) |
| `LLM` | ✅ | `openai:gpt-4o`, `google-gla:gemini-2.0-flash`, `anthropic:claude-3-haiku`, `ollama:gemma-3-4b-it` |
| `OPENAI_API_KEY` | * | One of these LLM provider keys |
| `GOOGLE_API_KEY` | * | |
| `ANTHROPIC_API_KEY` | * | |
| `WHISPERX_MODEL` | ✗ | Local transcription model: `tiny`, `base`, `small`, `medium`, `large` (default: `tiny`) |
| `DATABASE_URL` | ⚡ | `postgresql+asyncpg://user:pass@localhost:5432/arioclip` |
| `REDIS_HOST` | ⚡ | Default: `localhost` |
| `REDIS_PORT` | ⚡ | Default: `6379` |
| `PEXELS_API_KEY` | ✗ | B-roll stock footage |
| `BETTER_AUTH_SECRET` | ⚡ | Auth session encryption |

### Hardware Notes

- **GPU (recommended):** Face detection + WhisperX transcription benefit greatly from CUDA
- **4GB VRAM** works with `llama-server -ngl 24` for Gemma-3-4B-Q5_K_S
- **CPU-only:** Use a cloud LLM provider (`openai:*`, `google-gla:*`) instead

### GPU Memory Management (4GB VRAM)

On low-VRAM cards the worker manages GPU memory by **starting `llama-server` on demand** and stopping it during heavy stages:

```
Download
   ↓
Stop llama-server  ← free VRAM
   ↓
WhisperX transcription (CUDA)
   ↓
Start llama-server ← reload model
   ↓
AI analysis (Pydantic AI / llama)
   ↓
Stop llama-server  ← free VRAM again
   ↓
ffmpeg CUDA rendering (face crop + subtitles)
   ↓
Start llama-server (for next task)
```

The worker auto-stops llama-server before WhisperX and ffmpeg rendering, and restarts it before the next AI analysis. No manual intervention needed.

### yt-dlp & YouTube

YouTube rate-limits aggressive downloads. Keep yt-dlp updated:

```bash
pip3 install -U yt-dlp --break-system-packages
```

1080p downloads require **deno** at `~/.deno/bin/deno` for YouTube challenge solving.

<br>

## 🤝 Contributing

| **Samuv5** |
|---|
| <img src="https://github.com/Samuv5.png" width="100" height="100" alt="Samuv5"> |
| Author & maintainer |

Contributions are welcome! Check the [issues](https://github.com/Samuv5/ArioClip/issues) for open tasks.

1. Fork the repo
2. Create a feature branch (`git checkout -b feat/amazing`)
3. Commit your changes (`git commit -m 'feat: add amazing feature'`)
4. Push to the branch (`git push origin feat/amazing`)
5. Open a Pull Request

<br>

## 📄 License

**AGPL-3.0** — See [LICENSE](LICENSE) for details.

---

<div align="center">

**ArioClip** is a fork of [SupoClip](https://github.com/FujiwaraChoki/supoclip) by FujiwaraChoki.  
Built with ❤️ for the open-source community.

</div>
