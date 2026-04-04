#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_summary.py - summarize recent memories into a session preference snapshot.

Usage:
  python scripts/session_summary.py --lookback-hours 8
  python scripts/session_summary.py --session-label "auth refactor"
  python scripts/session_summary.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from create_memory import extract_preference_signals, normalize_keywords, read_file_safely
from load_brain import load_brain
from memory_defaults import (
    SESSION_SUMMARY_LOOKBACK_HOURS_DEFAULT,
    SESSION_SUMMARY_MAX_MEMORIES_DEFAULT,
    SESSION_SUMMARY_MAX_ROWS_DEFAULT,
)
from project_utils import resolve_brain_path


def parse_frontmatter_and_body(text: str) -> tuple[dict, str]:
    if not text:
        return {}, ""
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n?", text, flags=re.DOTALL)
    if not m:
        return {}, text
    yaml_part = m.group(1)
    body = text[m.end() :]
    meta = {}
    for line in yaml_part.splitlines():
        if ":" not in line:
            continue
        k, v = line.split(":", 1)
        meta[k.strip()] = v.strip()
    return meta, body


def parse_keywords(value: str) -> list[str]:
    if not value:
        return []
    m = re.match(r"^\[(.*)\]$", value.strip())
    if m:
        return normalize_keywords(m.group(1))
    return normalize_keywords(value)


def parse_title(meta: dict, body: str, fallback: str) -> str:
    title = meta.get("title", "").strip()
    if title:
        return title
    m = re.search(r"^#\s+(.+)$", body or "", flags=re.MULTILINE)
    if m:
        return m.group(1).strip()
    return fallback


def collect_recent_memories(brain_path: Path, lookback_hours: int, max_memories: int) -> list[dict]:
    memory_root = brain_path.parent / "memories"
    if not memory_root.exists():
        return []

    cutoff = datetime.now(timezone.utc) - timedelta(hours=max(1, lookback_hours))
    entries = []
    for file_path in memory_root.rglob("*.md"):
        try:
            mtime = datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc)
        except OSError:
            continue
        if mtime < cutoff:
            continue

        raw = read_file_safely(str(file_path)) or ""
        meta, body = parse_frontmatter_and_body(raw)
        title = parse_title(meta, body, file_path.stem)
        keywords = parse_keywords(meta.get("keywords", ""))
        memory_id = meta.get("id", file_path.stem)
        entries.append(
            {
                "id": memory_id,
                "title": title,
                "keywords": keywords,
                "body": body,
                "path": str(file_path),
                "mtime": mtime,
            }
        )

    entries.sort(key=lambda x: x["mtime"], reverse=True)
    return entries[: max(1, max_memories)]


def extract_session_rows(content: str) -> list[str]:
    if not content:
        return []
    pattern = (
        r"## Session Summaries\s*\n"
        r"\| Time \| Session ID \| Memories \| Summary \|\n"
        r"\|[-| ]+\|\n"
        r"((?:\|.*\|\n?)*)"
    )
    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        return []
    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if line.startswith("|") and line.count("|") >= 5 and "| - | - | - | - |" not in line:
            rows.append(line)
    return rows[:20]


def ensure_profile_skeleton(content: str, now_iso: str) -> str:
    if content and "# User Preference Profile" in content:
        return content
    return "\n".join(
        [
            "---",
            "version: 1",
            f"updated_at: {now_iso}",
            "total_signals: 0",
            "last_memory_id: ",
            "---",
            "",
            "# User Preference Profile",
            "",
            "## Stable Preferences (>=3)",
            "- [0] None yet",
            "",
            "## Emerging Preferences (<3)",
            "- [0] None yet",
            "",
            "## Recent Signals",
            "| Time | Memory ID | Title | Signal |",
            "|------|-----------|-------|--------|",
            "| - | - | - | - |",
            "",
        ]
    )


def upsert_session_summary(profile_content: str, row: str, max_rows: int = SESSION_SUMMARY_MAX_ROWS_DEFAULT) -> str:
    profile_content = profile_content.rstrip() + "\n"
    existing_rows = extract_session_rows(profile_content)
    rows = [row] + [r for r in existing_rows if r != row]
    rows = rows[:max_rows]

    section = "\n".join(
        [
            "## Session Summaries",
            "| Time | Session ID | Memories | Summary |",
            "|------|------------|----------|---------|",
            *(rows if rows else ["| - | - | - | - |"]),
            "",
        ]
    )

    pattern = (
        r"## Session Summaries\s*\n"
        r"\| Time \| Session ID \| Memories \| Summary \|\n"
        r"\|[-| ]+\|\n"
        r"(?:\|.*\|\n?)*"
    )
    if re.search(pattern, profile_content, flags=re.MULTILINE):
        return re.sub(pattern, section, profile_content, flags=re.MULTILINE)
    return profile_content + "\n" + section


def build_session_summary(memories: list[dict], session_label: str | None = None) -> dict:
    signal_counts = Counter()
    topic_counts = Counter()

    for mem in memories:
        signals = extract_preference_signals(mem["title"], mem["body"], mem["keywords"])
        for s in signals:
            signal_counts[s] += 1
        for kw in mem["keywords"]:
            topic_counts[kw] += 1

    top_signals = [s for s, _ in signal_counts.most_common(4)]
    top_topics = [t for t, _ in topic_counts.most_common(4)]
    parts = []
    if session_label:
        parts.append(f"label: {session_label}")
    if top_signals:
        parts.append("prefs: " + "; ".join(top_signals))
    if top_topics:
        parts.append("topics: " + ", ".join(top_topics))
    if not parts:
        parts.append("no strong new preference signal")

    return {
        "memory_count": len(memories),
        "top_signals": top_signals,
        "top_topics": top_topics,
        "summary_text": " ; ".join(parts),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize recent memory entries into a session preference summary")
    parser.add_argument("--brain-path", type=str, help="path to brain.md")
    parser.add_argument("--project-root", type=str, help="project root for brain discovery")
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=SESSION_SUMMARY_LOOKBACK_HOURS_DEFAULT,
        help="only summarize memories within this time window",
    )
    parser.add_argument(
        "--max-memories",
        type=int,
        default=SESSION_SUMMARY_MAX_MEMORIES_DEFAULT,
        help="max recent memories to include",
    )
    parser.add_argument("--session-id", type=str, help="optional explicit session id")
    parser.add_argument("--session-label", type=str, help="optional short label for this session")
    parser.add_argument("--dry-run", action="store_true", help="do not write file, only print result")
    args = parser.parse_args()

    brain_path = (
        resolve_brain_path(explicit_path=args.brain_path)
        if args.brain_path
        else resolve_brain_path(start_path=args.project_root or os.getcwd())
    )
    load_brain(str(brain_path))

    memories = collect_recent_memories(brain_path, args.lookback_hours, args.max_memories)
    summary = build_session_summary(memories, session_label=args.session_label)
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    session_id = args.session_id or f"sess_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    summary_cell = summary["summary_text"].replace("|", "/").replace("\n", " ").strip()
    row = f"| {now_iso} | {session_id} | {summary['memory_count']} | {summary_cell} |"

    profile_path = brain_path.parent / "user_profile.md"
    old_profile = read_file_safely(str(profile_path)) or ""
    old_profile = ensure_profile_skeleton(old_profile, now_iso)
    new_profile = upsert_session_summary(old_profile, row=row, max_rows=SESSION_SUMMARY_MAX_ROWS_DEFAULT)

    if not args.dry_run:
        with open(profile_path, "w", encoding="utf-8") as f:
            f.write(new_profile)

    print(
        json.dumps(
            {
                "status": "success",
                "brain_path": str(brain_path),
                "profile_path": str(profile_path),
                "session_id": session_id,
                "lookback_hours": args.lookback_hours,
                "memory_count": summary["memory_count"],
                "top_signals": summary["top_signals"],
                "top_topics": summary["top_topics"],
                "summary_text": summary["summary_text"],
                "written": not args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
