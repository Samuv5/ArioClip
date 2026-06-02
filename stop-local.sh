#!/bin/bash
# Stop all SupoClip local services
echo "=== Stopping ArioClip (Local Mode) ==="

pkill -f "uvicorn src.main" 2>/dev/null && echo "  ✅ Backend stopped" || echo "  ⚪ Backend not running"
pkill -f "arq src.workers.tasks.WorkerSettings" 2>/dev/null && echo "  ✅ Worker stopped" || echo "  ⚪ Worker not running"
pkill -f "next.*3107" 2>/dev/null && echo "  ✅ Frontend stopped" || echo "  ⚪ Frontend not running"
# llama-server is managed on-demand; uncomment to force-stop:
# pkill -f "llama-server" 2>/dev/null && echo "  ✅ llama-server stopped" || echo "  ⚪ llama-server not running"

echo "=== Done ==="
