#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
delete_memory.py - Delete memory and synchronize index.

This script handles memory deletion, including:
- Deleting standalone memory files
- Removing entries from brain.md index
- Automatically synchronizing category counts and statistics
- Supporting both memory ID and file path as input
"""

import os
import sys
import argparse
import re
from pathlib import Path

# Add the scripts directory to the path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from project_utils import (
    resolve_brain_path,
    get_memory_dir,
    read_file_safely,
    DEFAULT_CATEGORIES,
)
from sync_index import sync_brain_index


def find_memory_by_id(brain_path: Path, memory_id: str) -> Path | None:
    """
    Find memory file by ID.
    
    Args:
        brain_path: Path to brain.md
        memory_id: Memory ID to find
        
    Returns:
        Path | None: Path to memory file if found, None otherwise
    """
    memories_dir = get_memory_dir(brain_path)
    
    # Search in all category directories
    for cat in DEFAULT_CATEGORIES:
        cat_dir = memories_dir / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.rglob("*.md"):
            if f.is_file() and memory_id in f.name:
                # Check file content to confirm ID
                content = read_file_safely(f)
                if content and re.search(rf"^id:\s*{re.escape(memory_id)}\s*$", content, flags=re.MULTILINE):
                    return f
    
    # Also check archive directory
    archive_dir = brain_path.parent / "archive"
    if archive_dir.exists():
        for f in archive_dir.rglob("*.md"):
            if f.is_file() and memory_id in f.name:
                content = read_file_safely(f)
                if content and re.search(rf"^id:\s*{re.escape(memory_id)}\s*$", content, flags=re.MULTILINE):
                    return f
    
    return None


def remove_memory_from_index(brain_path: Path, memory_id: str) -> bool:
    """
    Remove memory entry from brain.md index.
    
    Args:
        brain_path: Path to brain.md
        memory_id: Memory ID to remove
        
    Returns:
        bool: True if removed successfully
    """
    if not brain_path.exists():
        return False
    
    content = read_file_safely(brain_path)
    if not content:
        return False
    
    # Remove from memory index table
    updated_content = re.sub(
        rf"^\|\s*{re.escape(memory_id)}\s*\|.*$\n?", 
        "", 
        content, 
        flags=re.MULTILINE
    )
    
    # Remove from recent activity
    updated_content = re.sub(
        rf"^\|[^\|]*\|\s*delete\s*\|\s*{re.escape(memory_id)}\s*\|.*$\n?",
        "",
        updated_content,
        flags=re.MULTILINE
    )
    
    if updated_content == content:
        return False
    
    with open(brain_path, "w", encoding="utf-8") as f:
        f.write(updated_content)
    
    return True


def delete_memory(
    brain_path: Path, 
    memory_identifier: str, 
    dry_run: bool = False,
    archive: bool = False
) -> dict:
    """
    Delete a memory.
    
    Args:
        brain_path: Path to brain.md
        memory_identifier: Memory ID or file path
        dry_run: If True, only show changes without modifying
        archive: If True, move to archive instead of deleting
        
    Returns:
        dict: Deletion result
    """
    # Check if identifier is a file path
    memory_path = Path(memory_identifier)
    if memory_path.exists() and memory_path.is_file() and memory_path.suffix == ".md":
        # Verify it's a memory file
        content = read_file_safely(memory_path)
        if not content or "---" not in content or "id:" not in content:
            return {"success": False, "error": "File is not a valid memory file"}
        
        # Extract ID from file
        id_match = re.search(r"^id:\s*(\S+)\s*$", content, flags=re.MULTILINE)
        if not id_match:
            return {"success": False, "error": "Could not find memory ID in file"}
        memory_id = id_match.group(1)
    else:
        # Treat as memory ID
        memory_id = memory_identifier
        memory_path = find_memory_by_id(brain_path, memory_id)
        if not memory_path:
            return {"success": False, "error": f"Memory with ID '{memory_id}' not found"}
    
    result = {
        "success": True,
        "memory_id": memory_id,
        "memory_path": str(memory_path),
        "dry_run": dry_run,
        "archived": archive,
    }
    
    if dry_run:
        result["message"] = f"Would {'archive' if archive else 'delete'} memory {memory_id} at {memory_path}"
        return result
    
    # Perform delete/archive
    if archive:
        archive_dir = brain_path.parent / "archive"
        archive_dir.mkdir(parents=True, exist_ok=True)
        target_path = archive_dir / memory_path.name
        os.rename(str(memory_path), str(target_path))
        result["archive_path"] = str(target_path)
    else:
        memory_path.unlink()
    
    # Remove from index
    index_updated = remove_memory_from_index(brain_path, memory_id)
    result["index_updated"] = index_updated
    
    # Sync index to update statistics
    sync_result = sync_brain_index(brain_path)
    result["index_synced"] = sync_result.get("success", False)
    result["stats"] = sync_result.get("stats", {})
    
    return result


def main():
    parser = argparse.ArgumentParser(description="Delete memory and synchronize index")
    parser.add_argument(
        "memory",
        type=str,
        help="Memory ID or path to memory file",
    )
    parser.add_argument(
        "--brain-path",
        type=str,
        help="Explicit path to brain.md file (optional, auto-detected if not provided)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only show changes without modifying files",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Move to archive instead of permanently deleting",
    )
    
    args = parser.parse_args()
    
    # Resolve brain path
    brain_path = resolve_brain_path(explicit_path=args.brain_path)
    
    print(f"🗑️ Deleting memory: {args.memory}")
    print(f"📍 Brain location: {brain_path}")
    print("=" * 60)
    
    result = delete_memory(brain_path, args.memory, dry_run=args.dry_run, archive=args.archive)
    
    if not result["success"]:
        print(f"❌ Error: {result['error']}")
        return 1
    
    if result["dry_run"]:
        print(f"✅ {result['message']}")
        return 0
    
    if result["archived"]:
        print(f"✅ Memory archived successfully:")
        print(f"  ID: {result['memory_id']}")
        print(f"  Archived to: {result['archive_path']}")
    else:
        print(f"✅ Memory deleted successfully:")
        print(f"  ID: {result['memory_id']}")
        print(f"  Deleted from: {result['memory_path']}")
    
    if result["index_updated"]:
        print(f"✅ Index entry removed")
    
    if result["index_synced"]:
        print(f"✅ Index synchronized, statistics updated")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
