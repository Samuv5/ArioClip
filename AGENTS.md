# ArioClip — Development Guide

This file provides guidance to AI coding assistants when working with this repository.

## Project Overview

**ArioClip** is an open-source AI-powered video clipping tool — a fork of SupoClip. It transforms long-form content into viral short clips. AGPL-3.0 licensed.

## Repository Structure

```
arioclip/
├── backend/          # FastAPI + async worker
│   ├── src/
│   │   ├── api/routes/      # HTTP handlers (tasks.py, media.py, youtube.py)
│   │   ├── services/        # Business logic (task_service.py, video_service.py)
│   │   ├── repositories/    # Raw SQL access (task_repository.py, clip_repository.py)
│   │   ├── workers/         # ARQ job queue (tasks.py, job_queue.py, progress.py)
│   │   ├── main.py          # FastAPI entry point
│   │   ├── ai.py            # Pydantic AI agents for clip selection
│   │   ├── config.py        # Environment configuration
│   │   ├── ffmpeg_utils.py  # FFmpeg wrappers
│   │   ├── subtitle_utils.py# Subtitle utilities
│   │   ├── face_detection.py# Face detection + cropping
│   │   ├── clip_rendering.py# Clip generation
│   │   ├── video_utils.py   # Re-exporter (legacy compat)
│   │   ├── youtube_utils.py # YouTube download
│   │   └── broll.py         # Pexels B-roll integration
│   └── tests/
├── frontend/         # Next.js 15 App Router
│   ├── src/
│   │   ├── app/             # Pages (tasks, youtube, settings, etc.)
│   │   ├── components/      # React components
│   │   │   ├── tasks/       # Task detail components
│   │   │   └── ui/          # ShadCN UI primitives
│   │   ├── lib/             # Utilities, API client
│   │   └── server/          # Server-side API proxy + auth
│   └── prisma/              # Schema (Better Auth)
├── assets/           # Images (banner.png)
├── .env.example      # Environment template
├── docker-compose.yml
└── init.sql
```

## Development Commands

### Docker (recommended for production-like setup)

```bash
docker compose up -d --build    # Start all services
docker compose logs -f          # Stream logs
docker compose down             # Stop everything
```

### Local Development

**Backend:**
```bash
cd backend
uv venv .venv && source .venv/bin/activate
uv sync
uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
```

**Worker:**
```bash
cd backend && source .venv/bin/activate
arq src.workers.tasks.WorkerSettings
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev           # Dev with Turbopack on :3107
npm run build         # Production build
npm run lint          # ESLint
```

**Important:** In the opencode tool environment, services die between tool calls because uvicorn catches SIGHUP. Use this Python wrapper pattern to keep them alive:

```python
python3 -c "
import signal, subprocess, sys
signal.signal(signal.SIGHUP, signal.SIG_IGN)
proc = subprocess.Popen(['.venv/bin/uvicorn', 'src.main:app', '--host', '0.0.0.0', '--port', '8000'], stdout=open('/tmp/backend.log','w'), stderr=subprocess.STDOUT)
print(f'PID: {proc.pid}')
sys.stdout.flush()
" &
disown
```

Same pattern for `arq` worker and `next dev --turbopack --port 3107`.

### Database

```bash
createuser -P supoclip          # password: supoclip_password
createdb -O supoclip supoclip
psql -U supoclip -d supoclip -f init.sql
```

## Coding Style

- **Python:** 4-space indentation, type hints, `snake_case`
- **TypeScript/React:** 2-space indentation, `PascalCase` components, `camelCase` functions
- **Imports:** `@/*` alias in frontend, relative imports in backend
- **Linting:** `cd frontend && npm run lint`, backend uses ruff

## Architecture Notes

### Backend Layered Architecture

```
api/routes/    → HTTP handlers
services/      → Business logic
repositories/  → Raw SQL (asyncpg, text() queries)
workers/       → ARQ job definitions
```

**Patterns:**
- All DB access via repository classes with raw SQL
- Blocking ops wrapped in `run_in_thread()` for async compatibility
- Progress tracking: Redis pub/sub → SSE to frontend
- Task status: `queued → processing → completed/error/cancelled`

### Video Processing Pipeline

1. **Input** → YouTube URL (yt-dlp) or uploaded file
2. **Transcription** → WhisperX word timestamps (cached)
3. **AI Analysis** → Pydantic AI selects 3–7 viral segments with virality scoring
4. **Clip Generation** → MoviePy with face cropping, subtitles, effects
5. **Storage** → Clips to `{TEMP_DIR}/clips/`, metadata to PostgreSQL

### Frontend Architecture

- Next.js 15 App Router, React 19, TailwindCSS v4
- ShadCN UI (New York style, stone base)
- Better Auth with Prisma adapter
- No global state — React hooks only
- API calls proxied through `/api/tasks/[...path]` which signs HMAC headers

## Key API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/start-with-progress` | Create task + enqueue |
| GET | `/tasks/` | List tasks |
| GET | `/tasks/{id}` | Task details + clips |
| GET | `/tasks/{id}/progress` | SSE progress stream |
| DELETE | `/tasks/{id}` | Delete task |
| POST | `/tasks/{id}/cancel` | Cancel processing |
| PATCH | `/tasks/{id}/clips/{clip_id}` | Trim clip |
| POST | `/tasks/{id}/clips/{clip_id}/split` | Split clip |
| POST | `/tasks/{id}/clips/merge` | Merge clips |
| GET | `/fonts` | Available fonts |
| GET | `/caption-templates` | Caption styles |
| GET | `/broll/status` | B-roll service status |
| POST | `/upload` | Upload video file |

## Environment Variables

Required in `.env` (root):

```bash
ASSEMBLY_AI_API_KEY=              # Optional: cloud transcription (local WhisperX by default)
LLM=openai:gpt-4o                 # Provider:model format
OPENAI_API_KEY=...                 # Or GOOGLE_API_KEY / ANTHROPIC_API_KEY / ollama
DATABASE_URL=postgresql+asyncpg://supoclip:supoclip_password@localhost:5432/supoclip
BETTER_AUTH_SECRET=...             # Frontend auth secret
BACKEND_AUTH_SECRET=...            # HMAC signing secret
```

## Configuration Dependencies

- **LLM Backend:** `OPENAI_API_KEY`, `GOOGLE_API_KEY`, or `ANTHROPIC_API_KEY` for cloud; `LLM=ollama:*` for local
- **Ollama (optional):** `OLLAMA_BASE_URL` (default: localhost:11434/v1), `OLLAMA_API_KEY`
- **Pexels:** `PEXELS_API_KEY` for B-roll footage
- **Storage:** `TEMP_DIR` (default: `/tmp`), `UPLOAD_DIR`

## Hardware Requirements

- **GPU recommended** for face detection + whisperX
- GTX 1650 Mobile 4GB: use `-ngl 24` with Gemma-3-4B-Q5_K_S
- CPU-only: use cloud LLM provider instead of local llama.cpp

## Fork Information

ArioClip is a fork of [SupoClip](https://github.com/FujiwaraChoki/supoclip) by FujiwaraChoki.
- Original repo: `https://github.com/FujiwaraChoki/supoclip`
- Upstream remote: `upstream`
- Author: [Samuv5](https://github.com/Samuv5)
