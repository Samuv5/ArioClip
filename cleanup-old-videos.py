#!/usr/bin/env python3
"""
Cleanup old video files not referenced by active tasks.
Usage:
  ./cleanup-old-videos.py              # delete files for tasks >7 days old
  ./cleanup-old-videos.py --days 1     # delete files for tasks >1 day old
  ./cleanup-old-videos.py --dry-run    # preview only
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

try:
    import asyncpg
except ImportError:
    # fallback to psycopg2 or subprocess
    import subprocess

    def _get_active_refs(days: int) -> set[str]:
        sql = f"""
            SELECT s.url FROM sources s
            JOIN tasks t ON t.source_id = s.id
            WHERE t.status != 'deleted'
              AND t.created_at > CURRENT_TIMESTAMP - INTERVAL '{days} days'
        """
        result = subprocess.run(
            [
                "psql",
                "-h", "localhost",
                "-U", "supoclip",
                "-d", "supoclip",
                "-t", "-A",
                "-c", sql,
            ],
            capture_output=True, text=True,
            env={**os.environ, "PGPASSWORD": "supoclip_password"},
        )
        refs: set[str] = set()
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            refs.add(line)
        return refs
else:
    async def _get_active_refs_async(days: int) -> set[str]:
        conn = await asyncpg.connect(
            user="supoclip",
            password="supoclip_password",
            host="localhost",
            database="supoclip",
        )
        try:
            rows = await conn.fetch(
                """
                SELECT s.url FROM sources s
                JOIN tasks t ON t.source_id = s.id
                WHERE t.status != 'deleted'
                  AND t.created_at > CURRENT_TIMESTAMP - $1::interval
                """,
                timedelta(days=days),
            )
            return {row["url"] for row in rows}
        finally:
            await conn.close()

    def _get_active_refs(days: int) -> set[str]:
        import asyncio
        return asyncio.run(_get_active_refs_async(days))


def _video_id_from_url(url: str) -> str | None:
    # YouTube: https://www.youtube.com/watch?v=XXXX
    m = re.search(r"[?&]v=([^&]+)", url)
    if m:
        return m.group(1)
    # Upload: upload://UUID.mp4
    m = re.match(r"upload://(.+)\.mp4", url)
    if m:
        return m.group(1)
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Clean up old video files")
    parser.add_argument("--days", type=int, default=7, help="Age threshold in days (default: 7)")
    parser.add_argument("--dry-run", action="store_true", help="Preview only, no deletion")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    uploads_dir = script_dir / "data" / "uploads"
    outputs_dir = script_dir / "data" / "outputs"
    clips_dir = script_dir / "data" / "clips"

    print(f"Fetching active video refs (created within {args.days} days)...")
    active_urls = _get_active_refs(args.days)
    active_ids: set[str] = set()
    for url in active_urls:
        vid = _video_id_from_url(url)
        if vid:
            active_ids.add(vid)
    print(f"  Found {len(active_ids)} active video IDs")

    total_deleted = 0
    now = datetime.now(timezone.utc)

    for label, directory in [("Uploads", uploads_dir), ("Outputs", outputs_dir), ("Clips", clips_dir)]:
        if not directory.exists():
            print(f"\n=== {label} ({directory}) ===")
            print("  (directory not found)")
            continue

        print(f"\n=== {label} ({directory}) ===")
        count = 0
        for f in sorted(directory.iterdir()):
            if not f.is_file():
                continue
            # skip non-video/audio/cache files
            if f.suffix.lower() not in (".mp4", ".mkv", ".webm", ".mov", ".mp3", ".json"):
                continue

            fname = f.name
            base = fname.split(".")[0]

            # Check if the base (or first part before _) is an active video ID
            is_active = base in active_ids or base.split("_")[0] in active_ids

            if is_active:
                continue

            # Check age
            mtime = datetime.fromtimestamp(f.stat().st_mtime, tz=timezone.utc)
            age_days = (now - mtime).days
            if age_days < args.days:
                continue

            if args.dry_run:
                print(f"  [DRY-RUN] would delete: {fname} ({age_days}d old)")
            else:
                f.unlink()
                print(f"  deleted: {fname} ({age_days}d old)")
            count += 1

        if count == 0:
            print("  (nothing to clean)")
        total_deleted += count

    print()
    print("═" * 50)
    if args.dry_run:
        print(f"  Dry-run complete — {total_deleted} files would be deleted")
    else:
        print(f"  Cleanup complete — {total_deleted} files deleted")
    print("═" * 50)


if __name__ == "__main__":
    main()
