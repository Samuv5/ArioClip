#!/bin/bash
# Cleanup old video files not associated with active tasks
# Usage: ./cleanup-old-videos.sh [--dry-run] [--days 7]
#   --dry-run  : only list files that would be deleted
#   --days N   : delete files for tasks older than N days (default: 7)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DRY_RUN=false
DAYS=7

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run) DRY_RUN=true; shift ;;
    --days) DAYS="$2"; shift 2 ;;
    *) echo "Unknown: $1"; exit 1 ;;
  esac
done

UPLOADS_DIR="${SCRIPT_DIR}/data/uploads"
OUTPUTS_DIR="${SCRIPT_DIR}/data/outputs"
CLIPS_DIR="${SCRIPT_DIR}/data/clips"

DB_USER="supoclip"
DB_PASS="supoclip_password"
DB_NAME="supoclip"
DB_HOST="localhost"

TOTAL_DELETED=0

clean_dir() {
  local dir="$1" label="$2"
  if [[ ! -d "$dir" ]]; then
    echo "  (dir $dir not found)"
    return
  fi
  echo ""
  echo "=== $label ($dir) ==="

  # Get filenames referenced by active (non-deleted) tasks, excluding extensions
  PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -A \
    -c "SELECT s.filename FROM sources s JOIN tasks t ON t.source_id = s.id WHERE t.status != 'deleted';" \
    | sort -u > /tmp/active_files.txt

  local count=0
  for f in "$dir"/*; do
    [[ -f "$f" ]] || continue
    fname="$(basename "$f")"
    base="${fname%.*}"

    # Check if any active source filename starts with this base
    if grep -q "^${base}" /tmp/active_files.txt 2>/dev/null; then
      continue
    fi

    # Also check if the file is a clip for an active task
    # Clip files are named with task UUIDs; check via DB
    if [[ "$label" == "Clips" ]]; then
      task_id="${base%%_*}"  # clip filename format: <task_id>_<index>.mp4
      if [[ "$task_id" =~ ^[0-9a-f-]+$ ]]; then
        active=$(PGPASSWORD="$DB_PASS" psql -h "$DB_HOST" -U "$DB_USER" -d "$DB_NAME" -t -A \
          -c "SELECT 1 FROM tasks WHERE id='$task_id' AND status != 'deleted';")
        if [[ "$active" == "1" ]]; then
          continue
        fi
      fi
    fi

    # Check age
    age=$(( ($(date +%s) - $(stat -c %Y "$f")) / 86400 ))
    if [[ $age -lt $DAYS ]]; then
      continue
    fi

    if $DRY_RUN; then
      echo "  [DRY-RUN] would delete: $fname (${age}d old)"
    else
      rm -f "$f"
      echo "  deleted: $fname (${age}d old)"
    fi
    ((count++))
  done

  TOTAL_DELETED=$((TOTAL_DELETED + count))
  if [[ $count -eq 0 ]]; then
    echo "  (nothing to clean)"
  fi
}

clean_dir "$UPLOADS_DIR" "Uploads"
clean_dir "$OUTPUTS_DIR" "Outputs"
clean_dir "$CLIPS_DIR" "Clips"

echo ""
echo "═══════════════════════════════════════"
if $DRY_RUN; then
  echo "  Dry-run complete — $TOTAL_DELETED files would be deleted"
else
  echo "  Cleanup complete — $TOTAL_DELETED files deleted"
fi
echo "═══════════════════════════════════════"
