#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_memory.py - memory creation helper

LLM-assisted workflow:
- prepare/evaluate/extract-kw: generate prompts for the model
- quick/create: persist memory files and update brain indexes

Design goals:
- Never silently fail writes when triggered
- Avoid corrupting markdown tables by using exact-column row updates
- Continuously accumulate user preference profile
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from load_brain import load_brain
from project_utils import (
    find_project_root,
    resolve_brain_path,
    read_file_safely,
    generate_memory_id,
    generate_filename,
    create_memory_document,
    save_memory,
    update_brain_index,
    update_cue_network,
    record_brain_activity,
    _sanitize_table_cell,
    normalize_category,
    normalize_keywords,
    infer_title,
    simple_keyword_extraction,
    estimate_quality_score,
    DEFAULT_CATEGORIES,
    CATEGORY_BRAIN_DOMINANT,
)
from memory_defaults import POST_WRITE_CONTEXT_MAX_CHARS_DEFAULT
from memory_extensions import (
    FRAGMENT_MAX_CHARS_DEFAULT,
    is_learning_memory,
    should_route_to_fragment_memory,
    summarize_minor_note,
    update_fragment_memory,
    update_lessons_learned,
)


PREFERENCE_HINTS = [
    "prefer",
    "preference",
    "like",
    "dislike",
    "avoid",
    "must",
    "should",
    "dont",
    "don't",
    "do not",
    "please",
    "always",
    "never",
    "first",
    "priority",
    "habit",
    "style",
    "tone",
    "format",
    "constraint",
]


def prepare_evaluation_context(content: str, category: str | None, project: str | None, title: str | None) -> dict:
    prompt_path = script_dir.parent / "prompts" / "evaluate_quality.md"
    prompt_template = read_file_safely(str(prompt_path)) if prompt_path.exists() else None
    return {
        "status": "ready_for_llm",
        "content": content,
        "category": category,
        "project": project,
        "title": title,
        "prompt_template": prompt_template,
    }


def prepare_keyword_extraction_context(content: str, category: str | None, project: str | None, title: str | None) -> dict:
    prompt_path = script_dir.parent / "prompts" / "extract_keywords.md"
    prompt_template = read_file_safely(str(prompt_path)) if prompt_path.exists() else None
    return {
        "status": "ready_for_llm",
        "content": content,
        "category": category,
        "project": project,
        "title": title,
        "prompt_template": prompt_template,
    }


def _parse_profile_counts(content: str) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for m in re.finditer(r"^\- \[(\d+)\] (.+)$", content or "", flags=re.MULTILINE):
        signal = m.group(2).strip()
        if not signal:
            continue
        count = int(m.group(1))
        if count <= 0:
            continue
        if signal.lower() in {"none yet", "none"}:
            continue
        counts[signal] = max(counts.get(signal, 0), count)
    return counts


def _extract_session_summary_rows(content: str) -> list[str]:
    """
    Preserve existing session summary rows when rewriting profile.
    """
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
    rows_block = m.group(1).strip()
    if not rows_block:
        return []
    rows = []
    for line in rows_block.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        # keep only plausible table rows
        if line.count("|") < 5:
            continue
        rows.append(line)
    return rows[:20]


def _extract_recent_signal_rows(content: str) -> list[str]:
    if not content:
        return []
    pattern = (
        r"## Recent Signals\s*\n"
        r"\| Time \| Memory ID \| Title \| Signal \|\n"
        r"\|[-| ]+\|\n"
        r"((?:\|.*\|\n?)*)"
    )
    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        return []

    rows = []
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|") or line.count("|") < 5:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 4:
            continue
        memory_id = parts[1]
        if memory_id != "-" and not memory_id.startswith("mem_"):
            # Prevent session rows from being mixed into recent signal rows.
            continue
        rows.append("| " + " | ".join(parts[:4]) + " |")
    return rows[:50]


def _normalize_signal(signal: str) -> str:
    signal = re.sub(r"[`*_#>-]", " ", signal)
    signal = re.sub(r"\s+", " ", signal).strip(" ;,.:")
    return signal[:120]


def extract_preference_signals(title: str, content: str, keywords=None, limit: int = 8) -> list[str]:
    candidates: list[str] = []
    if title and any(h in title.lower() for h in PREFERENCE_HINTS):
        candidates.append(_normalize_signal(title))

    for raw_line in (content or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if any(h in lower for h in PREFERENCE_HINTS):
            normalized = _normalize_signal(line)
            if normalized:
                candidates.append(normalized)

    for kw in normalize_keywords(keywords)[:3]:
        if len(kw) >= 2:
            candidates.append(_normalize_signal(f"topic: {kw}"))

    out = []
    seen = set()
    for c in candidates:
        k = c.lower()
        if not c or k in seen:
            continue
        seen.add(k)
        out.append(c)
        if len(out) >= limit:
            break
    return out


def update_user_profile(brain_path: str, memory_metadata: dict, content: str) -> dict:
    brain_dir = Path(brain_path).parent
    profile_path = brain_dir / "user_profile.md"
    existing = read_file_safely(str(profile_path)) or ""
    counts = _parse_profile_counts(existing)
    session_rows = _extract_session_summary_rows(existing)

    signals = extract_preference_signals(
        title=memory_metadata.get("title", ""),
        content=content,
        keywords=memory_metadata.get("keywords", []),
    )
    for s in signals:
        counts[s] = counts.get(s, 0) + 1

    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    strong = [(k, v) for k, v in ranked if v >= 3][:20]
    weak = [(k, v) for k, v in ranked if v < 3][:20]

    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")
    signal_text = "; ".join(signals[:3]) if signals else "no clear preference signal"
    signal_text = _sanitize_table_cell(signal_text)
    title = _sanitize_table_cell(memory_metadata.get("title", ""))
    memory_id = _sanitize_table_cell(memory_metadata.get("id", ""))

    existing_rows = _extract_recent_signal_rows(existing)
    recent_rows = [f"| {now} | {memory_id} | {title} | {signal_text} |"] + existing_rows
    recent_rows = recent_rows[:50]

    lines = [
        "---",
        "version: 1",
        f"updated_at: {now}",
        f"total_signals: {len(counts)}",
        f"last_memory_id: {memory_id}",
        "---",
        "",
        "# User Preference Profile",
        "",
        "## Stable Preferences (>=3)",
    ]
    lines.extend([f"- [{cnt}] {sig}" for sig, cnt in strong] if strong else ["- [0] None yet"])
    lines.extend(["", "## Emerging Preferences (<3)"])
    lines.extend([f"- [{cnt}] {sig}" for sig, cnt in weak] if weak else ["- [0] None yet"])
    lines.extend(["", "## Recent Signals", "| Time | Memory ID | Title | Signal |", "|------|-----------|-------|--------|"])
    lines.extend(recent_rows if recent_rows else ["| - | - | - | - |"])
    lines.extend(["", "## Session Summaries", "| Time | Session ID | Memories | Summary |", "|------|------------|----------|---------|"])
    lines.extend(session_rows if session_rows else ["| - | - | - | - |"])
    lines.append("")

    with open(profile_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    return {
        "updated": True,
        "path": str(profile_path),
        "signals_added": len(signals),
        "stable_preferences": len(strong),
    }


def _finalize_memory_write(
    brain_path: Path,
    metadata: dict,
    content: str,
    *,
    enable_fragment_routing: bool = True,
    fragment_max_chars: int = FRAGMENT_MAX_CHARS_DEFAULT,
) -> dict:
    memory_id = metadata.get("id") or generate_memory_id()
    filename = generate_filename(metadata.get("title"), memory_id=memory_id)
    now = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    metadata["id"] = memory_id
    metadata["created_at"] = metadata.get("created_at") or now
    metadata["updated_at"] = metadata.get("updated_at") or now
    metadata["access_count"] = metadata.get("access_count", 1)
    metadata["strength"] = metadata.get("strength", 1.0)

    learning_flag = is_learning_memory(metadata.get("title", ""), content)
    route_fragment = enable_fragment_routing and should_route_to_fragment_memory(
        category=metadata["category"],
        title=metadata.get("title", ""),
        content=content,
        keywords=metadata.get("keywords", []),
        quality_score=int(metadata.get("quality_score", 50)),
        is_learning=learning_flag,
    )

    if route_fragment:
        note = summarize_minor_note(
            metadata.get("title", ""),
            content,
            metadata.get("keywords", []),
        )
        fragment_updated = update_fragment_memory(
            str(brain_path),
            note=note,
            max_chars=max(500, int(fragment_max_chars)),
        )
        profile_updated = update_user_profile(str(brain_path), metadata, note)
        lessons_updated = update_lessons_learned(
            str(brain_path),
            memory_id=f"frag_{metadata['created_at']}",
            title=metadata.get("title", ""),
            content=content,
            keywords=metadata.get("keywords", []),
        )
        brain_activity_updated = record_brain_activity(
            str(brain_path),
            operation="fragment_write",
            memory_id=f"frag_{metadata['created_at']}",
            detail=metadata.get("title") or "fragment note",
        )

        return {
            "status": "success",
            "stored_in": "fragment_memory",
            "standalone_memory_created": False,
            "fragment_updated": fragment_updated,
            "profile_updated": profile_updated,
            "lessons_updated": lessons_updated,
            "brain_activity_updated": brain_activity_updated,
            "brain_path": str(brain_path),
            "brain_refresh_hint": f"python scripts/refresh_brain.py --max-chars {POST_WRITE_CONTEXT_MAX_CHARS_DEFAULT} --format text",
        }

    document = create_memory_document(metadata, content)
    save_path = save_memory(document, metadata["category"], filename, str(brain_path))
    brain_updated = update_brain_index(str(brain_path), metadata, operation="add")
    cue_updated = update_cue_network(
        str(brain_path),
        category=metadata["category"],
        project=metadata.get("project"),
        keywords=metadata.get("keywords", []),
        memory_id=memory_id,
        operation="add",
    )
    profile_updated = update_user_profile(str(brain_path), metadata, content)
    lessons_updated = update_lessons_learned(
        str(brain_path),
        memory_id=memory_id,
        title=metadata.get("title", ""),
        content=content,
        keywords=metadata.get("keywords", []),
    )

    return {
        "status": "success",
        "stored_in": "standalone_memory",
        "standalone_memory_created": True,
        "memory": {
            "id": memory_id,
            "title": metadata.get("title"),
            "path": save_path,
            "category": metadata["category"],
            "project": metadata.get("project", ""),
            "keywords": metadata.get("keywords", []),
            "brain_dominant": metadata.get("brain_dominant", "both"),
            "quality_score": metadata.get("quality_score", 50),
            "created_at": metadata["created_at"],
        },
        "brain_updated": brain_updated,
        "cue_network_updated": cue_updated,
        "profile_updated": profile_updated,
        "lessons_updated": lessons_updated,
        "brain_path": str(brain_path),
        "brain_refresh_hint": f"python scripts/refresh_brain.py --max-chars {POST_WRITE_CONTEXT_MAX_CHARS_DEFAULT} --format text",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Memory creation helper")
    parser.add_argument("--category", type=str, help="memory category")
    parser.add_argument("--project", type=str, help="project name")
    parser.add_argument("--keywords", type=str, help="comma-separated keywords")
    parser.add_argument("--title", type=str, help="memory title")
    parser.add_argument("--content", type=str, help="memory content")
    parser.add_argument("--brain-dominant", type=str, choices=["left", "right", "both"], help="brain dominant side")
    parser.add_argument("--quality-score", type=int, default=None, help="quality score")
    parser.add_argument("--mode", type=str, choices=["prepare", "create", "evaluate", "extract-kw", "quick"], default="prepare")
    parser.add_argument("--metadata", type=str, help="metadata json for create mode")
    parser.add_argument("--brain-path", type=str, help="path to brain.md")
    parser.add_argument("--project-root", type=str, help="project root (optional)")
    parser.add_argument("--force-write", action="store_true", help="force write even when decision=no_memory")
    parser.add_argument("--respect-no-memory", action="store_true", help="skip write when decision=no_memory")
    parser.add_argument("--disable-fragment-routing", action="store_true", help="always create standalone memory")
    parser.add_argument("--fragment-max-chars", type=int, default=FRAGMENT_MAX_CHARS_DEFAULT, help="max chars for fragment_memory.md")
    args = parser.parse_args()

    brain_path = resolve_brain_path(explicit_path=args.brain_path) if args.brain_path else resolve_brain_path(start_path=args.project_root or os.getcwd())
    load_brain(str(brain_path))

    try:
        if args.mode == "prepare":
            content = args.content or ""
            eval_context = prepare_evaluation_context(content, args.category, args.project, args.title)
            kw_context = prepare_keyword_extraction_context(content, args.category, args.project, args.title)
            output = {
                "status": "ready_for_llm",
                "evaluation": {
                    "prompt": eval_context["prompt_template"].format(
                        memory_content=content,
                        category=args.category or "unspecified",
                        project=args.project or "unspecified",
                        title=args.title or "unspecified",
                    )
                    if eval_context["prompt_template"]
                    else None
                },
                "keyword_extraction": {
                    "prompt": kw_context["prompt_template"].format(
                        memory_content=content,
                        category=args.category or "unspecified",
                        project=args.project or "unspecified",
                        title=args.title or "unspecified",
                    )
                    if kw_context["prompt_template"]
                    else None
                },
            }
            print(json.dumps(output, ensure_ascii=False, indent=2))
            return

        if args.mode == "evaluate":
            content = args.content or ""
            eval_context = prepare_evaluation_context(content, args.category, args.project, args.title)
            prompt = (
                eval_context["prompt_template"].format(
                    memory_content=content,
                    category=args.category or "unspecified",
                    project=args.project or "unspecified",
                    title=args.title or "unspecified",
                )
                if eval_context["prompt_template"]
                else None
            )
            print(json.dumps({"status": "ready_for_llm", "prompt": prompt}, ensure_ascii=False, indent=2))
            return

        if args.mode == "extract-kw":
            content = args.content or ""
            kw_context = prepare_keyword_extraction_context(content, args.category, args.project, args.title)
            prompt = (
                kw_context["prompt_template"].format(
                    memory_content=content,
                    category=args.category or "unspecified",
                    project=args.project or "unspecified",
                    title=args.title or "unspecified",
                )
                if kw_context["prompt_template"]
                else None
            )
            print(json.dumps({"status": "ready_for_llm", "prompt": prompt}, ensure_ascii=False, indent=2))
            return

        if args.mode == "quick":
            content = args.content
            if not content and not sys.stdin.isatty():
                content = sys.stdin.read()
            if not content or not content.strip():
                print(json.dumps({"status": "error", "error": "EMPTY_CONTENT", "message": "content is empty"}, ensure_ascii=False, indent=2))
                sys.exit(1)

            project_root = find_project_root(args.project_root or os.getcwd())
            metadata = {
                "title": args.title or infer_title(content),
                "category": normalize_category(args.category),
                "project": args.project or project_root.name,
                "keywords": normalize_keywords(args.keywords) or simple_keyword_extraction(content),
                "brain_dominant": args.brain_dominant or CATEGORY_BRAIN_DOMINANT.get(normalize_category(args.category), "both"),
                "quality_score": args.quality_score if args.quality_score is not None else estimate_quality_score(content),
            }
            print(
                json.dumps(
                    _finalize_memory_write(
                        brain_path,
                        metadata,
                        content,
                        enable_fragment_routing=not args.disable_fragment_routing,
                        fragment_max_chars=args.fragment_max_chars,
                    ),
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return

        if args.mode == "create":
            if not args.metadata:
                print(json.dumps({"status": "error", "error": "NO_METADATA", "message": "metadata is required for create mode"}, ensure_ascii=False, indent=2))
                sys.exit(1)
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError as e:
                print(json.dumps({"status": "error", "error": "INVALID_JSON", "message": str(e)}, ensure_ascii=False, indent=2))
                sys.exit(1)

            decision = str(metadata.get("decision", "")).strip().lower()
            decision_overridden = False
            if decision == "no_memory":
                if args.respect_no_memory and not args.force_write:
                    print(json.dumps({"status": "skipped", "reason": "decision=no_memory", "message": "decision=no_memory respected by --respect-no-memory"}, ensure_ascii=False, indent=2))
                    sys.exit(0)
                decision_overridden = True

            content = args.content
            if not content:
                if not sys.stdin.isatty():
                    content = sys.stdin.read()
                else:
                    content = f"# {metadata.get('title', 'Memory')}\n\n## Context\n\n## Need\n\n## Solution\n\n## Notes\n"

            project_root = find_project_root(args.project_root or os.getcwd())
            if not metadata.get("title"):
                metadata["title"] = args.title or infer_title(content)
            metadata["category"] = normalize_category(metadata.get("category") or args.category)
            metadata["project"] = metadata.get("project") or args.project or project_root.name
            metadata["keywords"] = normalize_keywords(metadata.get("keywords") or args.keywords)
            if not metadata["keywords"]:
                metadata["keywords"] = simple_keyword_extraction(content)
            metadata["brain_dominant"] = metadata.get("brain_dominant") or args.brain_dominant or CATEGORY_BRAIN_DOMINANT.get(metadata["category"], "both")
            if metadata.get("quality_score") is None:
                metadata["quality_score"] = args.quality_score if args.quality_score is not None else estimate_quality_score(content)
            if decision_overridden:
                metadata["quality_score"] = max(35, int(metadata.get("quality_score", 35)))
                if "micro-memory" not in metadata["keywords"]:
                    metadata["keywords"].append("micro-memory")

            result = _finalize_memory_write(
                brain_path,
                metadata,
                content,
                enable_fragment_routing=not args.disable_fragment_routing,
                fragment_max_chars=args.fragment_max_chars,
            )
            result["decision_overridden"] = decision_overridden
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return

    except Exception as e:
        print(json.dumps({"status": "error", "error": {"code": "CREATE_FAILED", "message": str(e)}}, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
