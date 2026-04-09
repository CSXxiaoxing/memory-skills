#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forget_memory.py - 遗忘机制管理脚本

功能：
- 冲突遗忘：检测同文件的新变更，覆盖旧记忆
- 时间遗忘：自动遗忘长期未访问的低强度记忆
- 归档处理：将遗忘的记忆移动到archive目录

使用方式：
python forget_memory.py --check          # 检查遗忘
python forget_memory.py --archive <id>   # 手动归档某记忆
python forget_memory.py --stats          # 显示遗忘统计
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple, List

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))

from project_utils import get_memory_dir, resolve_brain_path


def resolve_memory_paths(brain_path: Path) -> tuple[Path, Path]:
    """根据brain路径解析记忆目录和归档目录"""
    brain_path = Path(brain_path)
    memories_dir = get_memory_dir(brain_path)
    archive_dir = brain_path.parent / "archive"
    return memories_dir, archive_dir


def load_brain_index(brain_path):
    """加载brain.md索引"""
    try:
        with open(brain_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except Exception as e:
        return {"memories": [], "content": ""}

    memories = []

    # 解析记忆索引表
    pattern = r'\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|\s*([\d.]+)\s*\|\s*([^|]+?)\s*\|\s*(\d+)\s*\|'
    for match in re.finditer(pattern, content):
        mem_id = match.group(1).strip()
        if mem_id and mem_id != "(空)" and mem_id != "ID":
            memories.append({
                "id": mem_id,
                "title": match.group(2).strip(),
                "category": match.group(3).strip(),
                "project": match.group(4).strip(),
                "quality": int(match.group(5)),
                "strength": float(match.group(6)),
                "updated": match.group(7).strip(),
                "access_count": int(match.group(8))
            })

    return {"memories": memories, "content": content}


def get_memory_content(memory_id, memories_dir):
    """获取记忆文件内容"""
    # 尝试在coding目录下查找
    for category in ["coding", "design", "config", "docs", "debug", "other"]:
        mem_file = memories_dir / category / f"{memory_id}.md"
        if mem_file.exists():
            try:
                with open(mem_file, 'r', encoding='utf-8') as f:
                    return f.read()
            except:
                pass

    # 尝试从ID提取（mem_xxx格式）
    if memory_id.startswith("mem_") or memory_id.startswith("diff_"):
        filename = memory_id[4:] + ".md" if memory_id.startswith("mem_") else memory_id + ".md"
        for category in ["coding", "design", "config", "docs", "debug", "other"]:
            mem_file = memories_dir / category / filename
            if mem_file.exists():
                try:
                    with open(mem_file, 'r', encoding='utf-8') as f:
                        return f.read()
                except:
                    pass

    return None


def extract_files_from_memory(memory_content):
    """从记忆内容中提取关联的文件列表"""
    files = []
    if not memory_content:
        return files

    # 查找Diff内容区域的文件
    patterns = [
        r'`([^`]+\.(?:py|js|ts|java|go|rs|cpp|c|h|json|yaml|yml|xml|html|css))`',  # 代码块中的文件
        r'/([a-zA-Z0-9_./]+\.(?:py|js|ts|java|go|rs|cpp|c|h|json|yaml|yml|xml|html|css))',  # 路径格式
        r'\| `([^`]+)` \|',  # 表格中的文件
    ]

    for pattern in patterns:
        for match in re.finditer(pattern, memory_content):
            file_path = match.group(1)
            if file_path and len(file_path) > 3:
                files.append(file_path)

    return list(set(files))


def check_conflict_forgetting(memory_id, memories_data, current_diff_files, memories_dir):
    """
    检查是否应该冲突遗忘

    规则：
    1. 新变更修改了某个文件
    2. 旧记忆也涉及同一个文件
    3. 新记忆的复杂度 >= 旧记忆复杂度
    """
    memory = next((m for m in memories_data["memories"] if m["id"] == memory_id), None)
    if not memory:
        return False, None

    # 获取记忆内容
    content = get_memory_content(memory_id, memories_dir)

    if not content:
        return False, None

    # 提取记忆关联的文件
    memory_files = extract_files_from_memory(content)

    # 检查文件重叠
    overlap = set(memory_files) & set(current_diff_files)
    if overlap:
        return True, {
            "reason": f"File conflict: {', '.join(overlap)}",
            "old_quality": memory["quality"],
            "new_files": list(overlap)
        }

    return False, None


def check_time_forgetting(memory, max_days=30, min_strength=0.2):
    """
    检查是否应该时间遗忘

    规则：
    1. 超过max_days天未访问
    2. 记忆强度低于min_strength
    3. 访问次数为0或很低
    """
    if not memory.get("updated"):
        return False, None

    try:
        # 尝试解析日期
        updated_str = memory["updated"]
        # 支持多种日期格式
        for fmt in ["%Y-%m-%d", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S"]:
            try:
                updated_date = datetime.strptime(updated_str.split("T")[0], "%Y-%m-%d")
                break
            except:
                continue
        else:
            return False, None

        days_since = (datetime.now() - updated_date).days
        strength = memory.get("strength", 1.0)
        access_count = memory.get("access_count", 0)

        # 遗忘条件
        old_and_weak = days_since > max_days and strength < min_strength
        never_accessed = access_count == 0 and days_since > max_days * 2

        if old_and_weak or never_accessed:
            return True, {
                "reason": f"Time-based: {days_since} days old, strength {strength:.2f}",
                "days_since": days_since,
                "strength": strength,
                "access_count": access_count
            }

    except Exception as e:
        pass

    return False, None


def check_coverage_forgetting(old_memory, new_memory):
    """
    检查是否应该覆盖遗忘
    新记忆完全覆盖旧记忆时，标记旧记忆为遗忘
    """
    if not old_memory or not new_memory:
        return False

    old_quality = old_memory.get("quality", 0)
    new_quality = new_memory.get("quality", 0)

    # 新记忆质量明显高于旧记忆
    if new_quality > old_quality * 1.5:
        return True

    return False


def archive_memory(memory_id, memories_dir, archive_dir, reason=""):
    """归档记忆"""
    # 查找源文件
    source_file = None
    for category in ["coding", "design", "config", "docs", "debug", "other"]:
        mem_file = memories_dir / category / f"{memory_id}.md"
        if mem_file.exists():
            source_file = mem_file
            break
        # 也尝试 mem_xxx.md 格式
        if memory_id.startswith("diff_"):
            mem_file = memories_dir / category / f"{memory_id}.md"
        elif memory_id.startswith("mem_"):
            mem_file = memories_dir / category / f"{memory_id[4:]}.md"
        if mem_file.exists():
            source_file = mem_file
            break

    if not source_file:
        return False, f"Memory file not found: {memory_id}"

    # 创建归档目录
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 移动到归档
    archive_file = archive_dir / f"{memory_id}.md"
    try:
        # 读取内容
        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 添加遗忘标记
        now = datetime.now().isoformat()
        forgotten_content = content.replace(
            "---",
            f"---\nforgotten_at: {now}\nforgotten_reason: {reason}",
            1
        )

        # 写入归档
        with open(archive_file, 'w', encoding='utf-8') as f:
            f.write(forgotten_content)

        # 删除源文件
        source_file.unlink()

        return True, f"Archived to {archive_file}"

    except Exception as e:
        return False, f"Failed to archive: {e}"


def update_brain_after_forget(brain_path, memory_id):
    """从brain.md中移除已遗忘的记忆"""
    try:
        with open(brain_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # 移除记忆索引行
        pattern = rf'\|\s*{re.escape(memory_id)}\s*\|[^|]*\|[^|]*\|[^|]*\|\d+\|[\d.]+\|[^|]*\|\d+\|'
        content = re.sub(pattern, '| (空) | - | - | - | - | - | - | - |', content)

        # 更新总数
        match = re.search(r"\| 总记忆数 \| (\d+) \|")
        if match:
            current = int(match.group(1))
            new_count = max(0, current - 1)
            content = content.replace(
                f"| 总记忆数 | {current} |",
                f"| 总记忆数 | {new_count} |"
            )

        # 添加遗忘活动记录
        now = datetime.now().strftime('%Y-%m-%d %H:%M')
        old_empty = "| - | - | - | - |"
        new_entry = f"| {now} | 遗忘 | {memory_id} | 系统自动遗忘 |\n{old_empty}"
        content = content.replace(old_empty, new_entry)

        with open(brain_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return True

    except Exception as e:
        return False, str(e)


def check_and_forget(brain_path, current_diff_files=None, dry_run=True):
    """
    检查并执行遗忘

    Args:
        brain_path: brain.md路径
        current_diff_files: 当前diff涉及的文件列表
        dry_run: True=只检查不执行，False=执行遗忘
    """
    memories_dir, archive_dir = resolve_memory_paths(Path(brain_path))

    # 确保目录存在
    archive_dir.mkdir(parents=True, exist_ok=True)

    # 加载记忆索引
    memories_data = load_brain_index(brain_path)

    if not memories_data["memories"]:
        return {
            "checked": 0,
            "forgotten": 0,
            "candidates": [],
            "message": "No memories to check"
        }

    candidates = []
    forgotten_count = 0

    for memory in memories_data["memories"]:
        memory_id = memory["id"]
        forget_reason = None
        forget_type = None

        # 1. 检查冲突遗忘
        if current_diff_files:
            is_conflict, conflict_info = check_conflict_forgetting(
                memory_id, memories_data, current_diff_files, memories_dir
            )
            if is_conflict:
                forget_reason = conflict_info["reason"]
                forget_type = "conflict"

        # 2. 检查时间遗忘
        if not forget_reason:
            is_old, time_info = check_time_forgetting(memory)
            if is_old:
                forget_reason = time_info["reason"]
                forget_type = "time"

        if forget_reason:
            candidates.append({
                "id": memory_id,
                "title": memory["title"],
                "reason": forget_reason,
                "type": forget_type,
                "quality": memory["quality"],
                "strength": memory.get("strength", 1.0),
                "updated": memory.get("updated", "unknown")
            })

            if not dry_run:
                # 执行归档
                success, msg = archive_memory(memory_id, memories_dir, archive_dir, forget_reason)
                if success:
                    update_brain_after_forget(brain_path, memory_id)
                    forgotten_count += 1

    return {
        "checked": len(memories_data["memories"]),
        "forgotten": forgotten_count if not dry_run else 0,
        "candidates": candidates,
        "message": f"Found {len(candidates)} memories to forget (dry run)" if dry_run else f"Archived {forgotten_count} memories"
    }


def get_forget_stats(brain_path):
    """获取遗忘统计"""
    memories_dir, archive_dir = resolve_memory_paths(Path(brain_path))

    # 加载当前记忆
    memories_data = load_brain_index(brain_path)

    # 统计归档记忆
    archived_count = 0
    if archive_dir.exists():
        archived_count = len(list(archive_dir.glob("*.md")))

    # 统计遗忘原因
    time_forget_candidates = 0
    conflict_forget_candidates = 0

    for memory in memories_data["memories"]:
        is_old, _ = check_time_forgetting(memory)
        if is_old:
            time_forget_candidates += 1

    # 分类统计
    by_category = {}
    for memory in memories_data["memories"]:
        cat = memory.get("category", "other")
        by_category[cat] = by_category.get(cat, 0) + 1

    by_quality = {"high": 0, "medium": 0, "low": 0}
    for memory in memories_data["memories"]:
        q = memory.get("quality", 50)
        if q >= 70:
            by_quality["high"] += 1
        elif q >= 40:
            by_quality["medium"] += 1
        else:
            by_quality["low"] += 1

    return {
        "current_memories": len(memories_data["memories"]),
        "archived_memories": archived_count,
        "time_forget_candidates": time_forget_candidates,
        "by_category": by_category,
        "by_quality": by_quality,
        "total_capacity": 300,  # 估算容量
        "usage_rate": len(memories_data["memories"]) / 300 * 100
    }


def main():
    parser = argparse.ArgumentParser(
        description="遗忘机制管理脚本",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="检查遗忘候选")
    parser.add_argument("--execute", action="store_true", help="执行遗忘（默认是dry-run）")
    parser.add_argument("--archive", type=str, help="手动归档指定记忆ID")
    parser.add_argument("--stats", action="store_true", help="显示遗忘统计")
    parser.add_argument("--brain-path", type=str, help="brain.md路径")
    parser.add_argument("--project-root", type=str, help="项目根目录(可选,用于自动定位brain)")

    args = parser.parse_args()

    # 设置brain路径
    if args.brain_path:
        brain_path = resolve_brain_path(explicit_path=args.brain_path)
    else:
        brain_path = resolve_brain_path(start_path=args.project_root or os.getcwd())

    if not brain_path.exists():
        print(f"Brain file not found: {brain_path}")
        return 1

    # 显示统计
    if args.stats:
        stats = get_forget_stats(brain_path)
        print("\n=== 遗忘统计 ===")
        print(f"当前记忆数: {stats['current_memories']}")
        print(f"已归档记忆: {stats['archived_memories']}")
        print(f"时间遗忘候选: {stats['time_forget_candidates']}")
        print(f"\n按类别分布:")
        for cat, count in stats["by_category"].items():
            print(f"  {cat}: {count}")
        print(f"\n按质量分布:")
        print(f"  高质量(>70): {stats['by_quality']['high']}")
        print(f"  中质量(40-70): {stats['by_quality']['medium']}")
        print(f"  低质量(<40): {stats['by_quality']['low']}")
        print(f"\n容量使用率: {stats['usage_rate']:.1f}%")
        return 0

    # 检查遗忘候选
    if args.check:
        result = check_and_forget(brain_path, dry_run=not args.execute)
        print(f"\n=== 遗忘检查结果 ===")
        print(f"检查记忆数: {result['checked']}")
        print(f"遗忘候选数: {len(result['candidates'])}")
        print(f"消息: {result['message']}")

        if result['candidates']:
            print(f"\n遗忘候选列表:")
            for i, candidate in enumerate(result['candidates'], 1):
                print(f"  {i}. [{candidate['type']}] {candidate['id']}")
                print(f"     标题: {candidate['title']}")
                print(f"     原因: {candidate['reason']}")
                print(f"     质量: {candidate['quality']}, 强度: {candidate.get('strength', 1.0):.2f}")

        if not args.execute:
            print(f"\n(这是dry-run模式，使用 --execute 实际执行遗忘)")

        return 0

    # 手动归档
    if args.archive:
        memories_dir, archive_dir = resolve_memory_paths(Path(brain_path))
        success, msg = archive_memory(args.archive, memories_dir, archive_dir, "Manual archive")
        if success:
            update_brain_after_forget(brain_path, args.archive)
            print(f"Success: {msg}")
        else:
            print(f"Failed: {msg}")
        return 0 if success else 1

    # 无参数时显示帮助
    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
