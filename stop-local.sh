#!/bin/bash
# Stop all SupoClip services
echo "=== Stopping SupoClip ==="

pkill -f "uvicorn src.main_refactored" 2>/dev/null && echo "  ✅ Backend stopped" || echo "  ⚪ Backend not running"
pkill -f "arq src.workers.tasks.WorkerSettings" 2>/dev/null && echo "  ✅ Worker stopped" || echo "  ⚪ Worker not running"
pkill -f "next dev" 2>/dev/null && echo "  ✅ Frontend stopped" || echo "  ⚪ Frontend not running"
# Comment out the next line if you want to keep llama-server running
pkill -f "llama-server" 2>/dev/null && echo "  ✅ llama-server stopped" || echo "  ⚪ llama-server not running"

echo "=== Done ==="
echo ""
echo "Note: llama-server will be stopped/started automatically by the"
echo "worker during transcription (whisperx uses CUDA). Run this script"
echo "only when you want to fully shut down all services."
