#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
refresh_brain.py

Post-write brain refresh helper:
1) optional session summary update
2) compact context rebuild for next reasoning step
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from context_pack import build_context_pack
from load_brain import load_brain
from memory_defaults import (
    POST_WRITE_CONTEXT_MAX_CHARS_DEFAULT,
    SESSION_SUMMARY_LOOKBACK_HOURS_DEFAULT,
    SESSION_SUMMARY_MAX_MEMORIES_DEFAULT,
    SESSION_SUMMARY_MAX_ROWS_DEFAULT,
)
from project_utils import resolve_brain_path, update_cue_network
from session_summary import (
    build_session_summary,
    collect_recent_memories,
    ensure_profile_skeleton,
    read_file_safely,
    upsert_session_summary,
)


def refresh_session_summary(
    brain_path: Path,
    *,
    lookback_hours: int,
    max_memories: int,
    session_label: str | None = None,
    dry_run: bool = False,
) -> dict:
    memories = collect_recent_memories(brain_path, lookback_hours, max_memories)
    summary = build_session_summary(memories, session_label=session_label)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    summary_cell = summary["summary_text"].replace("|", "/").replace("\n", " ").strip()
    row = f"| {now_iso} | {session_id} | {summary['memory_count']} | {summary_cell} |"

    profile_path = brain_path.parent / "user_profile.md"
    old_profile = read_file_safely(str(profile_path)) or ""
    old_profile = ensure_profile_skeleton(old_profile, now_iso)
    new_profile = upsert_session_summary(old_profile, row=row, max_rows=SESSION_SUMMARY_MAX_ROWS_DEFAULT)

    if not dry_run:
        profile_path.write_text(new_profile, encoding="utf-8")

    return {
        "updated": not dry_run,
        "profile_path": str(profile_path),
        "session_id": session_id,
        "lookback_hours": lookback_hours,
        "memory_count": summary["memory_count"],
        "top_signals": summary["top_signals"],
        "top_topics": summary["top_topics"],
        "summary_text": summary["summary_text"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Refresh memory brain after write and emit compact context")
    parser.add_argument("--brain-path", type=str, help="path to brain.md")
    parser.add_argument("--project-root", type=str, help="project root for brain discovery")
    parser.add_argument(
        "--max-chars",
        type=int,
        default=POST_WRITE_CONTEXT_MAX_CHARS_DEFAULT,
        help="max chars for returned compact context",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=SESSION_SUMMARY_LOOKBACK_HOURS_DEFAULT,
        help="time window for session summary update",
    )
    parser.add_argument(
        "--max-memories",
        type=int,
        default=SESSION_SUMMARY_MAX_MEMORIES_DEFAULT,
        help="max recent memories considered by session summary",
    )
    parser.add_argument("--session-label", type=str, help="optional label to add in summary row")
    parser.add_argument("--skip-session-summary", action="store_true", help="skip updating session summary")
    parser.add_argument("--dry-run-summary", action="store_true", help="compute session summary but do not write")
    parser.add_argument("--format", choices=["json", "text"], default="json", help="output format")
    args = parser.parse_args()

    brain_path = (
        resolve_brain_path(explicit_path=args.brain_path)
        if args.brain_path
        else resolve_brain_path(start_path=args.project_root or os.getcwd())
    )
    load_brain(str(brain_path))
    # 统一刷新统计（总记忆数/类别索引等），确保与磁盘真实数据一致
    update_cue_network(str(brain_path))

    summary_result = None
    if not args.skip_session_summary:
        summary_result = refresh_session_summary(
            brain_path,
            lookback_hours=max(1, int(args.lookback_hours)),
            max_memories=max(1, int(args.max_memories)),
            session_label=args.session_label,
            dry_run=args.dry_run_summary,
        )

    pack = build_context_pack(brain_path, max_chars=max(300, int(args.max_chars)))
    output = {
        "status": "success",
        "brain_path": str(brain_path),
        "session_summary": summary_result,
        "context_pack": pack,
    }

    if args.format == "text":
        print(pack["context"])
        return
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
