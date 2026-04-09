#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync_index.py - Synchronize brain.md index with actual memory files.

This script ensures that the brain.md index and statistics accurately reflect
the actual memory files on disk. It fixes inconsistencies between the index
and real files, which is the root cause of incorrect statistics.
"""

import os
import sys
import argparse
from pathlib import Path
from datetime import datetime

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from project_utils import (
    resolve_brain_path,
    read_file_safely,
    _collect_memory_statistics,
    _refresh_brain_status,
    _count_memory_index_rows,
)


def sync_brain_index(brain_path: str | Path, dry_run: bool = False) -> dict:
    """
    Synchronize brain.md index with actual memory files.
    
    Args:
        brain_path: Path to brain.md file
        dry_run: If True, only show changes without modifying the file
        
    Returns:
        dict: Synchronization result statistics
    """
    brain_path = Path(brain_path)
    if not brain_path.exists():
        return {"success": False, "error": "brain.md not found"}
    
    content = read_file_safely(brain_path)
    if not content:
        return {"success": False, "error": "Failed to read brain.md"}
    
    # Get real statistics from disk
    stats = _collect_memory_statistics(brain_path)
    
    # Count current index entries
    index_count = _count_memory_index_rows(content)
    
    # Refresh the entire brain status and category index
    updated_content = _refresh_brain_status(content, brain_path=brain_path)
    
    # Calculate changes
    changes = {
        "before": {
            "index_count": index_count,
            "total_in_index": int(
                [line.split("|")[2].strip() for line in content.splitlines() 
                 if "总记忆数" in line and line.startswith("|")][0]
                if any("总记忆数" in line and line.startswith("|") for line in content.splitlines())
                else 0
            )
        },
        "after": {
            "total_real": stats["total_count"],
            "category_counts": stats["category_counts"],
        },
        "inconsistencies_found": index_count != stats["standalone_count"],
        "changes_made": updated_content != content,
    }
    
    # Save changes if not dry run
    if not dry_run and changes["changes_made"]:
        with open(brain_path, "w", encoding="utf-8") as f:
            f.write(updated_content)
    
    return {
        "success": True,
        **changes,
        "stats": stats,
    }


def main():
    parser = argparse.ArgumentParser(description="Synchronize brain.md index with actual memory files")
    parser.add_argument(
        "--brain-path",
        type=str,
        help="Explicit path to brain.md file (optional, auto-detected if not provided)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show changes without modifying the file",
    )
    parser.add_argument(
        "--auto-fix",
        action="store_true",
        help="Automatically fix inconsistencies (default: True)",
    )
    
    args = parser.parse_args()
    
    # Resolve brain path
    brain_path = resolve_brain_path(explicit_path=args.brain_path)
    
    print(f"📊 Synchronizing brain index at: {brain_path}")
    print("=" * 60)
    
    result = sync_brain_index(brain_path, dry_run=args.dry_run or not args.auto_fix)
    
    if not result["success"]:
        print(f"❌ Error: {result['error']}")
        return 1
    
    # Print results
    stats = result["stats"]
    
    print(f"📈 Real memory statistics:")
    print(f"  Total memories: {stats['total_count']}")
    print(f"  Standalone memories: {stats['standalone_count']}")
    print(f"  Fragment memories: {stats['fragment_count']}")
    print(f"  Extra docs: {stats['docs_extra_count']}")
    print()
    
    print(f"📋 Category breakdown:")
    for cat, count in stats["category_counts"].items():
        print(f"  {cat:<10}: {count}")
    print()
    
    if result["inconsistencies_found"]:
        print(f"⚠️ Inconsistencies detected:")
        print(f"  Index entries: {result['before']['index_count']}")
        print(f"  Actual files: {stats['standalone_count']}")
        print()
    
    if result["changes_made"]:
        if args.dry_run:
            print("✅ Changes detected (dry run, no files modified)")
        else:
            print("✅ Index synchronized successfully!")
    else:
        print("✅ Index is already consistent with actual files")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
