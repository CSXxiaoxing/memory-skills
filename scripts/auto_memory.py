#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_memory.py - 自动记忆脚本

功能：
- 检测代码变更（git diff）
- 决策是否需要创建记忆
- 自动创建增量Diff记忆
- 管理遗忘机制（冲突遗忘 + 时间遗忘）

触发方式：
1. Git Hook（post-commit, post-merge, post-checkout）
2. 手动运行：python auto_memory.py --check
3. IDE保存时触发
"""

import os
import sys
import re
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from load_brain import load_brain
from project_utils import (
    resolve_brain_path,
    find_project_root,
    read_file_safely,
    generate_memory_id,
    save_memory,
    update_brain_index,
    update_cue_network,
    generate_filename,
    create_memory_document,
)


def run_command(cmd, cwd=None):
    """执行shell命令并返回输出"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, cwd=cwd, timeout=30
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except subprocess.TimeoutExpired:
        return "", "Command timeout", 1
    except Exception as e:
        return "", str(e), 1


def is_git_repo(cwd=None):
    """检查是否为git仓库"""
    stdout, _, code = run_command("git rev-parse --is-inside-work-tree", cwd)
    return code == 0 and stdout == "true"


def get_git_diff(cwd=None):
    """获取git diff信息"""
    if not is_git_repo(cwd):
        return None, "Not a git repository"

    # 获取暂存区差异
    stdout, _, code = run_command("git diff --cached --stat", cwd)
    staged_diff = stdout if code == 0 else ""

    # 获取工作区差异（未提交的）
    stdout, _, code = run_command("git diff --stat", cwd)
    unstaged_diff = stdout if code == 0 else ""

    # 获取最近commit
    stdout, _, code = run_command("git log -1 --format='%H|%s|%an|%ad' --date=iso", cwd)
    last_commit = stdout.split("|") if code == 0 and stdout else []

    return {
        "staged": staged_diff,
        "unstaged": unstaged_diff,
        "last_commit": {
            "hash": last_commit[0] if len(last_commit) > 0 else "",
            "message": last_commit[1] if len(last_commit) > 1 else "",
            "author": last_commit[2] if len(last_commit) > 2 else "",
            "date": last_commit[3] if len(last_commit) > 3 else ""
        } if last_commit else None
    }, None


def get_detailed_diff(cwd=None, file_path=None):
    """获取详细diff"""
    if file_path:
        cmd = f"git diff HEAD -- '{file_path}'"
    else:
        cmd = "git diff HEAD"

    stdout, _, code = run_command(cmd, cwd)
    return stdout if code == 0 else ""


def analyze_change_complexity(diff_content):
    """
    分析变更复杂度，决定是否值得记忆

    返回:
        (should_remember: bool, reason: str, complexity_score: int)
    """
    if not diff_content:
        return False, "No changes", 0

    lines = diff_content.split("\n")
    added_lines = [l for l in lines if l.startswith("+") and not l.startswith("+++")]
    removed_lines = [l for l in lines if l.startswith("-") and not l.startswith("---")]

    # 过滤纯注释和空白变更
    code_added = [l for l in added_lines if not is_comment_or_whitespace(l)]
    code_removed = [l for l in removed_lines if not is_comment_or_whitespace(l)]

    added_count = len(code_added)
    removed_count = len(code_removed)
    total_change = added_count + removed_count

    # 复杂度评分
    complexity = 0

    # 1. 行数评分
    if total_change > 100:
        complexity += 40
    elif total_change > 50:
        complexity += 30
    elif total_change > 20:
        complexity += 20
    elif total_change > 5:
        complexity += 10
    else:
        complexity += 5

    # 2. 是否涉及关键文件
    key_patterns = [
        r"\.py$", r"\.js$", r"\.ts$", r"\.java$", r"\.go$", r"\.rs$",
        r"\.cpp$", r"\.c$", r"\.h$", r"config", r"\.json$", r"\.yaml$"
    ]
    has_key_file = any(re.search(p, diff_content) for p in key_patterns)
    if has_key_file:
        complexity += 20

    # 3. 是否新增文件
    if "new file mode" in diff_content:
        complexity += 15

    # 4. 是否删除文件
    if "delete mode" in diff_content:
        complexity += 25

    # 5. 是否修改接口/函数定义
    if any(kw in diff_content for kw in ["def ", "function ", "class ", "interface ", "struct "]):
        complexity += 20

    # 6. 是否有冲突标记
    if "<<<<<<<" in diff_content or "=======" in diff_content:
        complexity += 30

    # 决策阈值
    should_remember = complexity >= 35

    if complexity >= 60:
        reason = "Complex change (high priority)"
    elif complexity >= 45:
        reason = "Moderate change"
    elif complexity >= 35:
        reason = "Minor change (low priority)"
    else:
        reason = "Trivial change (no memory needed)"

    return should_remember, reason, complexity


def is_comment_or_whitespace(line):
    """判断是否为注释或空白行"""
    stripped = line.strip()
    if not stripped:
        return True
    if stripped.startswith("//"):
        return True
    if stripped.startswith("#"):
        return True
    if stripped.startswith("/*") or stripped.endswith("*/"):
        return True
    if stripped.startswith("<!--") or stripped.endswith("-->"):
        return True
    return False


def extract_changed_files(diff_content):
    """提取变更的文件列表"""
    files = []
    current_file = None
    current_stats = {}

    for line in diff_content.split("\n"):
        # 文件路径行
        if line.startswith("diff --git"):
            match = re.search(r"a/(.+?) b/(.+)", line)
            if match:
                if current_file:
                    files.append({"file": current_file, "stats": current_stats})
                current_file = match.group(2)
                current_stats = {"additions": 0, "deletions": 0}
        # 统计行
        elif line.startswith("+") and not line.startswith("+++"):
            current_stats["additions"] = current_stats.get("additions", 0) + 1
        elif line.startswith("-") and not line.startswith("---"):
            current_stats["deletions"] = current_stats.get("deletions", 0) + 1

    if current_file:
        files.append({"file": current_file, "stats": current_stats})

    return files


def find_related_memory(brain_data, file_path):
    """查找同文件的历史记忆"""
    memories = brain_data.get("memories", [])
    related = []

    for mem in memories:
        mem_id = mem.get("id", "")
        if mem_id.startswith("diff_"):
            # 检查关联文件（从记忆内容中查找）
            if file_path in str(mem):
                related.append(mem)

    return related


def should_forget(old_memory, new_change):
    """
    遗忘决策：判断旧记忆是否应该被遗忘

    规则：
    1. 冲突遗忘：新变更覆盖同文件的旧变更
    2. 时间遗忘：超过N天未访问且强度低于阈值
    3. 覆盖遗忘：新记忆复杂度明显高于旧记忆时
    """
    # 配置参数
    max_age_days = 30
    min_strength_threshold = 0.2

    old_id = old_memory.get("id", "")
    old_strength = old_memory.get("strength", 1.0)
    old_access = old_memory.get("access_count", 0)
    old_updated = old_memory.get("updated_at", "")

    # 1. 冲突遗忘：同文件新变更
    if "file" in new_change:
        # 新变更的文件与旧记忆关联
        pass  # 实际应该解析记忆内容获取关联文件

    # 2. 时间遗忘
    if old_updated:
        try:
            updated_date = datetime.fromisoformat(old_updated.replace("Z", "+00:00"))
            days_since_update = (datetime.now() - updated_date).days
            if days_since_update > max_age_days and old_strength < min_strength_threshold:
                return True, f"Time-based forgetting: {days_since_update} days old, strength {old_strength}"
        except:
            pass

    # 3. 访问遗忘：从未被访问且很旧
    if old_access == 0 and old_strength < 0.1:
        return True, "Never accessed and low strength"

    return False, None


def create_diff_memory(brain_path, diff_content, change_info, parent_id=None):
    """
    创建增量Diff记忆

    Args:
        brain_path: brain.md路径
        diff_content: 详细diff内容
        change_info: 变更信息字典
        parent_id: 父记忆ID（用于链式追踪）
    """
    now = datetime.now()
    memory_id = f"diff_{now.strftime('%Y%m%d_%H%M%S')}_{hash(diff_content) % 1000:03d}"

    # 提取变更文件
    changed_files = extract_changed_files(diff_content)

    # 生成摘要
    summary = generate_diff_summary(diff_content, changed_files)

    # 构建记忆内容
    memory_content = f"""---
id: {memory_id}
type: code_change
version: 1.0
created_at: {now.isoformat()}
updated_at: {now.isoformat()}
parent: {parent_id or ""}
complexity_score: {change_info.get("complexity", 0)}
quality_score: {min(100, change_info.get("complexity", 50))}
strength: 1.0
access_count: 0
---

# 代码变更记忆

## 变更摘要

**变更时间**: {now.strftime('%Y-%m-%d %H:%M:%S')}
**变更原因**: {change_info.get("reason", "Manual analysis")}
**变更复杂度**: {change_info.get("complexity", 0)}/100

## 变更文件

| 文件 | 增加行 | 删除行 |
|------|--------|--------|
"""

    for f in changed_files:
        memory_content += f"| `{f['file']}` | +{f['stats'].get('additions', 0)} | -{f['stats'].get('deletions', 0)} |\n"

    memory_content += f"""
## Diff内容

```diff
{diff_content[:5000]}
```
{"...(truncated)" if len(diff_content) > 5000 else ""}

## 影响范围

{change_info.get("impact", "Analyzing...")}

## 关联历史

{"Parent: " + parent_id if parent_id else "Initial change"}
"""

    return {
        "id": memory_id,
        "content": memory_content,
        "files": [f["file"] for f in changed_files],
        "parent": parent_id
    }


def generate_diff_summary(diff_content, changed_files):
    """生成变更摘要"""
    summaries = []

    # 分析变更类型
    if "new file mode" in diff_content:
        summaries.append("新增文件")
    if "delete mode" in diff_content:
        summaries.append("删除文件")

    # 统计
    added = diff_content.count("\n+") - diff_content.count("\n+++")
    removed = diff_content.count("\n-") - diff_content.count("\n---")
    summaries.append(f"+{added}/-{removed} 行")

    # 文件类型
    file_types = set()
    for f in changed_files:
        ext = Path(f["file"]).suffix
        if ext:
            file_types.add(ext)

    if file_types:
        summaries.append(f"类型: {', '.join(sorted(file_types))}")

    return ", ".join(summaries) if summaries else "Code modified"


def install_git_hook(repo_path, hook_type="post-commit"):
    """安装Git Hook"""
    hooks_dir = Path(repo_path) / ".git" / "hooks"
    hooks_dir.mkdir(exist_ok=True)

    hook_path = hooks_dir / hook_type
    script_content = f"""#!/bin/bash
# Auto Memory Hook - {hook_type}
# Generated by memory-skills

SCRIPT_DIR="{script_dir}"
cd "$(git rev-parse --show-toplevel)"
python "$SCRIPT_DIR/auto_memory.py" --hook {hook_type} --quiet
"""

    try:
        with open(hook_path, 'w', encoding='utf-8') as f:
            f.write(script_content)
        os.chmod(hook_path, 0o755)
        return True, f"Installed {hook_type} hook"
    except Exception as e:
        return False, f"Failed to install hook: {e}"


def main():
    parser = argparse.ArgumentParser(
        description="自动记忆脚本 - 追踪代码变更",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--check", action="store_true", help="检查变更并决策是否记忆")
    parser.add_argument("--hook", type=str, help="Git hook类型触发")
    parser.add_argument("--force", action="store_true", help="强制创建记忆（忽略复杂度阈值）")
    parser.add_argument("--quiet", action="store_true", help="静默模式（减少输出）")
    parser.add_argument("--install-hook", action="store_true", help="安装Git Hook")
    parser.add_argument("--cwd", type=str, help="工作目录路径")
    parser.add_argument("--brain-path", type=str, help="brain.md路径")

    args = parser.parse_args()

    # 设置工作目录
    cwd = args.cwd or script_dir.parent

    # 设置brain路径
    if args.brain_path:
        brain_path = resolve_brain_path(explicit_path=args.brain_path)
    else:
        brain_path = resolve_brain_path(start_path=cwd)

    # 确保大脑文件和目录结构存在
    load_brain(str(brain_path))

    # 安装Hook
    if args.install_hook:
        success, msg = install_git_hook(cwd)
        print(msg)
        return 0 if success else 1

    # 检查git仓库
    if not is_git_repo(cwd):
        if not args.quiet:
            print("Not a git repository. Skipping auto-memory.")
        return 0

    # 获取diff
    diff_info, err = get_git_diff(cwd)
    if err:
        if not args.quiet:
            print(f"Error: {err}")
        return 1

    # 检查是否有变更
    has_changes = diff_info["staged"] or diff_info["unstaged"]
    if not has_changes:
        if not args.quiet:
            print("No changes detected.")
        return 0

    # 获取详细diff
    detailed_diff = get_detailed_diff(cwd)
    if not detailed_diff:
        if not args.quiet:
            print("No detailed diff available.")
        return 0

    # 分析复杂度
    should_remember, reason, complexity = analyze_change_complexity(detailed_diff)

    # 决策输出
    if not args.quiet:
        print(f"Change analysis:")
        print(f"  - Complexity: {complexity}/100")
        print(f"  - Decision: {reason}")
        print(f"  - Should remember: {should_remember}")

    # 强制模式或超过阈值
    if args.force or should_remember:
        # 创建记忆
        change_info = {
            "reason": reason,
            "complexity": complexity,
            "impact": f"Files changed: {len(extract_changed_files(detailed_diff))}"
        }

        memory = create_diff_memory(brain_path, detailed_diff, change_info)

        # 保存记忆文件（统一写入路径）
        memory_filename = generate_filename(memory_id=memory["id"])
        memory_path = save_memory(
            memory["content"],
            category="coding",
            filename=memory_filename,
            brain_path=str(brain_path),
        )

        # 更新索引（使用统一接口）
        project_name = find_project_root(cwd).name
        metadata = {
            "id": memory['id'],
            "title": f"代码变更: {', '.join(memory['files'][:2])}" + (f" (+{len(memory['files'])-2} more)" if len(memory['files']) > 2 else ""),
            "category": "coding",
            "project": project_name,
            "quality_score": memory.get('quality_score', 50),
            "created_at": datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ'),
        }
        brain_updated = update_brain_index(str(brain_path), metadata, operation="add")
        
        # 更新线索网络
        cue_updated = update_cue_network(
            str(brain_path),
            category="coding",
            project=project_name,
            keywords=memory['files'],
            memory_id=memory['id'],
            operation="add"
        )

        if not brain_updated or not cue_updated:
            if not args.quiet:
                print("Failed to update brain index/cue network for auto memory write.")
                print(f"  memory_file: {memory_path}")
            return 1

        if not args.quiet:
            print(f"\nMemory created: {memory['id']}")
            print(f"  Files: {', '.join(memory['files'][:3])}")
            if len(memory['files']) > 3:
                print(f"  ... and {len(memory['files']) - 3} more")

        return 0
    else:
        if not args.quiet:
            print("Change is trivial. No memory created.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
