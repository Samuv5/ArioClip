#!/bin/bash
# Start all SupoClip services locally (no Docker)
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Starting SupoClip (Local Mode) ==="
echo ""

# ── 0. Optional cleanup ──────────────────────────────────────────
if [[ "${1:-}" == "--clean" ]]; then
    echo "  🧹 Running video cleanup (files >7 days)..."
    "$SCRIPT_DIR/cleanup-old-videos.py" --days 7 2>/dev/null || true
    echo ""
fi

# ── 1. llama.cpp server ──────────────────────────────────────────
if curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
    echo "  ✅ llama-server already running on :8080"
else
    echo "  🔄 Starting llama-server..."
    setsid /home/samuel/llama/build/bin/llama-server \
        -m /mnt/82F4CC78F4CC6FC9/lmodels/gemma-3-4b-it.Q5_K_S.gguf \
        --host 0.0.0.0 --port 8080 \
        --fit on --fit-ctx 4096 -c 50000 \
        --cache-type-k q8_0 --cache-type-v q8_0 -fa on \
        > "$SCRIPT_DIR/llama-server.log" 2>&1 < /dev/null &
    echo "     (╰┈➤ waiting for model to load)"
    sleep 3
    for i in $(seq 1 30); do
        if curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
            echo "  ✅ llama-server ready"
            break
        fi
        sleep 2
    done
    if ! curl -sf http://localhost:8080/v1/models > /dev/null 2>&1; then
        echo "  ❌ llama-server failed to start — check llama-server.log"
        exit 1
    fi
fi

# ── 2. Redis ──────────────────────────────────────────────────────
if redis-cli -h localhost ping 2>/dev/null | grep -q PONG; then
    echo "  ✅ Redis ready on :6379"
else
    echo "  ⚠️  Redis not responding — is it running?"
fi

# ── 3. PostgreSQL ────────────────────────────────────────────────
if pg_isready -h localhost -q 2>/dev/null; then
    echo "  ✅ PostgreSQL ready on :5432"
else
    echo "  ⚠️  PostgreSQL not responding — is it running?"
fi

# ── 4. Backend ───────────────────────────────────────────────────
echo "  🔄 Starting backend..."
pkill -f "uvicorn src.main_refactored" 2>/dev/null || true
sleep 1
cd "$SCRIPT_DIR/backend"
setsid .venv/bin/uvicorn src.main_refactored:app --host 0.0.0.0 --port 8000 > "$SCRIPT_DIR/backend.log" 2>&1 < /dev/null &
for i in $(seq 1 15); do
    if curl -sf http://localhost:8000/health > /dev/null 2>&1; then
        echo "  ✅ Backend ready on :8000"
        break
    fi
    sleep 1
done
if ! curl -sf http://localhost:8000/health > /dev/null 2>&1; then
    echo "  ❌ Backend failed to start — check backend.log"
    exit 1
fi

# ── 5. Worker ─────────────────────────────────────────────────────
echo "  🔄 Starting worker..."
pkill -f "arq src.workers.tasks.WorkerSettings" 2>/dev/null || true
sleep 1
cd "$SCRIPT_DIR/backend"
setsid .venv/bin/python -m arq src.workers.tasks.WorkerSettings > "$SCRIPT_DIR/worker.log" 2>&1 < /dev/null &
sleep 3
if pgrep -f "arq src.workers.tasks.WorkerSettings" > /dev/null 2>&1; then
    echo "  ✅ Worker started"
else
    echo "  ⚠️  Worker may not have started — check worker.log"
fi

# ── 6. Frontend ──────────────────────────────────────────────────
echo "  🔄 Starting frontend..."
pkill -f "next dev" 2>/dev/null || true
sleep 1
cd "$SCRIPT_DIR/frontend"
nohup npm run dev > /tmp/frontend.log 2>&1 &
for i in $(seq 1 20); do
    if curl -sf http://localhost:3107 > /dev/null 2>&1; then
        echo "  ✅ Frontend ready on :3107"
        break
    fi
    sleep 1
done
if ! curl -sf http://localhost:3107 > /dev/null 2>&1; then
    echo "  ⚠️  Frontend may not be ready — check /tmp/frontend.log"
fi

cd "$SCRIPT_DIR"

echo ""
# ── 7. Default user ──────────────────────────────────────────────
"$SCRIPT_DIR/setup-default-user.sh" 2>/dev/null || true

echo "═══════════════════════════════════════════"
echo "  All services started!"
echo ""
echo "  Frontend  →  http://localhost:3107"
echo "  YouTube   →  http://localhost:3107/youtube"
echo "  Backend   →  http://localhost:8000"
echo "  API docs  →  http://localhost:8000/docs"
echo "═══════════════════════════════════════════"
echo ""
echo "To stop:  ./stop-local.sh"
echo "Cleanup:  ./cleanup-old-videos.py --dry-run"
echo "Logs:     $SCRIPT_DIR/*.log  and  /tmp/frontend.log"
