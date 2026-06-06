# ArioClip

AI-powered video clipping tool — transforms long-form content into viral short clips.  
Fork of [SupoClip](https://github.com/FujiwaraChoki/supoclip) by FujiwaraChoki. AGPL-3.0.

## Quick Start

```bash
./install.sh        # Check deps, set up DB, install backend + frontend
cp .env.example .env # Edit with your API keys
./start-local.sh    # Start all services
```

**Default login:** `admin@supoclip.local` / `admin123`

## Running Services

| Service | Command | Port |
|---------|---------|------|
| Backend | `cd backend && uvicorn src.main:app --host 0.0.0.0 --port 8000` | :8000 |
| Worker | `cd backend && arq src.workers.tasks.WorkerSettings` | — |
| Frontend | `cd frontend && npm run dev` | :3107 |
| llama-server | `llama-server -m <model> --host 0.0.0.0 --port 8080 -ngl 24` | :8080 |

Dependencies: PostgreSQL 15+, Redis 7+, ffmpeg, Python 3.11+, Node.js 20+

## Config

Core `.env` vars:

- `ASSEMBLY_AI_API_KEY` — transcription
- `LLM=openai:gpt-4o` — format: `provider:model` (openai, google-gla, anthropic, ollama)
- `OPENAI_API_KEY` / `GOOGLE_API_KEY` / `ANTHROPIC_API_KEY` — one required

For local llama.cpp: `LLM=openai:gemma-3-4b-it` + `OPENAI_BASE_URL=http://localhost:8080/v1`

## Architecture

```
api/routes/       → HTTP handlers
services/         → Business logic
repositories/     → Raw SQL (asyncpg + text())
workers/          → ARQ job definitions
```

**Pipeline:** Input (yt-dlp/upload) → AssemblyAI → AI segment selection → MoviePy rendering (face crop + subs + effects)

Task status: `queued → processing → completed/error/cancelled`

## Key Files

| Path | Role |
|------|------|
| `backend/src/main.py` | FastAPI entry point |
| `backend/src/api/routes/tasks.py` | Task CRUD, SSE progress, clip editing |
| `backend/src/workers/tasks.py` | ARQ worker (process_video_task) |
| `backend/src/ai.py` | Pydantic AI agent for clip selection |
| `backend/src/ffmpeg_utils.py` | FFmpeg wrappers |
| `backend/src/face_detection.py` | Face detection chain |
| `backend/src/clip_rendering.py` | Clip generation orchestration |
| `frontend/src/app/tasks/[id]/page.tsx` | Task detail page |
| `frontend/src/components/tasks/` | Task UI components |

## Style

- **Python:** 4-space, type hints, snake_case
- **TS/React:** 2-space, PascalCase components, camelCase functions, `@/*` imports
- All DB access via repository classes with raw SQL
- Blocking ops in `run_in_thread()`
