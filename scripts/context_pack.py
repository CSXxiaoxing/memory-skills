#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
context_pack.py

Build a compact memory context for reasoning with a strict character budget.
This helps keep token usage low while retaining key memory signals.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from load_brain import load_brain
from memory_defaults import CONTEXT_PACK_MAX_CHARS_DEFAULT
from project_utils import resolve_brain_path


def read_file_safely(path: Path) -> str:
    if not path.exists():
        return ""
    for encoding in ["utf-8", "gbk", "gb2312", "latin1"]:
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return ""


def extract_profile_preferences(profile_text: str, max_items: int = 8) -> list[str]:
    if not profile_text:
        return []
    items = []
    for m in re.finditer(r"^\- \[(\d+)\] (.+)$", profile_text, flags=re.MULTILINE):
        count = int(m.group(1))
        text = m.group(2).strip()
        if count <= 0 or text.lower() in {"none yet", "none"}:
            continue
        items.append((count, text))
    items.sort(key=lambda x: (-x[0], x[1]))
    return [f"[{c}] {t}" for c, t in items[:max_items]]


def extract_session_summaries(profile_text: str, max_items: int = 4) -> list[str]:
    if not profile_text:
        return []
    pattern = (
        r"## Session Summaries\s*\n"
        r"\| Time \| Session ID \| Memories \| Summary \|\n"
        r"\|[-| ]+\|\n"
        r"((?:\|.*\|\n?)*)"
    )
    m = re.search(pattern, profile_text, flags=re.MULTILINE)
    if not m:
        return []
    out = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or "| - | - | - | - |" in line:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        ts, session_id, memories, summary = parts[:4]
        out.append(f"[{ts} | {session_id} | mem={memories}] {summary}")
        if len(out) >= max_items:
            break
    return out


def extract_lessons(lessons_text: str, max_items: int = 8) -> list[str]:
    if not lessons_text:
        return []
    lessons = []
    for m in re.finditer(r"^\- \[(\d+)\] (.+)$", lessons_text, flags=re.MULTILINE):
        count = int(m.group(1))
        text = m.group(2).strip()
        if count <= 0 or text.lower() in {"none yet", "none"}:
            continue
        lessons.append((count, text))
    lessons.sort(key=lambda x: (-x[0], x[1]))
    return [f"[{c}] {t}" for c, t in lessons[:max_items]]


def extract_fragment_notes(fragment_text: str, max_items: int = 6) -> list[str]:
    if not fragment_text:
        return []
    notes = []
    for m in re.finditer(r"^\- \[([^\]]+)\] \(score:(-?\d+)\) (.+)$", fragment_text, flags=re.MULTILINE):
        ts = m.group(1).strip()
        score = int(m.group(2))
        note = m.group(3).strip()
        notes.append((ts, score, note))
    notes = notes[:max_items]
    return [f"[{ts} | s={score}] {note}" for ts, score, note in notes]


def extract_recent_memory_index(brain_text: str, max_items: int = 8) -> list[str]:
    if not brain_text:
        return []
    rows = []
    for m in re.finditer(r"^\| (mem_[^|]+) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|", brain_text, flags=re.MULTILINE):
        mem_id, title, category, project = [x.strip() for x in m.groups()]
        rows.append(f"{mem_id}: {title} [{category}/{project}]")
    return rows[:max_items]


def build_context_lines(
    *,
    project_name: str,
    prefs: list[str],
    lessons: list[str],
    recent_memories: list[str],
    fragment_notes: list[str],
    session_summaries: list[str],
) -> list[str]:
    lines = [
        f"Project: {project_name}",
        "",
        "Reasoning rules:",
        "- prioritize lessons to avoid repeating mistakes",
        "- follow stable user preferences before style choices",
        "- use recent memories only when relevant",
        "",
        "User preferences:",
    ]
    lines.extend([f"- {x}" for x in (prefs or ["(none)"])])
    lines.extend(["", "Lessons to avoid repeating mistakes:"])
    lines.extend([f"- {x}" for x in (lessons or ["(none)"])])
    lines.extend(["", "Recent standalone memories:"])
    lines.extend([f"- {x}" for x in (recent_memories or ["(none)"])])
    lines.extend(["", "Recent session summaries:"])
    lines.extend([f"- {x}" for x in (session_summaries or ["(none)"])])
    lines.extend(["", "Recent fragment notes:"])
    lines.extend([f"- {x}" for x in (fragment_notes or ["(none)"])])
    return lines


def fit_to_max_chars(lines: list[str], max_chars: int) -> str:
    out = []
    cur = 0
    for line in lines:
        add = len(line) + 1
        if cur + add > max_chars:
            break
        out.append(line)
        cur += add
    text = "\n".join(out).strip()
    if not text:
        text = "No memory context available."
    return text


def build_context_pack(brain_path: Path, max_chars: int = CONTEXT_PACK_MAX_CHARS_DEFAULT) -> dict:
    brain_path = Path(brain_path)
    load_brain(str(brain_path))

    brain_text = read_file_safely(brain_path)
    brain_dir = brain_path.parent
    profile_text = read_file_safely(brain_dir / "user_profile.md")
    lessons_text = read_file_safely(brain_dir / "lessons_learned.md")
    fragment_text = read_file_safely(brain_dir / "fragment_memory.md")

    prefs = extract_profile_preferences(profile_text)
    session_summaries = extract_session_summaries(profile_text)
    lessons = extract_lessons(lessons_text)
    recent_memories = extract_recent_memory_index(brain_text)
    fragment_notes = extract_fragment_notes(fragment_text)

    lines = build_context_lines(
        project_name=brain_dir.parent.name if brain_dir.parent else "unknown",
        prefs=prefs,
        lessons=lessons,
        recent_memories=recent_memories,
        fragment_notes=fragment_notes,
        session_summaries=session_summaries,
    )
    bounded_max_chars = max(300, int(max_chars))
    context_text = fit_to_max_chars(lines, max_chars=bounded_max_chars)
    return {
        "status": "success",
        "brain_path": str(brain_path),
        "max_chars": bounded_max_chars,
        "actual_chars": len(context_text),
        "counts": {
            "preferences": len(prefs),
            "lessons": len(lessons),
            "recent_memories": len(recent_memories),
            "session_summaries": len(session_summaries),
            "fragment_notes": len(fragment_notes),
        },
        "context": context_text,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build compact memory context for reasoning")
    parser.add_argument("--brain-path", type=str, help="path to brain.md")
    parser.add_argument("--project-root", type=str, help="project root (optional)")
    parser.add_argument("--max-chars", type=int, default=CONTEXT_PACK_MAX_CHARS_DEFAULT, help="maximum output chars")
    parser.add_argument("--format", choices=["text", "json"], default="text", help="output format")
    args = parser.parse_args()

    brain_path = (
        resolve_brain_path(explicit_path=args.brain_path)
        if args.brain_path
        else resolve_brain_path(start_path=args.project_root or os.getcwd())
    )
    pack = build_context_pack(brain_path, max_chars=args.max_chars)

    if args.format == "text":
        print(pack["context"])
        return

    print(json.dumps(pack, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
