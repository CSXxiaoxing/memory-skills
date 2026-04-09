#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
memory_extensions.py

Extensions for:
1) fragment memory (small scattered updates)
2) lessons learned memory (mistakes/corrections)
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

from memory_defaults import FRAGMENT_MAX_CHARS_DEFAULT

FRAGMENT_ROUTE_CONTENT_MAX = 220

FRAGMENT_HINTS = [
    "style",
    "wording",
    "copy",
    "typo",
    "font",
    "spacing",
    "color",
    "rename",
    "small fix",
    "text",
    "样式",
    "文案",
    "错字",
    "间距",
    "小改",
]

LEARNING_HINTS = [
    "error",
    "bug",
    "mistake",
    "wrong",
    "failed",
    "failure",
    "regression",
    "fix",
    "fixed",
    "correct",
    "correction",
    "avoid",
    "root cause",
    "don't",
    "do not",
    "never again",
    "错误",
    "修复",
    "纠正",
    "回归",
    "避免",
    "根因",
    "不要再",
]

LOW_VALUE_HINTS = [
    "ok",
    "done",
    "looks good",
    "tiny tweak",
    "minor update",
    "finished",
]


def read_file_safely(file_path: str) -> str | None:
    p = Path(file_path)
    if not p.exists():
        return None
    for encoding in ["utf-8", "gbk", "gb2312", "latin1"]:
        try:
            return p.read_text(encoding=encoding)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _sanitize_inline(text: str) -> str:
    text = (text or "").replace("\n", " ").replace("|", "/")
    return re.sub(r"\s+", " ", text).strip()


def _contains_hint(text: str, hints: list[str]) -> bool:
    lower = (text or "").lower()
    return any(h.lower() in lower for h in hints)


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"[。\n.!?；;]+", text or "")
    out = []
    for p in parts:
        p = _sanitize_inline(p)
        if p:
            out.append(p)
    return out


def summarize_minor_note(title: str, content: str, keywords: list[str] | None = None, max_len: int = 180) -> str:
    title = _sanitize_inline(title)
    body = _sanitize_inline(content)
    kws = ", ".join((keywords or [])[:3]).strip()

    if body:
        note = f"{title}: {body}" if title else body
    else:
        note = title or "minor change"

    if kws:
        note = f"{note} (topics: {kws})"
    return note[:max_len]


def score_fragment_note(note: str) -> int:
    n = _sanitize_inline(note)
    if not n:
        return 0

    score = 0
    if len(n) >= 24:
        score += 1
    if _contains_hint(n, FRAGMENT_HINTS):
        score += 1
    if _contains_hint(n, LEARNING_HINTS):
        score += 2
    if _contains_hint(n, LOW_VALUE_HINTS):
        score -= 2
    return score


def _parse_fragment_entries(content: str) -> list[dict]:
    rows = []
    if not content:
        return rows
    pattern = r"^\- \[([^\]]+)\] \(score:(-?\d+)\) (.+)$"
    for line in content.splitlines():
        m = re.match(pattern, line.strip())
        if not m:
            continue
        rows.append(
            {
                "time": m.group(1).strip(),
                "score": int(m.group(2)),
                "note": _sanitize_inline(m.group(3)),
            }
        )
    return rows


def _render_fragment_doc(entries: list[dict], max_chars: int) -> str:
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "---",
        "version: 1",
        f"updated_at: {now}",
        f"max_chars: {max_chars}",
        f"entries: {len(entries)}",
        "---",
        "",
        "# Fragment Memory",
        "",
        "Small scattered memory notes. Older low-value notes are forgotten first when over limit.",
        "",
        "## Entries",
    ]
    if entries:
        for e in entries:
            lines.append(f"- [{e['time']}] (score:{e['score']}) {e['note']}")
    else:
        lines.append("- [empty] (score:0) no entries")
    lines.append("")
    return "\n".join(lines)


def _dedupe_keep_newest(entries: list[dict]) -> list[dict]:
    seen = set()
    out = []
    for e in entries:
        key = e["note"].lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _compress_fragment_entries(entries: list[dict], max_chars: int) -> tuple[list[dict], int]:
    entries = _dedupe_keep_newest(entries)
    dropped = 0

    def over_limit(cur: list[dict]) -> bool:
        return len(_render_fragment_doc(cur, max_chars)) > max_chars

    while entries and over_limit(entries):
        idx = next((i for i in range(len(entries) - 1, -1, -1) if entries[i]["score"] <= 0), None)
        if idx is None:
            idx = next((i for i in range(len(entries) - 1, -1, -1) if entries[i]["score"] <= 1), None)
        if idx is not None and len(entries) > 5:
            entries.pop(idx)
            dropped += 1
            continue

        truncated = False
        for i in range(len(entries) - 1, -1, -1):
            note = entries[i]["note"]
            if len(note) > 80:
                entries[i]["note"] = note[:80].rstrip() + "..."
                truncated = True
                break
        if truncated and not over_limit(entries):
            break
        if truncated:
            continue

        if len(entries) > 5:
            entries.pop()
            dropped += 1
        else:
            break

    return entries, dropped


def update_fragment_memory(brain_path: str | Path, note: str, max_chars: int = FRAGMENT_MAX_CHARS_DEFAULT) -> dict:
    brain_dir = Path(brain_path).parent
    target = brain_dir / "fragment_memory.md"
    old = read_file_safely(str(target)) or ""
    entries = _parse_fragment_entries(old)

    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    clean_note = _sanitize_inline(note)[:220]
    entries.insert(0, {"time": now, "score": score_fragment_note(clean_note), "note": clean_note})

    entries, dropped = _compress_fragment_entries(entries, max_chars=max_chars)
    doc = _render_fragment_doc(entries, max_chars=max_chars)
    target.write_text(doc, encoding="utf-8")

    return {
        "updated": True,
        "path": str(target),
        "entry_count": len(entries),
        "dropped_count": dropped,
        "current_chars": len(doc),
        "max_chars": max_chars,
    }


def is_learning_memory(title: str, content: str) -> bool:
    text = f"{title}\n{content}".lower()
    return _contains_hint(text, LEARNING_HINTS)


def should_route_to_fragment_memory(
    *,
    category: str,
    title: str,
    content: str,
    keywords: list[str] | None,
    quality_score: int,
    is_learning: bool,
) -> bool:
    if is_learning:
        return False
    text = f"{title}\n{content}\n{','.join(keywords or [])}".lower()
    if "```" in (content or ""):
        return False
    if len(content or "") > FRAGMENT_ROUTE_CONTENT_MAX:
        return False
    if quality_score > 45:
        return False
    if category in {"docs", "design", "other"}:
        return True
    if _contains_hint(text, FRAGMENT_HINTS):
        return True
    return False


def _parse_lesson_counts(content: str) -> dict[str, int]:
    counts = {}
    for m in re.finditer(r"^\- \[(\d+)\] (.+)$", content or "", flags=re.MULTILINE):
        cnt = int(m.group(1))
        lesson = _sanitize_inline(m.group(2))
        if cnt <= 0 or lesson.lower() in {"none yet", "none"}:
            continue
        counts[lesson] = max(counts.get(lesson, 0), cnt)
    return counts


def _extract_incident_rows(content: str) -> list[dict]:
    """提取事件行，支持新结构化格式"""
    if not content:
        return []
    pattern = (
        r"## Recent Incidents\s*\n"
        r"\| Time \| Memory ID \| Type \| Lesson \|\n"
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
            parts = [p.strip() for p in line.strip("|").split("|")]
            if len(parts) >= 4:
                rows.append({
                    "time": parts[0],
                    "memory_id": parts[1],
                    "type": parts[2],
                    "lesson": parts[3]
                })
    return rows[:100]


def _extract_correction_entries(content: str) -> list[dict]:
    """提取结构化纠正记忆条目"""
    if not content:
        return []
    entries = []
    # 匹配结构化纠正记忆块
    pattern = r"---\n((?:.|\n)*?)\n---\n((?:.|\n)*?)(?=\n---\n|$)"
    for m in re.finditer(pattern, content, flags=re.MULTILINE):
        front_matter = m.group(1)
        body = m.group(2)
        entry = {}
        for line in front_matter.splitlines():
            line = line.strip()
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()
                if key == "reuse_count":
                    value = int(value) if value.isdigit() else 0
                entry[key] = value
        if entry.get("type") == "correction":
            entry["content"] = body.strip()
            entries.append(entry)
    return entries


def generate_correction_id() -> str:
    """生成唯一纠正记忆ID"""
    now = datetime.now()
    return f"corr_{now.strftime('%Y%m%d_%H%M%S')}_{str(now.microsecond // 1000).zfill(3)}"


def extract_learning_items(title: str, content: str, keywords: list[str] | None = None, limit: int = 6) -> list[str]:
    text = f"{title}\n{content}".strip()
    items = []
    for sent in _split_sentences(text):
        if _contains_hint(sent, LEARNING_HINTS):
            items.append(sent)

    for kw in (keywords or [])[:4]:
        kw = _sanitize_inline(kw)
        if _contains_hint(kw, LEARNING_HINTS):
            items.append(f"Watchpoint topic: {kw}")

    if not items and is_learning_memory(title, content):
        items.append(_sanitize_inline(title or "learning memory item"))

    deduped = []
    seen = set()
    for it in items:
        key = it.lower()
        if key in seen or not it:
            continue
        seen.add(key)
        deduped.append(it[:180])
        if len(deduped) >= limit:
            break
    return deduped


def update_lessons_learned(
    brain_path: str | Path,
    *,
    memory_id: str,
    title: str,
    content: str,
    keywords: list[str] | None = None,
    correction_info: dict | None = None,
) -> dict:
    """
    更新经验库，支持普通学习记忆和结构化纠正记忆
    
    Args:
        correction_info: 结构化纠正信息，包含：
            - error_scene: 错误场景
            - error_content: 错误内容
            - correction_points: 纠正要点
            - correct_solution: 正确方案
            - quality_score: 质量分数（默认95）
            - strength: 记忆强度（默认1.5）
    """
    items = extract_learning_items(title, content, keywords)
    target = Path(brain_path).parent / "lessons_learned.md"
    old = read_file_safely(str(target)) or ""
    now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
    
    # 处理结构化纠正记忆
    correction_added = False
    structured_corrections = _extract_correction_entries(old)
    if correction_info is not None:
        # 生成纠正记忆ID
        corr_id = correction_info.get("id") or generate_correction_id()
        correction_entry = {
            "id": corr_id,
            "type": "correction",
            "memory_id": memory_id,
            "error_scene": _sanitize_inline(correction_info.get("error_scene", "")),
            "error_content": _sanitize_inline(correction_info.get("error_content", "")),
            "correction_points": _sanitize_inline(correction_info.get("correction_points", "")),
            "correct_solution": _sanitize_inline(correction_info.get("correct_solution", "")),
            "keywords": ",".join(keywords or []),
            "quality_score": correction_info.get("quality_score", 95),
            "strength": correction_info.get("strength", 1.5),
            "created_at": now,
            "reuse_count": 0
        }
        structured_corrections.insert(0, correction_entry)
        correction_added = True
        
        # 自动提取纠正相关的学习条目
        correction_items = [
            correction_entry["error_scene"],
            correction_entry["correction_points"],
            correction_entry["correct_solution"]
        ]
        correction_items = [item for item in correction_items if item]
        items.extend(correction_items)
    
    # 处理规则和事件
    counts = _parse_lesson_counts(old)
    incident_rows = _extract_incident_rows(old)
    incident_type = "correction" if correction_info is not None or _contains_hint(f"{title}\n{content}", ["fix", "fixed", "correct", "纠正", "修复"]) else "mistake"

    for it in items:
        counts[it] = counts.get(it, 0) + 1

    for it in reversed(items):
        row = {
            "time": now,
            "memory_id": memory_id,
            "type": incident_type,
            "lesson": _sanitize_inline(it)
        }
        incident_rows.insert(0, row)
    incident_rows = incident_rows[:100]

    ranked = sorted(counts.items(), key=lambda x: (-x[1], x[0]))
    stable = [(k, v) for k, v in ranked if v >= 2][:30]
    emerging = [(k, v) for k, v in ranked if v < 2][:30]

    # 构建新文档
    lines = [
        "---",
        "version: 2",
        f"updated_at: {now}",
        f"total_lessons: {len(counts)}",
        f"total_corrections: {len(structured_corrections)}",
        "---",
        "",
        "# Lessons Learned",
        "",
        "## Stable Rules (>=2)",
    ]
    lines.extend([f"- [{cnt}] {txt}" for txt, cnt in stable] if stable else ["- [0] None yet"])
    lines.extend(["", "## Emerging Rules (<2)"])
    lines.extend([f"- [{cnt}] {txt}" for txt, cnt in emerging] if emerging else ["- [0] None yet"])
    lines.extend(["", "## Recent Incidents", "| Time | Memory ID | Type | Lesson |", "|------|-----------|------|--------|"])
    lines.extend([
        f"| {row['time']} | {row['memory_id']} | {row['type']} | {row['lesson']} |" 
        for row in incident_rows
    ] if incident_rows else ["| - | - | - | - |"])
    
    # 新增结构化纠正记忆部分
    lines.extend(["", "## Structured Corrections", ""])
    for corr in structured_corrections[:100]:  # 保留最新100条纠正记录
        lines.extend([
            "---",
            f"id: {corr['id']}",
            f"type: {corr['type']}",
            f"memory_id: {corr['memory_id']}",
            f"error_scene: {corr['error_scene']}",
            f"error_content: {corr['error_content']}",
            f"correction_points: {corr['correction_points']}",
            f"correct_solution: {corr['correct_solution']}",
            f"keywords: {corr['keywords']}",
            f"quality_score: {corr['quality_score']}",
            f"strength: {corr['strength']}",
            f"created_at: {corr['created_at']}",
            f"reuse_count: {corr['reuse_count']}",
            "---",
            "",
            corr.get("content", ""),
            ""
        ])

    lines.append("")

    target.write_text("\n".join(lines), encoding="utf-8")
    return {
        "updated": True,
        "path": str(target),
        "items_added": len(items),
        "stable_rules": len(stable),
        "correction_added": correction_added,
        "correction_id": corr_id if correction_added else None,
    }
