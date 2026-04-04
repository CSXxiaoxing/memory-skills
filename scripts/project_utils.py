#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
project_utils.py - Project root and memory path helpers.

Goals:
- Consistent project root detection (per SKILL.md rules)
- Stable brain.md resolution (.memory preferred, legacy brain.md supported)
- Shared helpers for memory directory resolution
- Common utility functions for memory operations (DRY principle)
"""

from __future__ import annotations

import os
import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


PROJECT_MARKERS = ["package.json", "Cargo.toml", "go.mod"]

DEFAULT_CATEGORIES = ["coding", "design", "config", "docs", "debug", "other"]
CATEGORY_BRAIN_DOMINANT = {
    "coding": "left",
    "config": "left",
    "debug": "left",
    "design": "right",
    "docs": "right",
    "other": "both",
}


def find_project_root(start_path: Optional[str | Path] = None) -> Path:
    """
    Detect project root by walking upward from start_path.

    Priority:
    1) .memory/brain.md exists
    2) .git exists
    3) package.json / Cargo.toml / go.mod exists
    4) fallback to start_path
    """
    start = Path(start_path or os.getcwd()).resolve()
    for candidate in [start] + list(start.parents):
        if (candidate / ".memory" / "brain.md").exists():
            return candidate
        if (candidate / ".git").exists():
            return candidate
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
    return start


def resolve_brain_path(
    start_path: Optional[str | Path] = None,
    explicit_path: Optional[str | Path] = None,
    prefer_dot_memory: bool = True,
) -> Path:
    """
    Resolve brain.md path.

    - If explicit_path provided, use it.
    - Otherwise detect project root and prefer .memory/brain.md if present.
    - Fallback to legacy root/brain.md if it exists.
    - If none exist, return preferred target (dot-memory by default).
    """
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    root = find_project_root(start_path)
    dot_brain = root / ".memory" / "brain.md"
    legacy_brain = root / "brain.md"

    if dot_brain.exists():
        return dot_brain
    if legacy_brain.exists():
        return legacy_brain
    return dot_brain if prefer_dot_memory else legacy_brain


def get_memory_dir(brain_path: str | Path) -> Path:
    """Return the memories directory based on brain.md location."""
    return Path(brain_path).parent / "memories"


def ensure_dir(path: str | Path) -> Path:
    """Ensure directory exists and return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def read_file_safely(file_path: str | Path) -> Optional[str]:
    """
    安全读取文件(支持多种编码)

    Args:
        file_path: 文件路径

    Returns:
        str: 文件内容，如果读取失败返回 None
    """
    if not os.path.exists(file_path):
        return None

    for encoding in ["utf-8", "gbk", "gb2312", "latin1"]:
        try:
            with open(file_path, "r", encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue

    return None


def generate_memory_id() -> str:
    """
    生成唯一记忆ID

    格式: mem_YYYYMMDD_HHMMSS_序号

    Returns:
        str: 记忆ID
    """
    now = datetime.now()
    return f"mem_{now.strftime('%Y%m%d_%H%M%S')}_{str(now.microsecond // 1000).zfill(3)}"


def generate_filename(title: str | None = None, memory_id: str | None = None) -> str:
    """
    生成文件名

    格式: YYYYMMDD_HHMMSS_简短标识.md 或 memory_id.md

    Args:
        title: 标题(用于提取标识)
        memory_id: 记忆ID（如果提供则直接使用）

    Returns:
        str: 文件名
    """
    if memory_id:
        return f"{memory_id}.md"
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    if title:
        ident = re.sub(r"[^\w\u4e00-\u9fff]", "", title)[:20] or "memory"
    else:
        ident = "memory"
    return f"{ts}_{ident}.md"


def create_memory_document(metadata: dict, content: str) -> str:
    """
    创建记忆文档

    Args:
        metadata: 元数据字典
        content: 正文内容

    Returns:
        str: 完整的Markdown文档（包含YAML前置元数据）
    """
    lines = [
        "---",
        f"id: {metadata.get('id', '')}",
        f"title: {metadata.get('title', '')}",
        f"category: {metadata.get('category', 'other')}",
        f"project: {metadata.get('project', '')}",
        f"brain_dominant: {metadata.get('brain_dominant', 'both')}",
    ]
    kws = metadata.get("keywords", [])
    if kws:
        lines.append(f"keywords: [{', '.join(kws)}]")
    else:
        lines.append("keywords: []")
    lines.extend(
        [
            f"quality_score: {metadata.get('quality_score', 50)}",
            f"created_at: {metadata.get('created_at', '')}",
            f"updated_at: {metadata.get('updated_at', '')}",
            f"access_count: {metadata.get('access_count', 1)}",
            f"strength: {metadata.get('strength', 1.0)}",
            "---",
            "",
            content,
        ]
    )
    return "\n".join(lines)


def save_memory(document: str, category: str, filename: str, brain_path: str, memories_dir: str = "memories") -> str:
    """
    保存记忆文档到文件系统

    Args:
        document: 文档内容
        category: 类别
        filename: 文件名
        brain_path: brain.md路径
        memories_dir: 记忆仓库目录

    Returns:
        str: 保存路径
    """
    brain_dir = Path(brain_path).parent
    target_dir = brain_dir / memories_dir / category
    target_dir.mkdir(parents=True, exist_ok=True)
    save_path = target_dir / filename
    with open(save_path, "w", encoding="utf-8") as f:
        f.write(document)
    return str(save_path)


def _sanitize_table_cell(value: str | None) -> str:
    """清理表格单元格中的特殊字符"""
    if value is None:
        return ""
    value = str(value).replace("\n", " ").replace("|", " ")
    return re.sub(r"\s+", " ", value).strip()


def _insert_row_under_table_header(content: str, header_regex: str, row: str) -> tuple[str, bool]:
    """在表格标题行后插入新行"""
    m = re.search(header_regex, content, flags=re.MULTILINE)
    if not m:
        return content, False
    pos = m.end()
    return content[:pos] + row + content[pos:], True


def _count_memory_index_rows(content: str) -> int:
    """统计记忆索引表中的有效行数"""
    pattern = (
        r"##\s+(?:📚\s+)?(?:记忆索引表|Memory Index)\s*\n\n"
        r"\|[^\n]*ID[^\n]*\|\n"
        r"\|[-| ]+\|\n"
        r"((?:\|.*\|\n?)*)"
    )
    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        return 0

    count = 0
    for line in m.group(1).splitlines():
        line = line.strip()
        if re.match(r"^\|\s*mem_[^|]+\|", line):
            count += 1
    return count


def _count_fragment_entries(brain_path: str | Path | None) -> int:
    """统计 fragment_memory.md 中的有效条目数"""
    if not brain_path:
        return 0
    fragment_path = Path(brain_path).parent / "fragment_memory.md"
    content = read_file_safely(fragment_path)
    if not content:
        return 0

    count = 0
    for m in re.finditer(r"^\- \[([^\]]+)\] \(score:(-?\d+)\) .+$", content, flags=re.MULTILINE):
        tag = m.group(1).strip().lower()
        if tag == "empty":
            continue
        count += 1
    return count


def _count_keyword_index_rows(content: str) -> int:
    """统计关键词索引表中的有效行数"""
    pattern = (
        r"###\s+(?:关键词索引|Keyword Index)\s*\n\n"
        r"\|[^\n]*\|\n"
        r"\|[-| ]+\|\n"
        r"((?:\|.*\|\n?)*)"
    )
    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        return 0

    count = 0
    for line in m.group(1).splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 2:
            continue
        word, freq = parts[0], parts[1]
        if word in {"-", "(空)", ""}:
            continue
        if not freq.isdigit() or int(freq) <= 0:
            continue
        count += 1
    return count


def _set_status_row_value(content: str, keys: list[str], value: str) -> str:
    """设置状态表格中指定键的值"""
    for key in keys:
        pattern = rf"^\|\s*{re.escape(key)}\s*\|\s*[^|]*\|\s*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            return re.sub(
                pattern,
                f"| {key} | {value} |",
                content,
                count=1,
                flags=re.MULTILINE,
            )
    return content


def _refresh_brain_status(content: str, brain_path: str | Path | None = None) -> str:
    """刷新brain.md的状态信息（总记忆数、总线索数、最近更新时间）"""
    now = datetime.now().strftime("%Y-%m-%d")
    standalone_count = _count_memory_index_rows(content)
    fragment_count = _count_fragment_entries(brain_path)
    memory_count = standalone_count + fragment_count
    cue_count = _count_keyword_index_rows(content)

    content = _set_status_row_value(content, ["总记忆数", "Total Memories"], str(memory_count))
    content = _set_status_row_value(content, ["总线索数", "Total Cues"], str(cue_count))
    content = _set_status_row_value(content, ["最近更新", "Last Updated"], now)
    content = re.sub(r"^updated_at:\s*.*$", f"updated_at: {now}", content, count=1, flags=re.MULTILINE)
    return content


def record_brain_activity(brain_path: str, operation: str, memory_id: str, detail: str) -> bool:
    """
    记录大脑活动到最近活动表

    Args:
        brain_path: brain.md路径
        operation: 操作类型
        memory_id: 记忆ID
        detail: 详情描述

    Returns:
        bool: 是否成功
    """
    if not os.path.exists(brain_path):
        return False
    content = read_file_safely(brain_path)
    if not content:
        return False

    now = datetime.now().strftime("%Y-%m-%d")
    op = _sanitize_table_cell(operation)
    mid = _sanitize_table_cell(memory_id or "-")
    det = _sanitize_table_cell(detail or "")
    row = f"| {now} | {op} | {mid} | {det} |\n"

    content, inserted = _insert_row_under_table_header(
        content, r"(\|[^\n]*\|[^\n]*\|[^\n]*ID[^\n]*\|[^\n]*\|\n\|[-| ]+\|\n)", row
    )
    if not inserted:
        content += (
            "\n## Recent Activity\n\n"
            "| Time | Operation | Memory ID | Detail |\n"
            "|------|-----------|-----------|--------|\n"
            + row
        )

    content = _refresh_brain_status(content, brain_path=brain_path)
    with open(brain_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def _update_exact_table_row_count(
    content: str,
    key: str,
    operation: str,
    expected_columns: int,
    extra_value: str | None = None,
) -> tuple[str, bool]:
    """精确更新表格中指定行的计数"""
    if not key:
        return content, False
    escaped_key = re.escape(key)
    if expected_columns == 3:
        pattern = rf"^\| {escaped_key} \| (\d+) \| ([^|]+) \|\s*$"
    elif expected_columns == 2:
        pattern = rf"^\| {escaped_key} \| (\d+) \|\s*$"
    else:
        return content, False

    m = re.search(pattern, content, flags=re.MULTILINE)
    if not m:
        return content, False

    current = int(m.group(1))
    if operation == "add":
        nxt = current + 1
    elif operation == "delete":
        nxt = max(0, current - 1)
    else:
        nxt = current

    if expected_columns == 3:
        tail = _sanitize_table_cell(extra_value) if extra_value is not None else _sanitize_table_cell(m.group(2))
        repl = f"| {key} | {nxt} | {tail} |"
    else:
        repl = f"| {key} | {nxt} |"

    return content[: m.start()] + repl + content[m.end() :], True


def update_brain_index(brain_path: str, memory_metadata: dict, operation: str = "add") -> bool:
    """
    更新大脑索引

    统一实现，支持 add/update/delete 操作。
    更新内容包括：
    - 记忆索引表
    - 最近活动记录
    - 状态信息（总记忆数、最近更新时间等）

    Args:
        brain_path: brain.md路径
        memory_metadata: 记忆元数据字典
        operation: 操作类型(add/update/delete)

    Returns:
        bool: 是否成功
    """
    if not os.path.exists(brain_path):
        return False
    content = read_file_safely(brain_path)
    if not content:
        return False

    now = datetime.now().strftime("%Y-%m-%d")
    if operation == "add":
        memory_id = _sanitize_table_cell(memory_metadata.get("id", ""))
        title = _sanitize_table_cell(memory_metadata.get("title", ""))
        category = _sanitize_table_cell(memory_metadata.get("category", "other"))
        project = _sanitize_table_cell(memory_metadata.get("project", ""))
        quality = memory_metadata.get("quality_score", 50)
        strength = memory_metadata.get("strength", 1.0)
        created_at = memory_metadata.get("created_at", "")
        created_date = created_at[:10] if isinstance(created_at, str) and created_at else now
        access_count = memory_metadata.get("access_count", 1)

        row = f"| {memory_id} | {title} | {category} | {project} | {quality} | {strength} | {created_date} | {access_count} |\n"

        # 移除已存在的同名条目并插入新行
        content = re.sub(rf"^\|\s*{re.escape(memory_id)}\s*\|.*$\n?", "", content, flags=re.MULTILINE)
        content, inserted = _insert_row_under_table_header(
            content, r"(\| ID \|.*\n\|[-| ]+\|\n)", row
        )
        if not inserted:
            content += (
                "\n## Memory Index\n\n"
                "| ID | Title | Category | Project | Quality | Strength | Created At | Access Count |\n"
                "|----|-------|----------|---------|---------|----------|------------|--------------|\n"
                + row
            )

        # 记录活动
        activity_row = f"| {now} | create | {memory_id} | {title} |\n"
        content, inserted = _insert_row_under_table_header(
            content, r"(\|[^\n]*\|[^\n]*\|[^\n]*ID[^\n]*\|[^\n]*\|\n\|[-| ]+\|\n)", activity_row
        )
        if not inserted:
            content += (
                "\n## Recent Activity\n\n"
                "| Time | Operation | Memory ID | Detail |\n"
                "|------|-----------|-----------|--------|\n"
                + activity_row
            )

    content = _refresh_brain_status(content, brain_path=brain_path)
    with open(brain_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def update_cue_network(
    brain_path: str,
    category: str | None = None,
    project: str | None = None,
    keywords: list[str] | None = None,
    memory_id: str | None = None,
    operation: str = "add",
) -> bool:
    """
    更新线索网络

    更新内容包括：
    - 类别索引计数
    - 项目索引计数和日期
    - 关键词索引计数

    Args:
        brain_path: brain.md路径
        category: 类别
        project: 项目名称
        keywords: 关键词列表
        memory_id: 记忆ID（保留参数兼容性）
        operation: 操作类型(add/delete)

    Returns:
        bool: 是否成功
    """
    if not os.path.exists(brain_path):
        return False
    content = read_file_safely(brain_path)
    if not content:
        return False

    if category:
        content, _ = _update_exact_table_row_count(content, category, operation, expected_columns=3)

    if project and project != "-":
        now = datetime.now().strftime("%Y-%m-%d")
        content, updated = _update_exact_table_row_count(
            content, project, operation, expected_columns=3, extra_value=now
        )
        if not updated and operation == "add":
            content, _ = _insert_row_under_table_header(
                content,
                r"(###\s+(?:项目索引|Project Index)\s*\n\n\|[^\n]*\|[^\n]*\|[^\n]*\|\n\|[-| ]+\|\n(?:\| - \| [^\n]*\|[^\n]*\|\n)?)",
                f"| {project} | 1 | {now} |\n",
            )

    if keywords:
        for kw in keywords:
            content, updated = _update_exact_table_row_count(content, kw, operation, expected_columns=2)
            if not updated and operation == "add":
                content, _ = _insert_row_under_table_header(
                    content,
                    r"(###\s+(?:关键词索引|Keyword Index)\s*\n\n\|[^\n]*\|[^\n]*\|\n\|[-| ]+\|\n(?:\| - \| [^\n]*\|\n)?)",
                    f"| {kw} | 1 |\n",
                )

    content = _refresh_brain_status(content, brain_path=brain_path)
    with open(brain_path, "w", encoding="utf-8") as f:
        f.write(content)
    return True


def normalize_category(category: str | None) -> str:
    """
    规范化类别名称

    Args:
        category: 原始类别字符串

    Returns:
        str: 规范化后的类别（如果不在默认类别中则返回'other'）
    """
    if not category:
        return "other"
    c = category.strip().lower()
    return c if c in DEFAULT_CATEGORIES else "other"


def normalize_keywords(raw_keywords) -> list[str]:
    """
    规范化关键词列表

    Args:
        raw_keywords: 原始关键词（可以是字符串、列表或其他类型）

    Returns:
        list[str]: 清洗后的去重关键词列表
    """
    if raw_keywords is None:
        return []
    if isinstance(raw_keywords, list):
        items = raw_keywords
    elif isinstance(raw_keywords, str):
        items = [x.strip() for x in raw_keywords.split(",")]
    else:
        items = [str(raw_keywords)]

    seen = set()
    out = []
    for kw in items:
        kw = kw.strip()
        if not kw:
            continue
        key = kw.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(kw)
    return out


def infer_title(content: str | None, fallback: str = "Untitled Memory") -> str:
    """
    从内容推断标题

    优先级：第一个 H1 标题 > 第一个非空行 > fallback

    Args:
        content: 内容文本
        fallback: 兜底标题

    Returns:
        str: 推断出的标题
    """
    if not content:
        return fallback
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()[:100]
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line[:100]
    return fallback


def simple_keyword_extraction(text: str, max_keywords: int = 5) -> list[str]:
    """
    轻量级关键词提取（无外部依赖）

    使用简单的词频统计方法提取关键词。

    Args:
        text: 输入文本
        max_keywords: 最大返回关键词数量

    Returns:
        list[str]: 按频率排序的关键词列表
    """
    if not text:
        return []
    text = re.sub(r"```[\s\S]*?```", " ", text)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_\-+#]{1,}", text)
    tokens = [t.lower() if re.match(r"[A-Za-z]", t) else t for t in tokens]

    stopwords = {
        "the", "and", "with", "for", "from", "this", "that", "these", "those",
        "using", "use", "used", "into", "over", "under", "about", "need",
        "have", "has", "had", "will", "would", "can", "could", "should",
        "please", "help", "issue", "problem", "solution", "change", "update",
        "task", "project", "feature", "code", "file", "memory",
    }
    filtered = [t for t in tokens if len(t) >= 2 and t not in stopwords]
    if not filtered:
        return []

    counts = Counter(filtered)
    ranked = sorted(counts.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    return [kw for kw, _ in ranked[:max_keywords]]


def estimate_quality_score(content: str) -> int:
    """
    估算记忆质量分数

    基于内容的长度、是否包含代码块、是否有标题等因素评分。

    Args:
        content: 记忆内容

    Returns:
        int: 质量分数 (0-100)
    """
    if not content:
        return 30
    score = 50
    length = len(content)
    if length > 800:
        score += 10
    if length > 1500:
        score += 10
    if "```" in content:
        score += 10
    if re.search(r"^#{2,}\s+", content, re.MULTILINE):
        score += 5
    if length < 200:
        score -= 15
    return max(0, min(100, score))
