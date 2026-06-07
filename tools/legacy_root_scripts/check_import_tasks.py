#!/usr/bin/env python3
"""
Diagnostic script to check import task storage and recover lost tasks
"""

import json
import os
from pathlib import Path
from datetime import datetime

# Define paths
UPLOAD_DIR = Path(__file__).parent / "uploads"
TASK_STORE_DIR = UPLOAD_DIR / ".import_tasks"

def check_task_store():
    """Check what tasks are stored on disk"""
    print("=" * 60)
    print("IMPORT TASK STORAGE DIAGNOSTICS")
    print("=" * 60)
    
    print(f"\n📁 Task Store Location: {TASK_STORE_DIR}")
    print(f"✓ Directory exists: {TASK_STORE_DIR.exists()}")
    
    if not TASK_STORE_DIR.exists():
        print("⚠️  Task store directory does not exist. Creating...")
        TASK_STORE_DIR.mkdir(parents=True, exist_ok=True)
        print("✓ Created task store directory")
        return
    
    # List all task files
    task_files = list(TASK_STORE_DIR.glob("*.json"))
    print(f"\n📊 Total stored tasks: {len(task_files)}")
    
    if not task_files:
        print("❌ No tasks found in storage")
        return
    
    print("\n" + "=" * 60)
    print("STORED TASKS:")
    print("=" * 60)
    
    for task_file in sorted(task_files):
        try:
            with open(task_file, 'r') as f:
                task_data = json.load(f)
            
            task_id = task_data.get('task_id', 'unknown')
            status = task_data.get('status', 'unknown')
            filename = task_data.get('filename', 'unknown')
            current_stage = task_data.get('current_stage', 'unknown')
            error = task_data.get('error', None)
            
            print(f"\n📋 Task ID: {task_id}")
            print(f"   Status: {status}")
            print(f"   Stage: {current_stage}")
            print(f"   Filename: {filename}")
            print(f"   File Size: {task_file.stat().st_size} bytes")
            print(f"   Modified: {datetime.fromtimestamp(task_file.stat().st_mtime)}")
            
            if error:
                print(f"   ⚠️  Error: {error}")
            
            # Show parsed stats if available
            stats = task_data.get('stats', {})
            if stats:
                print(f"   Stats: {json.dumps(stats, indent=6)}")
                
        except json.JSONDecodeError:
            print(f"\n⚠️  {task_file.name}: Invalid JSON format")
        except Exception as e:
            print(f"\n⚠️  {task_file.name}: Error reading - {str(e)}")
    
    print("\n" + "=" * 60)
    print("RECOVERY OPTIONS:")
    print("=" * 60)
    print("""
1. If you see your task in the list above:
   - The task data is persisted and can be recovered
   - Restart the backend to reload these tasks
   
2. If your task is NOT in the list:
   - The upload was interrupted before the task was saved
   - You need to re-upload the file
   
3. To restart the backend:
   cd "c:\\Users\\2787399\\Desktop\\paritosh sir\\Depo_onto\\backend"
   python -m main
   
4. To clear old tasks (optional):
   Remove .json files from: {TASK_STORE_DIR}
""")

def cleanup_old_tasks(days=7):
    """Remove task files older than N days"""
    from time import time
    
    current_time = time()
    cutoff_time = current_time - (days * 86400)
    
    if not TASK_STORE_DIR.exists():
        return 0
    
    removed = 0
    for task_file in TASK_STORE_DIR.glob("*.json"):
        if task_file.stat().st_mtime < cutoff_time:
            try:
                task_file.unlink()
                removed += 1
                print(f"🗑️  Removed: {task_file.name}")
            except Exception as e:
                print(f"❌ Failed to remove {task_file.name}: {e}")
    
    return removed

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--cleanup":
        days = int(sys.argv[2]) if len(sys.argv) > 2 else 7
        print(f"🧹 Cleaning up tasks older than {days} days...")
        removed = cleanup_old_tasks(days)
        print(f"✓ Removed {removed} old task files")
    else:
        check_task_store()
