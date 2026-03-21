#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
session_memory.py - 类脑记忆系统

4种记忆类型：
1. Working Memory (工作记忆) - 当前任务，高频更新
2. Episodic Memory (情景记忆) - 任务完成记录
3. Semantic Memory (语义记忆) - 长期知识方案
4. Procedural Memory (程序记忆) - 工作流程模式

记忆优先级最高 - 没有记忆，你不知道你是谁
"""

import os
import sys
import re
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

script_dir = Path(__file__).parent


# ============== 记忆类型定义 ==============

MEMORY_TYPES = {
    "working": {
        "name": "工作记忆",
        "lifetime": "session",
        "update_freq": "high",
        "forgetting": "fast",
        "storage": ".memory/working/"
    },
    "episodic": {
        "name": "情景记忆",
        "lifetime": "days",
        "update_freq": "medium",
        "forgetting": "gradual",
        "storage": ".memory/episodic/"
    },
    "semantic": {
        "name": "语义记忆",
        "lifetime": "permanent",
        "update_freq": "low",
        "forgetting": "slow",
        "storage": ".memory/semantic/"
    },
    "procedural": {
        "name": "程序记忆",
        "lifetime": "permanent",
        "update_freq": "rare",
        "forgetting": "minimal",
        "storage": ".memory/procedural/"
    }
}


def get_memory_storage(memory_type: str, base_path: Path = None) -> Path:
    """获取记忆存储路径"""
    if base_path is None:
        base_path = script_dir.parent
    return base_path / MEMORY_TYPES[memory_type]["storage"]


def ensure_memory_dirs(base_path: Path = None):
    """确保所有记忆目录存在"""
    for mem_type in MEMORY_TYPES:
        storage_path = get_memory_storage(mem_type, base_path)
        storage_path.mkdir(parents=True, exist_ok=True)


# ============== 工作记忆操作 ==============

def create_working_memory(task_name: str, task_goal: str, nodes: List[str], base_path: Path = None) -> Dict:
    """创建工作记忆"""
    now = datetime.now()
    memory_id = f"work_{now.strftime('%Y%m%d_%H%M%S')}"

    content = f"""---
id: {memory_id}
type: working_memory
task_name: {task_name}
task_goal: {task_goal}
created_at: {now.isoformat()}
updated_at: {now.isoformat()}
status: in_progress
completed_nodes: []
pending_nodes: {json.dumps(nodes, ensure_ascii=False)}
progress: 0%
---

# 工作记忆: {task_name}

## 任务目标
{task_goal}

## 节点列表
{chr(10).join(f"- [ ] {node}" for node in nodes)}

## 完成记录
（节点完成后追加记录）

## 变更日志
（每次变更自动记录）
"""

    storage = get_memory_storage("working", base_path)
    memory_file = storage / f"{memory_id}.md"

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return {
        "id": memory_id,
        "file": str(memory_file),
        "status": "created"
    }


def update_working_memory(memory_id: str, node_completed: str, result: str, changes: str = "", base_path: Path = None):
    """更新工作记忆 - 节点完成时调用"""
    storage = get_memory_storage("working", base_path)
    memory_file = storage / f"{memory_id}.md"

    if not memory_file.exists():
        return {"status": "error", "message": "Working memory not found"}

    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    now = datetime.now()

    # 更新完成节点
    content = re.sub(
        r'(## 完成记录\n)',
        rf'\1\n### {node_completed} ({now.strftime("%H:%M:%S")})\n{result}\n',
        content
    )

    # 更新变更日志
    if changes:
        content = re.sub(
            r'(## 变更日志\n)',
            rf'\1\n- [{now.strftime("%H:%M:%S")}] {changes}\n',
            content
        )

    # 更新元数据
    content = re.sub(r'updated_at: .*', f'updated_at: {now.isoformat()}', content)

    # 更新进度
    pending_match = re.search(r'pending_nodes: \[(.*?)\]', content)
    if pending_match:
        pending = json.loads(f"[{pending_match.group(1)}]")
        completed_match = re.search(r'completed_nodes: \[(.*?)\]', content)
        completed = json.loads(f"[{completed_match.group(1)}]") if completed_match else []

        total = len(pending) + len(completed)
        progress = int(len(completed) / total * 100) if total > 0 else 0
        content = re.sub(r'progress: \d+%', f'progress: {progress}%', content)

    # 更新任务状态
    if len(completed) == len(pending) + len(completed):
        content = re.sub(r'status: .*', 'status: completed', content)

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return {"status": "success", "memory_id": memory_id}


def append_change(memory_id: str, change_type: str, description: str, file_path: str = "", base_path: Path = None):
    """追加变更记录"""
    storage = get_memory_storage("working", base_path)
    memory_file = storage / f"{memory_id}.md"

    if not memory_file.exists():
        return {"status": "error", "message": "Working memory not found"}

    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    now = datetime.now()
    change_entry = f"\n### {change_type} - {now.strftime('%H:%M:%S')}\n{description}\n"
    if file_path:
        change_entry = f"\n### {change_type} - {now.strftime('%H:%M:%S')} [{file_path}]\n{description}\n"

    content = re.sub(
        r'(## 变更日志\n)',
        rf'\1{change_entry}',
        content
    )

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return {"status": "success"}


# ============== 记忆整合 ==============

def consolidate_to_episodic(working_memory_id: str, base_path: Path = None) -> Dict:
    """整合工作记忆到情景记忆"""
    storage_working = get_memory_storage("working", base_path)
    storage_episodic = get_memory_storage("episodic", base_path)

    work_file = storage_working / f"{working_memory_id}.md"
    if not work_file.exists():
        return {"status": "error", "message": "Working memory not found"}

    with open(work_file, 'r', encoding='utf-8') as f:
        work_content = f.read()

    # 解析工作记忆
    task_match = re.search(r'task_name: (.+)', work_content)
    goal_match = re.search(r'task_goal: (.+)', work_content)

    if not task_match:
        return {"status": "error", "message": "Invalid working memory format"}

    task_name = task_match.group(1).strip()
    task_goal = goal_match.group(1).strip() if goal_match else ""

    now = datetime.now()
    episodic_id = f"epis_{now.strftime('%Y%m%d_%H%M%S')}"

    # 创建情景记忆
    episodic_content = f"""---
id: {episodic_id}
type: episodic_memory
original_task: {task_name}
created_at: {now.isoformat()}
last_accessed: {now.isoformat()}
access_count: 0
importance: 50
strength: 1.0
parent: {working_memory_id}
---

# 情景记忆: {task_name}

## 任务目标
{task_goal}

## 完成内容
（从工作记忆复制的完成记录）
"""

    # 提取完成记录
    completed_section = re.search(r'## 完成记录\n(.*?)(?=##|$)', work_content, re.DOTALL)
    if completed_section:
        episodic_content += completed_section.group(1)

    episodic_file = storage_episodic / f"{episodic_id}.md"
    with open(episodic_file, 'w', encoding='utf-8') as f:
        f.write(episodic_content)

    # 删除工作记忆
    work_file.unlink()

    return {
        "status": "success",
        "episodic_id": episodic_id,
        "file": str(episodic_file)
    }


def consolidate_to_semantic(episodic_memory_id: str, llm_decision: str, base_path: Path = None) -> Dict:
    """将情景记忆整合为语义记忆（长期知识）"""
    storage_episodic = get_memory_storage("episodic", base_path)
    storage_semantic = get_memory_storage("semantic", base_path)

    episodic_file = storage_episodic / f"{episodic_memory_id}.md"
    if not episodic_file.exists():
        return {"status": "error", "message": "Episodic memory not found"}

    with open(episodic_file, 'r', encoding='utf-8') as f:
        episodic_content = f.read()

    # 解析情景记忆
    task_match = re.search(r'original_task: (.+)', episodic_content)

    now = datetime.now()
    semantic_id = f"sem_{now.strftime('%Y%m%d_%H%M%S')}"

    # 创建语义记忆
    semantic_content = f"""---
id: {semantic_id}
type: semantic_memory
topic: {task_match.group(1).strip() if task_match else "Unknown"}
created_at: {now.isoformat()}
last_accessed: {now.isoformat()}
access_count: 0
strength: 1.0
llm_decision: {llm_decision}
parent: {episodic_memory_id}
---

# 语义记忆: {task_match.group(1).strip() if task_match else "Unknown"}

## LLM决策理由
{llm_decision}

## 知识内容
（从情景记忆提取的核心知识）
"""

    semantic_file = storage_semantic / f"{semantic_id}.md"
    with open(semantic_file, 'w', encoding='utf-8') as f:
        f.write(semantic_content)

    return {
        "status": "success",
        "semantic_id": semantic_id
    }


# ============== 遗忘机制 ==============

def should_forget(memory_id: str, memory_type: str, llm_judgment: str = None, base_path: Path = None) -> Dict:
    """
    遗忘决策

    决策因素：
    1. 访问频率
    2. 记忆强度
    3. 时间衰减
    4. LLM判断

    返回:
        (should_forget: bool, reason: str, action: str)
    """
    storage = get_memory_storage(memory_type, base_path)
    memory_file = storage / f"{memory_id}.md"

    if not memory_file.exists():
        return {"should_forget": False, "reason": "Memory not found", "action": "none"}

    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 提取元数据
    strength_match = re.search(r'strength: ([\d.]+)', content)
    access_match = re.search(r'access_count: (\d+)', content)
    created_match = re.search(r'created_at: (.+)', content)

    strength = float(strength_match.group(1)) if strength_match else 1.0
    access_count = int(access_match.group(1)) if access_match else 0

    # 遗忘规则
    reasons = []

    # 1. 强度过低
    if strength < 0.1:
        reasons.append(f"强度过低 ({strength})")

    # 2. 从未被访问且超过30天
    if created_match and access_count == 0:
        created = created_match.group(1).strip()
        try:
            created_date = datetime.fromisoformat(created.replace("Z", "+00:00"))
            days_old = (datetime.now() - created_date).days
            if days_old > 30:
                reasons.append(f"从未访问且超过30天 ({days_old}天)")
        except:
            pass

    # 3. LLM判断
    if llm_judgment and "遗忘" in llm_judgment:
        reasons.append(f"LLM判断: {llm_judgment}")

    should_forget = len(reasons) > 0

    action = "archive" if should_forget else "keep"

    return {
        "should_forget": should_forget,
        "reason": "; ".join(reasons) if reasons else "条件不满足",
        "action": action,
        "current_strength": strength,
        "access_count": access_count
    }


def archive_memory(memory_id: str, memory_type: str, reason: str, base_path: Path = None):
    """归档记忆"""
    storage = get_memory_storage(memory_type, base_path)
    archive_storage = script_dir.parent / ".memory" / "archive"

    memory_file = storage / f"{memory_id}.md"
    if not memory_file.exists():
        return {"status": "error", "message": "Memory not found"}

    archive_storage.mkdir(parents=True, exist_ok=True)
    archive_file = archive_storage / f"{memory_id}.md"

    # 添加遗忘标记
    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    now = datetime.now()
    content = content.replace(
        "---",
        f"---\nforgotten_at: {now.isoformat()}\nforgotten_reason: {reason}",
        1
    )

    with open(archive_file, 'w', encoding='utf-8') as f:
        f.write(content)

    memory_file.unlink()

    return {"status": "success", "archived_to": str(archive_file)}


def update_strength(memory_id: str, memory_type: str, delta: float, base_path: Path = None):
    """更新记忆强度"""
    storage = get_memory_storage(memory_type, base_path)
    memory_file = storage / f"{memory_id}.md"

    if not memory_file.exists():
        return {"status": "error"}

    with open(memory_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # 更新强度
    strength_match = re.search(r'strength: ([\d.]+)', content)
    if strength_match:
        current = float(strength_match.group(1))
        new_strength = max(0, min(1.0, current + delta))
        content = re.sub(r'strength: [\d.]+', f'strength: {new_strength}', content)

    # 更新访问次数
    content = re.sub(r'access_count: (\d+)', lambda m: f'access_count: {int(m.group(1)) + 1}', content)

    with open(memory_file, 'w', encoding='utf-8') as f:
        f.write(content)

    return {"status": "success", "new_strength": new_strength if strength_match else 1.0}


# ============== 检索 ==============

def get_active_working_memory(base_path: Path = None) -> List[Dict]:
    """获取当前活跃的工作记忆"""
    storage = get_memory_storage("working", base_path)
    memories = []

    if not storage.exists():
        return memories

    for f in storage.glob("work_*.md"):
        with open(f, 'r', encoding='utf-8') as file:
            content = file.read()
            task_match = re.search(r'task_name: (.+)', content)
            status_match = re.search(r'status: (.+)', content)
            progress_match = re.search(r'progress: (\d+)%', content)

            memories.append({
                "id": f.stem,
                "task_name": task_match.group(1).strip() if task_match else "Unknown",
                "status": status_match.group(1).strip() if status_match else "unknown",
                "progress": int(progress_match.group(1)) if progress_match else 0
            })

    return memories


def get_recent_memories(memory_type: str = "all", limit: int = 5, base_path: Path = None) -> List[Dict]:
    """获取最近的记忆"""
    results = []

    types_to_search = [memory_type] if memory_type != "all" else MEMORY_TYPES.keys()

    for mem_type in types_to_search:
        storage = get_memory_storage(mem_type, base_path)
        if not storage.exists():
            continue

        for f in sorted(storage.glob(f"{mem_type[:3]}_*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            with open(f, 'r', encoding='utf-8') as file:
                content = file.read()
                topic_match = re.search(r'(task_name|original_task|topic): (.+)', content)
                topic = topic_match.group(2).strip() if topic_match else f.stem

                strength_match = re.search(r'strength: ([\d.]+)', content)
                strength = float(strength_match.group(1)) if strength_match else 1.0

                results.append({
                    "id": f.stem,
                    "type": mem_type,
                    "topic": topic,
                    "strength": strength,
                    "file": str(f)
                })

    return sorted(results, key=lambda x: x["strength"], reverse=True)[:limit]


# ============== 主函数 ==============

def main():
    parser = argparse.ArgumentParser(description="类脑记忆系统")
    subparsers = parser.add_subparsers(dest="command", help="命令")

    # 创建工作记忆
    create_parser = subparsers.add_parser("create", help="创建工作记忆")
    create_parser.add_argument("--task", required=True, help="任务名称")
    create_parser.add_argument("--goal", required=True, help="任务目标")
    create_parser.add_argument("--nodes", required=True, help="节点列表（逗号分隔）")

    # 更新工作记忆
    update_parser = subparsers.add_parser("update", help="更新工作记忆")
    update_parser.add_argument("--id", required=True, help="记忆ID")
    update_parser.add_argument("--node", required=True, help="完成的节点")
    update_parser.add_argument("--result", required=True, help="节点结果")
    update_parser.add_argument("--changes", default="", help="变更描述")

    # 追加变更
    change_parser = subparsers.add_parser("change", help="追加变更")
    change_parser.add_argument("--id", required=True, help="记忆ID")
    change_parser.add_argument("--type", required=True, help="变更类型")
    change_parser.add_argument("--desc", required=True, help="变更描述")
    change_parser.add_argument("--file", default="", help="相关文件")

    # 整合记忆
    consolidate_parser = subparsers.add_parser("consolidate", help="整合记忆")
    consolidate_parser.add_argument("--id", required=True, help="工作记忆ID")
    consolidate_parser.add_argument("--to", choices=["episodic", "semantic"], default="episodic", help="整合目标")

    # 遗忘检查
    forget_parser = subparsers.add_parser("forget-check", help="遗忘检查")
    forget_parser.add_argument("--id", required=True, help="记忆ID")
    forget_parser.add_argument("--type", required=True, choices=["working", "episodic", "semantic", "procedural"])

    # 获取活跃记忆
    status_parser = subparsers.add_parser("status", help="显示状态")
    status_parser.add_argument("--type", default="all", help="记忆类型")

    args = parser.parse_args()

    base_path = script_dir.parent
    ensure_memory_dirs(base_path)

    if args.command == "create":
        nodes = [n.strip() for n in args.nodes.split(",")]
        result = create_working_memory(args.task, args.goal, nodes, base_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "update":
        result = update_working_memory(args.id, args.node, args.result, args.changes, base_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "change":
        result = append_change(args.id, args.type, args.desc, args.file, base_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "consolidate":
        if args.to == "episodic":
            result = consolidate_to_episodic(args.id, base_path)
        else:
            result = consolidate_to_semantic(args.id, "LLM decision", base_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "forget-check":
        result = should_forget(args.id, args.type, base_path=base_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif args.command == "status":
        if args.type == "all":
            working = get_active_working_memory(base_path)
            print(f"活跃工作记忆: {len(working)}")
            for w in working:
                print(f"  - {w['task_name']} ({w['progress']}%)")
        else:
            recent = get_recent_memories(args.type, base_path=base_path)
            print(f"最近的{args.type}记忆: {len(recent)}")
            for r in recent:
                print(f"  - {r['topic']} (强度:{r['strength']:.2f})")

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
