#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
realtime_tracker.py - 实时变更追踪器

功能：
- 监控指定目录的文件变更
- 生成Diff记录
- 自动追加到工作记忆

使用方式：
python realtime_tracker.py --watch --dir ./src
python realtime_tracker.py --check --since "10 minutes ago"
"""

import os
import sys
import re
import json
import argparse
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict

script_dir = Path(__file__).parent


def run_command(cmd, cwd=None):
    """执行shell命令并返回输出"""
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True,
            text=True, cwd=cwd, timeout=30
        )
        return result.stdout.strip(), result.stderr.strip(), result.returncode
    except Exception as e:
        return "", str(e), 1


def get_changed_files(since: str = None, cwd: str = None) -> List[Dict]:
    """获取变更文件列表"""
    if since:
        cmd = f'git diff --name-only --since="{since}"'
    else:
        cmd = "git diff --name-only --cached"
        stdout, _, code = run_command(cmd, cwd)
        if code == 0 and stdout:
            return [{"file": f, "status": "staged"} for f in stdout.split("\n") if f]

        cmd = "git diff --name-only"
        stdout, _, code = run_command(cmd, cwd)
        if code == 0 and stdout:
            return [{"file": f, "status": "unstaged"} for f in stdout.split("\n") if f]

    stdout, _, code = run_command(cmd, cwd)
    if code == 0 and stdout:
        return [{"file": f, "status": "committed"} for f in stdout.split("\n") if f]

    return []


def get_file_diff(file_path: str, cwd: str = None) -> str:
    """获取文件diff"""
    cmd = f'git diff HEAD -- "{file_path}"'
    stdout, _, code = run_command(cmd, cwd)
    return stdout if code == 0 else ""


def get_recent_commits(since: str = "1 hour ago", cwd: str = None) -> List[Dict]:
    """获取最近的提交"""
    cmd = f'git log --since="{since}" --oneline --format="%H|%s|%an|%ad" --date=iso'
    stdout, _, code = run_command(cmd, cwd)

    if code != 0 or not stdout:
        return []

    commits = []
    for line in stdout.split("\n"):
        parts = line.split("|")
        if len(parts) >= 4:
            commits.append({
                "hash": parts[0],
                "message": parts[1],
                "author": parts[2],
                "date": parts[3]
            })

    return commits


def analyze_changes(files: List[Dict], cwd: str = None) -> Dict:
    """分析变更"""
    total_additions = 0
    total_deletions = 0
    file_types = {}

    for f in files:
        diff = get_file_diff(f["file"], cwd)
        if not diff:
            continue

        # 统计行数
        additions = diff.count("\n+") - diff.count("\n+++")
        deletions = diff.count("\n-") - diff.count("\n---")
        total_additions += additions
        total_deletions += deletions

        # 统计文件类型
        ext = Path(f["file"]).suffix
        if ext:
            file_types[ext] = file_types.get(ext, 0) + 1

    return {
        "files_count": len(files),
        "total_additions": total_additions,
        "total_deletions": total_deletions,
        "file_types": file_types,
        "summary": f"+{total_additions}/-{total_deletions} 行"
    }


def generate_change_record(files: List[Dict], analysis: Dict, cwd: str = None) -> str:
    """生成变更记录"""
    now = datetime.now()

    record = f"""## 变更记录 - {now.strftime('%Y-%m-%d %H:%M:%S')}

### 变更统计
- 文件数: {analysis['files_count']}
- 增加行: +{analysis['total_additions']}
- 删除行: -{analysis['total_deletions']}
- 文件类型: {', '.join(f'{k}({v})' for k, v in analysis['file_types'].items())}

### 变更文件
"""

    for f in files:
        record += f"- [{f['status']}] `{f['file']}`\n"

    return record


def append_to_working_memory(record: str, base_path: Path = None) -> bool:
    """追加到当前工作记忆"""
    if base_path is None:
        base_path = script_dir.parent

    storage = base_path / ".memory" / "working"

    if not storage.exists():
        return False

    # 查找当前活跃的工作记忆
    working_files = list(storage.glob("work_*.md"))
    if not working_files:
        return False

    # 获取最新的工作记忆
    latest = max(working_files, key=lambda x: x.stat().st_mtime)

    with open(latest, 'r', encoding='utf-8') as f:
        content = f.read()

    # 追加变更记录
    content = re.sub(
        r'(## 变更日志\n)',
        rf'\1{record}\n',
        content
    )

    # 更新时间
    content = re.sub(
        r'updated_at: .*',
        f'updated_at: {datetime.now().isoformat()}',
        content
    )

    with open(latest, 'w', encoding='utf-8') as f:
        f.write(content)

    return True


def create_change_memory(changes: List[Dict], analysis: Dict, cwd: str = None, base_path: Path = None) -> Dict:
    """创建变更记忆"""
    if base_path is None:
        base_path = script_dir.parent

    now = datetime.now()
    memory_id = f"change_{now.strftime('%Y%m%d_%H%M%S')}"

    content = f"""---
id: {memory_id}
type: change_record
created_at: {now.isoformat()}
files_count: {analysis['files_count']}
additions: {analysis['total_additions']}
deletions: {analysis['total_deletions']}
---

# 变更记录 - {now.strftime('%Y-%m-%d %H:%M')}

## 变更统计
| 指标 | 数值 |
|------|------|
| 文件数 | {analysis['files_count']} |
| 增加行 | +{analysis['total_additions']} |
| 删除行 | -{analysis['total_deletions']} |

## 变更文件
| 状态 | 文件 |
|------|------|
"""

    for f in changes:
        content += f"| {f['status']} | `{f['file']}` |\n"

    content += "\n## 详细Diff\n\n"
    for f in changes[:5]:  # 限制前5个文件
        diff = get_file_diff(f["file"], cwd)
        if diff:
            content += f"\n### {f['file']}\n```diff\n{diff[:2000]}\n```\n"

    storage = base_path / ".memory" / "episodic"
    storage.mkdir(parents=True, exist_ok=True)

    memory_file = storage / f"{memory_id}.md"
    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return {
        "id": memory_id,
        "file": str(memory_file),
        "files_count": analysis['files_count']
    }


def main():
    parser = argparse.ArgumentParser(description="实时变更追踪器")
    parser.add_argument("--watch", action="store_true", help="监控模式")
    parser.add_argument("--check", action="store_true", help="检查变更")
    parser.add_argument("--since", default="1 hour ago", help="检查时间范围")
    parser.add_argument("--dir", default=".", help="监控目录")
    parser.add_argument("--create-memory", action="store_true", help="创建变更记忆")

    args = parser.parse_args()

    cwd = os.getcwd()

    if args.check or args.create_memory:
        # 检查变更
        files = get_changed_files(args.since, cwd)
        if not files:
            print("No changes detected")
            return 0

        analysis = analyze_changes(files, cwd)
        print(f"Changes detected: {analysis['files_count']} files")
        print(f"Summary: {analysis['summary']}")

        if args.create_memory:
            memory = create_change_memory(files, analysis, cwd)
            print(f"Change memory created: {memory['id']}")
            return 0

        # 显示变更文件
        for f in files:
            print(f"  [{f['status']}] {f['file']}")

        return 0

    if args.watch:
        print(f"Watching {args.dir} for changes...")
        print("(Press Ctrl+C to stop)")

        # 简单监控 - 检查git变更
        import time
        last_check = None

        while True:
            files = get_changed_files("1 minute ago", cwd)
            if files and files != last_check:
                analysis = analyze_changes(files, cwd)
                print(f"\n[{datetime.now().strftime('%H:%M:%S')}] Changes detected:")
                print(f"  {analysis['summary']}")

                # 追加到工作记忆
                record = generate_change_record(files, analysis, cwd)
                if append_to_working_memory(record):
                    print("  → Appended to working memory")

                last_check = files

            time.sleep(30)  # 每30秒检查一次

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
