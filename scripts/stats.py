#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stats.py - Display memory system statistics.

This script provides accurate, real-time statistics about the memory system,
including total memory count, category distribution, keyword statistics, etc.
"""

import os
import sys
import argparse
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from project_utils import (
    resolve_brain_path,
    _collect_memory_statistics,
    _count_keyword_index_rows,
    _count_memory_index_rows,
)


def show_statistics(brain_path: str | Path) -> dict:
    """
    Show memory system statistics.
    
    Args:
        brain_path: Path to brain.md file
        
    Returns:
        dict: Statistics data
    """
    brain_path = Path(brain_path)
    
    # Get real statistics from disk
    stats = _collect_memory_statistics(brain_path)
    
    # Get index statistics
    index_count = _count_memory_index_rows(open(brain_path, encoding="utf-8").read()) if brain_path.exists() else 0
    keyword_count = _count_keyword_index_rows(open(brain_path, encoding="utf-8").read()) if brain_path.exists() else 0
    
    # Print formatted output
    print("🧠 Memory System Statistics")
    print("=" * 60)
    
    print(f"📍 Brain location: {brain_path}")
    print()
    
    print("📊 Overall Statistics:")
    print(f"  Total memories: {stats['total_count']:>4}")
    print(f"  Standalone memories: {stats['standalone_count']:>4}")
    print(f"  Fragment memories: {stats['fragment_count']:>4}")
    print(f"  Extra docs: {stats['docs_extra_count']:>4}")
    print(f"  Index entries: {index_count:>4}")
    print(f"  Total keywords: {keyword_count:>4}")
    print()
    
    print("📂 Category Distribution:")
    print("  " + "-" * 30)
    print(f"  | {'Category':<10} | {'Count':>5} | {'Type':<8} |")
    print("  " + "-" * 30)
    for cat, count in stats["category_counts"].items():
        cat_type = "左脑" if cat in ["coding", "config", "debug"] else "右脑" if cat in ["design", "docs"] else "双脑"
        print(f"  | {cat:<10} | {count:>5} | {cat_type:<8} |")
    print("  " + "-" * 30)
    print()
    
    # Check for inconsistencies
    if index_count != stats["standalone_count"]:
        print("⚠️ WARNING: Index inconsistency detected!")
        print(f"   Index has {index_count} entries but there are {stats['standalone_count']} actual files.")
        print("   Run 'python scripts/sync_index.py --auto-fix' to resolve this.")
        print()
    
    # Calculate storage usage
    memory_dir = brain_path.parent / "memories"
    if memory_dir.exists():
        total_size = sum(f.stat().st_size for f in memory_dir.rglob("*.md") if f.is_file())
        fragment_path = brain_path.parent / "fragment_memory.md"
        if fragment_path.exists():
            total_size += fragment_path.stat().st_size
        print(f"💾 Storage Usage:")
        print(f"  Total size: {total_size / 1024:.2f} KB")
        print()
    
    return {
        **stats,
        "index_count": index_count,
        "keyword_count": keyword_count,
        "inconsistent": index_count != stats["standalone_count"],
    }


def main():
    parser = argparse.ArgumentParser(description="Display memory system statistics")
    parser.add_argument(
        "--brain-path",
        type=str,
        help="Explicit path to brain.md file (optional, auto-detected if not provided)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output statistics in JSON format",
    )
    
    args = parser.parse_args()
    
    # Resolve brain path
    brain_path = resolve_brain_path(explicit_path=args.brain_path)
    
    stats = show_statistics(brain_path)
    
    if args.json:
        import json
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    
    if stats["inconsistent"]:
        return 2  # Inconsistency found
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
