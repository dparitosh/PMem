"""Inspect persisted import tasks under the runtime uploads folder."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path


def _task_dir(upload_dir: Path) -> Path:
    return upload_dir / ".import_tasks"


def inspect_tasks(upload_dir: Path) -> int:
    task_dir = _task_dir(upload_dir)
    print(f"Task store: {task_dir}")
    if not task_dir.exists():
        print("No task store directory found.")
        return 0

    task_files = sorted(task_dir.glob("*.json"))
    print(f"Stored tasks: {len(task_files)}")
    for task_file in task_files:
        try:
            task = json.loads(task_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  {task_file.name}: invalid JSON")
            continue
        modified = datetime.fromtimestamp(task_file.stat().st_mtime)
        print(
            "  {task_id} status={status} stage={stage} file={file} modified={modified}".format(
                task_id=task.get("task_id", task_file.stem),
                status=task.get("status", "?"),
                stage=task.get("current_stage", "?"),
                file=task.get("filename", "?"),
                modified=modified.isoformat(timespec="seconds"),
            )
        )
        if task.get("error"):
            print(f"    error: {task['error']}")
    return 0


def cleanup_tasks(upload_dir: Path, older_than_days: int, yes: bool) -> int:
    if not yes:
        raise SystemExit("Refusing to delete task files without --yes.")

    task_dir = _task_dir(upload_dir)
    if not task_dir.exists():
        return 0
    cutoff = datetime.now() - timedelta(days=older_than_days)
    removed = 0
    for task_file in task_dir.glob("*.json"):
        if datetime.fromtimestamp(task_file.stat().st_mtime) < cutoff:
            task_file.unlink()
            removed += 1
            print(f"Removed {task_file}")
    print(f"Removed {removed} task files.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upload-dir", type=Path, default=Path("uploads"))
    parser.add_argument("--cleanup-older-than-days", type=int)
    parser.add_argument("--yes", action="store_true")
    args = parser.parse_args()

    if args.cleanup_older_than_days is not None:
        return cleanup_tasks(args.upload_dir, args.cleanup_older_than_days, args.yes)
    return inspect_tasks(args.upload_dir)


if __name__ == "__main__":
    raise SystemExit(main())

