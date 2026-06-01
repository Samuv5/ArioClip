#!/bin/bash
# Stop all SupoClip services
echo "=== Stopping SupoClip ==="
pkill -f "uvicorn src.main_refactored" 2>/dev/null && echo "  ✅ Backend stopped" || echo "  ⚪ Backend not running"
pkill -f "arq src.workers.tasks.WorkerSettings" 2>/dev/null && echo "  ✅ Worker stopped" || echo "  ⚪ Worker not running"
pkill -f "next dev" 2>/dev/null && echo "  ✅ Frontend stopped" || echo "  ⚪ Frontend not running"
# llama-server is managed on-demand by the worker (stopped before whisperx, restarted after).
# It will naturally exit when no requests arrive, but you can force-stop it:
# pkill -f "llama-server" 2>/dev/null && echo "  ✅ llama-server stopped"
echo "=== Done ==="
