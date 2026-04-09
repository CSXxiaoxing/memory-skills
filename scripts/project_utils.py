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
import shutil
from hashlib import sha1
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional


PROJECT_MARKERS = ["package.json", "Cargo.toml", "go.mod"]
LEGACY_STORAGE_NAMES = [
    "memories",
    "archive",
    "references",
    "fragment_memory.md",
    "user_profile.md",
    "lessons_learned.md",
]

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
    1) .git exists
    2) package.json / Cargo.toml / go.mod exists
    3) fallback to nearest existing .memory/brain.md
    4) fallback to start_path
    """
    start = Path(start_path or os.getcwd()).expanduser().resolve()
    if start.exists() and start.is_file():
        start = start.parent

    candidates = [start] + list(start.parents)
    memory_fallback: Optional[Path] = None

    # Pass 1: strict .git priority across all ancestors.
    for candidate in candidates:
        if (candidate / ".git").exists():
            return candidate

    # Pass 2: project marker fallback.
    for candidate in candidates:
        if any((candidate / marker).exists() for marker in PROJECT_MARKERS):
            return candidate
        if memory_fallback is None and (candidate / ".memory" / "brain.md").exists():
            memory_fallback = candidate

    return memory_fallback or start


def _migrate_legacy_storage(root: Path, dot_brain: Path) -> None:
    """
    Migrate legacy root-level storage into <root>/.memory once.

    Legacy layout:
    - <root>/brain.md
    - <root>/memories
    - <root>/archive
    - ...
    """
    legacy_brain = root / "brain.md"
    dot_root = dot_brain.parent

    if not legacy_brain.exists():
        return

    dot_root.mkdir(parents=True, exist_ok=True)

    # Migrate brain.md first so all scripts converge to a single store.
    if not dot_brain.exists():
        shutil.move(str(legacy_brain), str(dot_brain))

    # Migrate known legacy side files/directories when destination is empty.
    for name in LEGACY_STORAGE_NAMES:
        source = root / name
        target = dot_root / name
        if source.exists() and not target.exists():
            shutil.move(str(source), str(target))


def _file_sha1(path: Path) -> str:
    """计算文件sha1"""
    h = sha1()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(8192)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def _move_conflict_file(source_file: Path, target_memory_root: Path, conflict_group: str) -> None:
    """将冲突文件移动到根.memory/archive/shadow_conflicts"""
    conflict_root = (
        target_memory_root
        / "archive"
        / "shadow_conflicts"
        / conflict_group
    )
    conflict_root.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source_file), str(conflict_root / source_file.name))


def _merge_shadow_memory_dir(
    source_dir: Path,
    target_dir: Path,
    target_memory_root: Path,
    conflict_group: str,
) -> None:
    """递归合并shadow .memory到目标.memory"""
    target_dir.mkdir(parents=True, exist_ok=True)
    for item in source_dir.iterdir():
        target_item = target_dir / item.name
        if item.is_dir():
            if target_item.exists() and target_item.is_dir():
                _merge_shadow_memory_dir(item, target_item, target_memory_root, conflict_group)
                try:
                    item.rmdir()
                except OSError:
                    pass
            elif not target_item.exists():
                shutil.move(str(item), str(target_item))
            else:
                # 类型冲突：保留目标，源目录整体归档
                archive_dir = target_memory_root / "archive" / "shadow_conflicts" / conflict_group
                archive_dir.mkdir(parents=True, exist_ok=True)
                shutil.move(str(item), str(archive_dir / item.name))
        elif item.is_file():
            if not target_item.exists():
                shutil.move(str(item), str(target_item))
            else:
                # 同名文件：内容相同则删除源，不同则归档源
                try:
                    same = _file_sha1(item) == _file_sha1(target_item)
                except OSError:
                    same = False
                if same:
                    item.unlink(missing_ok=True)
                else:
                    _move_conflict_file(item, target_memory_root, conflict_group)


def _migrate_shadow_memory_storage(root: Path, start_path: Optional[str | Path]) -> None:
    """
    合并并清理 root 之下路径上的 shadow .memory。

    典型场景：
    <git-root>/.memory 以及 <git-root>/subproj/.memory 并存。
    """
    if start_path is None:
        return

    start = Path(start_path).expanduser().resolve()
    if start.exists() and start.is_file():
        start = start.parent

    root = root.resolve()
    if start == root:
        return

    try:
        start.relative_to(root)
    except ValueError:
        # start 不在 root 下，不处理
        return

    target_memory_root = root / ".memory"
    target_memory_root.mkdir(parents=True, exist_ok=True)

    # 只处理 start 到 root 之间祖先路径上的 shadow .memory（不含 root）
    path_chain = [start] + list(start.parents)
    conflict_group = datetime.now().strftime("%Y%m%d_%H%M%S_shadow")
    for candidate in path_chain:
        if candidate == root:
            break
        shadow = candidate / ".memory"
        if not shadow.exists() or not shadow.is_dir():
            continue
        _merge_shadow_memory_dir(shadow, target_memory_root, target_memory_root, conflict_group)
        try:
            shadow.rmdir()
        except OSError:
            pass


def _is_under_nested_git_repo(path: Path, root: Path) -> bool:
    """判断 path 是否位于 root 之下的嵌套 git 仓库内"""
    cur = path.resolve()
    root = root.resolve()
    while cur != root and cur != cur.parent:
        if (cur / ".git").exists():
            return True
        cur = cur.parent
    return False


def _migrate_descendant_shadow_memories(root: Path) -> None:
    """
    兜底清理 root 下遗留的子目录 .memory（跳过嵌套 git 仓库）。
    """
    root = root.resolve()
    target_memory_root = root / ".memory"
    target_memory_root.mkdir(parents=True, exist_ok=True)
    conflict_group = datetime.now().strftime("%Y%m%d_%H%M%S_shadow_desc")

    skip_dirs = {".git", "node_modules", ".venv", "venv", "__pycache__"}
    for current, dirs, _ in os.walk(root, topdown=True):
        current_path = Path(current)
        dirs[:] = [d for d in dirs if d not in skip_dirs]

        if ".memory" not in dirs:
            continue

        shadow = current_path / ".memory"
        if shadow.resolve() == target_memory_root:
            dirs.remove(".memory")
            continue

        # 如果该路径在嵌套git仓库下，视为独立项目，不做跨仓合并
        if _is_under_nested_git_repo(current_path, root):
            dirs.remove(".memory")
            continue

        _merge_shadow_memory_dir(shadow, target_memory_root, target_memory_root, conflict_group)
        try:
            shadow.rmdir()
        except OSError:
            pass
        dirs.remove(".memory")


def resolve_brain_path(
    start_path: Optional[str | Path] = None,
    explicit_path: Optional[str | Path] = None,
    prefer_dot_memory: bool = True,
) -> Path:
    """
    Resolve brain.md path.

    - If explicit_path provided, use it.
    - Otherwise detect project root via .git/project markers.
    - Prefer <root>/.memory/brain.md as the unique writable location.
    - Auto-migrate legacy <root>/brain.md + side folders into .memory.
    - If prefer_dot_memory is False, allow legacy path fallback.
    """
    if explicit_path:
        return Path(explicit_path).expanduser().resolve()

    root = find_project_root(start_path)
    dot_brain = root / ".memory" / "brain.md"
    legacy_brain = root / "brain.md"

    if prefer_dot_memory and legacy_brain.exists() and not dot_brain.exists():
        _migrate_legacy_storage(root, dot_brain)
    if prefer_dot_memory:
        _migrate_shadow_memory_storage(root, start_path)
        _migrate_descendant_shadow_memories(root)

    if dot_brain.exists():
        return dot_brain
    if not prefer_dot_memory and legacy_brain.exists():
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
    """统计记忆索引表中的有效行数（支持 mem_/diff_ 等任意ID）"""
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
        if not line.startswith("|"):
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        # 记忆索引表标准列数为8；首列是ID，不能是占位符
        if len(parts) < 8:
            continue
        memory_id = parts[0]
        if memory_id in {"", "-", "(空)", "ID"}:
            continue
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

    # v2 format: "- [time] (score:x) note"
    count = 0
    for m in re.finditer(r"^\- \[([^\]]+)\] \(score:(-?\d+)\) .+$", content, flags=re.MULTILINE):
        tag = m.group(1).strip().lower()
        if tag == "empty":
            continue
        count += 1

    # v1 legacy format fallback: section titles by date
    if count == 0:
        count = len(re.findall(r"^##\s+\d{4}-\d{2}-\d{2}\b.*$", content, flags=re.MULTILINE))

    return count


def _count_markdown_files(directory: Path) -> int:
    """统计目录中的Markdown文件数量（递归）"""
    if not directory.exists() or not directory.is_dir():
        return 0
    return sum(1 for f in directory.rglob("*.md") if f.is_file())


def _collect_memory_statistics(brain_path: str | Path | None) -> dict:
    """
    汇总记忆统计（以磁盘真实文件为准）。

    统计口径：
    - standalone: .memory/memories 下各分类 md 文件
    - docs 扩展: user_profile.md + lessons_learned.md + references/*.md
    - other 扩展: fragment_memory 条目数
    """
    counts = {cat: 0 for cat in DEFAULT_CATEGORIES}
    if not brain_path:
        return {
            "category_counts": counts,
            "standalone_count": 0,
            "fragment_count": 0,
            "docs_extra_count": 0,
            "total_count": 0,
        }

    brain_root = Path(brain_path).parent
    memories_dir = get_memory_dir(brain_path)
    memories_dir.mkdir(parents=True, exist_ok=True)

    # 1) 主记忆目录（真实文件数）
    standalone_count = 0
    for cat in DEFAULT_CATEGORIES:
        cat_dir = memories_dir / cat
        cat_dir.mkdir(parents=True, exist_ok=True)
        cat_count = _count_markdown_files(cat_dir)
        counts[cat] += cat_count
        standalone_count += cat_count

    # 未知分类目录按 other 计
    for child in memories_dir.iterdir():
        if not child.is_dir():
            continue
        if child.name in DEFAULT_CATEGORIES:
            continue
        extra = _count_markdown_files(child)
        counts["other"] += extra
        standalone_count += extra

    # 2) 扩展记忆：碎片记忆记入 other；画像/经验/参考文档记入 docs
    fragment_count = _count_fragment_entries(brain_path)
    counts["other"] += fragment_count

    docs_extra_count = 0
    for aux_name in ["user_profile.md", "lessons_learned.md"]:
        p = brain_root / aux_name
        txt = read_file_safely(p)
        if txt and txt.strip():
            docs_extra_count += 1
    docs_extra_count += _count_markdown_files(brain_root / "references")
    counts["docs"] += docs_extra_count

    return {
        "category_counts": counts,
        "standalone_count": standalone_count,
        "fragment_count": fragment_count,
        "docs_extra_count": docs_extra_count,
        "total_count": standalone_count + fragment_count + docs_extra_count,
    }


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


def _set_status_bullet_value(content: str, keys: list[str], value: str) -> str:
    """设置状态列表中的项目（兼容 '- **总记忆数**: 123' 格式）"""
    for key in keys:
        pattern = rf"^-\s*\*\*{re.escape(key)}\*\*:\s*.*$"
        if re.search(pattern, content, flags=re.MULTILINE):
            return re.sub(
                pattern,
                f"- **{key}**: {value}",
                content,
                count=1,
                flags=re.MULTILINE,
            )
    return content


def _render_category_index_table(category_counts: dict[str, int], heading_level: str = "##") -> str:
    """渲染类别索引表"""
    dominant_label = {"left": "左脑", "right": "右脑", "both": "双脑"}
    lines = [
        f"{heading_level} 类别索引",
        "",
        "| 类别 | 数量 | 脑主导 |",
        "|------|------|--------|",
    ]
    for cat in DEFAULT_CATEGORIES:
        dominant = CATEGORY_BRAIN_DOMINANT.get(cat, "both")
        lines.append(f"| {cat} | {int(category_counts.get(cat, 0))} | {dominant_label.get(dominant, dominant)} |")
    return "\n".join(lines) + "\n\n"


def _sync_category_index_table(content: str, category_counts: dict[str, int]) -> str:
    """将类别索引表同步为真实统计"""
    pattern = (
        r"^#{2,3}\s*(?:类别索引|Category Index)\s*\n"
        r"(?:\n)?"
        r"\|[^\n]*\|\n"
        r"\|[-| ]+\|\n"
        r"(?:\|.*\|\n)*"
    )
    matches = list(re.finditer(pattern, content, flags=re.MULTILINE))
    if matches:
        # 先移除重复块（保留第一个）
        deduped = content
        for m in reversed(matches[1:]):
            deduped = deduped[: m.start()] + deduped[m.end() :]

        first = re.search(pattern, deduped, flags=re.MULTILINE)
        if not first:
            return deduped

        heading_m = re.match(r"^(#{2,3})\s*", first.group(0))
        heading_level = heading_m.group(1) if heading_m else "##"
        table = _render_category_index_table(category_counts, heading_level=heading_level)

        # 替换唯一块
        return deduped[: first.start()] + table + deduped[first.end() :]

    # 未找到类别表时，尽量插到项目索引前；否则追加到末尾
    table = _render_category_index_table(category_counts, heading_level="##")
    project_m = re.search(r"^#{2,3}\s+(?:项目索引|Project Index)\s*$", content, flags=re.MULTILINE)
    if project_m:
        return content[: project_m.start()] + table + content[project_m.start() :]
    memory_m = re.search(r"^#{2,3}\s+(?:记忆索引表|Memory Index)\s*$", content, flags=re.MULTILINE)
    if memory_m:
        return content[: memory_m.start()] + table + content[memory_m.start() :]
    return content.rstrip() + "\n\n" + table


def _refresh_brain_status(content: str, brain_path: str | Path | None = None) -> str:
    """刷新brain.md的状态信息（总记忆数、总线索数、最近更新时间）"""
    now = datetime.now().strftime("%Y-%m-%d")
    stats = _collect_memory_statistics(brain_path)
    # 无法读取磁盘统计时回退到索引表统计
    memory_count = stats["total_count"] if stats["total_count"] > 0 else (_count_memory_index_rows(content) + _count_fragment_entries(brain_path))
    cue_count = _count_keyword_index_rows(content)

    content = _sync_category_index_table(content, stats["category_counts"])
    content = _set_status_row_value(content, ["总记忆数", "Total Memories"], str(memory_count))
    content = _set_status_row_value(content, ["总线索数", "Total Cues"], str(cue_count))
    content = _set_status_row_value(content, ["最近更新", "Last Updated"], now)
    content = _set_status_bullet_value(content, ["总记忆数", "Total Memories"], str(memory_count))
    content = _set_status_bullet_value(content, ["总线索数", "Total Cues"], str(cue_count))
    content = _set_status_bullet_value(content, ["最近更新", "Last Updated"], now)
    content = re.sub(r"^updated_at:\s*.*$", f"updated_at: {now}", content, count=1, flags=re.MULTILINE)
    
    # 增加自动一致性校验标记
    if brain_path:
        index_count = _count_memory_index_rows(content)
        if index_count != stats["standalone_count"]:
            # 检测到不一致时添加注释标记
            inconsistency_note = f"<!-- 索引不一致警告: 索引{index_count}条, 实际文件{stats['standalone_count']}条, 请运行sync_index.py修复 -->"
            if inconsistency_note not in content:
                # 插入到文件开头
                if content.startswith("---"):
                    # 有YAML头，插入到YAML头之后
                    parts = content.split("---", 2)
                    if len(parts) >=3:
                        content = f"---{parts[1]}---\n{inconsistency_note}\n{parts[2]}"
                else:
                    # 无YAML头，直接插入到开头
                    content = f"{inconsistency_note}\n{content}"
    
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

    # 类别计数已由_refresh_brain_status自动基于真实文件统计，无需手动更新

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
        "task", "project", "feature", "code", "file"
        # 不移除核心关键词：记忆
    }
    
    filtered = [t for t in tokens if len(t) >= 2 and t not in stopwords]
    if not filtered:
        return []

    counts = Counter(filtered)
    ranked = sorted(counts.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    return [kw for kw, _ in ranked[:max_keywords]]


def get_synonyms(word: str) -> list[str]:
    """获取词的同义词（支持中英文）"""
    synonym_map = {
        "记忆": ["记忆", "记性", "记忆点", "memory", "memories"],
        "memory": ["记忆", "记性", "记忆点", "memory", "memories"],
        "创建": ["创建", "生成", "新建", "create", "add", "new"],
        "create": ["创建", "生成", "新建", "create", "add", "new"],
        "测试": ["测试", "验证", "test", "验证", "check"],
        "test": ["测试", "验证", "test", "验证", "check"],
        "纠正": ["纠正", "修正", "更正", "错误", "不对", "错了", "correction", "fix", "wrong", "error"],
        "correction": ["纠正", "修正", "更正", "错误", "不对", "错了", "correction", "fix", "wrong", "error"],
        "统计": ["统计", "计数", "统计信息", "stats", "statistics", "count"],
        "stats": ["统计", "计数", "统计信息", "stats", "statistics", "count"],
        "压缩": ["压缩", "精简", "compress", "compact", "squash"],
        "compress": ["压缩", "精简", "compress", "compact", "squash"],
        "检索": ["检索", "搜索", "查找", "search", "find", "query"],
        "search": ["检索", "搜索", "查找", "search", "find", "query"],
        "同步": ["同步", "sync", "同步索引", "synchronize"],
        "sync": ["同步", "sync", "同步索引", "synchronize"],
    }
    return synonym_map.get(word.lower() if isinstance(word, str) and re.match(r"[A-Za-z]", str(word)) else word, [word])


def is_keyword_match(target: str, memory_keywords: list[str], threshold: float = 0.6) -> bool:
    """判断关键词是否匹配，支持同义词和部分匹配"""
    if not target or not memory_keywords:
        return False
    
    # 标准化目标词
    target_norm = target.lower() if re.match(r"[A-Za-z]", target) else target
    
    # 获取所有同义词
    target_synonyms = get_synonyms(target_norm)
    
    # 检查每个记忆关键词
    for kw in memory_keywords:
        if not kw:
            continue
        # 标准化记忆关键词
        kw_norm = kw.lower() if re.match(r"[A-Za-z]", kw) else kw
        
        # 完全匹配
        if kw_norm in target_synonyms or target_norm in get_synonyms(kw_norm):
            return True
        
        # 部分匹配（包含关系）
        for syn in target_synonyms:
            if syn in kw_norm or kw_norm in syn:
                return True
    
    return False


def calculate_semantic_similarity(text1: str, text2: str) -> float:
    """
    计算两个文本的语义相似度（轻量级实现，无外部依赖）
    基于Jaccard相似度 + 关键词匹配 + 同义词扩展
    返回值范围：0-1，值越大相似度越高
    """
    if not text1 or not text2:
        return 0.0
    
    # 提取关键词
    keywords1 = set(simple_keyword_extraction(text1, max_keywords=10))
    keywords2 = set(simple_keyword_extraction(text2, max_keywords=10))
    
    if not keywords1 or not keywords2:
        return 0.0
    
    # 扩展同义词
    expanded1 = set()
    for kw in keywords1:
        expanded1.update(get_synonyms(kw))
    expanded2 = set()
    for kw in keywords2:
        expanded2.update(get_synonyms(kw))
    
    # 计算交集和并集
    intersection = len(expanded1 & expanded2)
    union = len(expanded1 | expanded2)
    
    if union == 0:
        return 0.0
    
    return intersection / union


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
