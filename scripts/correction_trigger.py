#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
correction_trigger.py - 用户纠正行为自动检测和记忆处理

功能：
1. 自动识别用户对AI回答的纠正行为
2. 提取纠正内容的结构化信息
3. 自动写入纠错经验库，标记高优先级
4. 支持命令行调用和API调用两种模式
"""

import sys
import argparse
import re
from pathlib import Path

# 添加脚本目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from memory_extensions import update_lessons_learned, _contains_hint
from project_utils import resolve_brain_path, simple_keyword_extraction, generate_memory_id


# 纠正行为识别关键词
CORRECTION_HINTS = [
    # 中文基础纠正表达
    "不对", "你错了", "错了", "错误", "不正确", "不是这样", "不对吧", "搞错了",
    "应该是", "应当是", "要这么做", "正确的是", "不对哦", "纠正一下", "修正一下", "更正",
    # 中文扩展表达
    "不对啊", "你搞错了", "不是这么回事", "不对的", "错的", "不正确哦", "你说反了",
    "反过来了", "不对不对", "弄错了", "搞错了吧", "不是吧", "不对呀", "更正一下",
    "改一下", "应该是这样", "正确做法是", "不对哦亲", "你说错了", "你理解错了",
    "理解错了", "想错了", "思路错了", "不对哒", "不是的", "不对哟", "这不对啊",
    "你这不对", "错了错了", "什么啊不对", "不对哦", "完全不对", "根本不对",
    "你记错了", "记混了", "搞混了", "搞反了", "反了", "不是这个意思",
    # 英文纠正表达
    "wrong", "incorrect", "not right", "you're wrong", "mistake", "error",
    "correction", "fix", "should be", "it should be", "this is wrong",
    "you got it wrong", "this is not correct", "that's wrong", "you misunderstood",
    "wrong answer", "incorrect response", "fix this", "it's not like that",
    "no, that's not right", "actually it's", "the correct way is", "that's not correct"
]

# 纠正要点提取模式
CORRECTION_PATTERNS = [
    # 基础模式
    r"(?:不对|错了|错误).*?应该是(.+?)(?:。|！|\n|$)",
    r"(?:应该是|应当是|正确的是)(.+?)(?:。|！|\n|$)",
    r"(?:不是这样|不对).*?实际是(.+?)(?:。|！|\n|$)",
    r"(?:纠正|更正|修正).*?正确的做法是(.+?)(?:。|！|\n|$)",
    r"你(?:之前|刚才)?说的不对.*?正确的是(.+?)(?:。|！|\n|$)",
    # 扩展模式
    r"(?:你搞错了|弄错了).*?正确的是(.+?)(?:。|！|\n|$)",
    r"(?:搞反了|反过来了).*?应该是(.+?)(?:。|！|\n|$)",
    r"(?:不对啊|不对呀|不对哦).*?其实是(.+?)(?:。|！|\n|$)",
    r"实际上是(.+?)(?:。|！|\n|$)",
    r"正确的做法是(.+?)(?:。|！|\n|$)",
    r"应该改成(.+?)(?:。|！|\n|$)",
    r"不对，(.+?)(?:。|！|\n|$)",
    r"错了，(.+?)(?:。|！|\n|$)",
    r"不是，(.+?)(?:。|！|\n|$)",
    r"(?:你说反了|搞混了|记混了).*?应该是(.+?)(?:。|！|\n|$)",
    r"(?:完全不对|根本不对).*?正确的是(.+?)(?:。|！|\n|$)",
]


def is_correction_behavior(text: str) -> bool:
    """判断是否是用户纠正行为"""
    if not text:
        return False
    return _contains_hint(text, CORRECTION_HINTS)


def extract_correction_info(
    user_input: str, 
    previous_answer: str = "", 
    context: str = ""
) -> dict:
    """
    提取纠正信息的结构化内容
    
    Args:
        user_input: 用户当前输入（纠正内容）
        previous_answer: AI之前的错误回答
        context: 上下文场景
        
    Returns:
        dict: 结构化纠正信息
    """
    correction_info = {
        "error_scene": context or "general conversation",
        "error_content": previous_answer[:500] if previous_answer else "",
        "correction_points": "",
        "correct_solution": "",
        "keywords": []
    }
    
    # 提取纠正要点和正确方案
    for pattern in CORRECTION_PATTERNS:
        m = re.search(pattern, user_input, flags=re.DOTALL | re.IGNORECASE)
        if m:
            solution = m.group(1).strip()
            if solution:
                correction_info["correct_solution"] = solution
                correction_info["correction_points"] = user_input[:300]
                break
    
    # 如果没匹配到结构化模式，直接提取完整纠正内容
    if not correction_info["correction_points"]:
        correction_info["correction_points"] = user_input[:300]
        if not correction_info["correct_solution"]:
            # 尝试提取用户输入中的核心内容作为正确方案
            cleaned = re.sub(r"^(?:不对|错了|你错了|不是这样)[，。！？]?\s*", "", user_input).strip()
            correction_info["correct_solution"] = cleaned[:200] if cleaned else user_input[:200]
    
    # 提取关键词
    all_text = f"{user_input} {previous_answer} {context}"
    correction_info["keywords"] = simple_keyword_extraction(all_text, max_keywords=6)
    
    # 高优先级标记
    correction_info["quality_score"] = 95
    correction_info["strength"] = 1.5
    
    return correction_info


def process_correction(
    user_input: str,
    previous_answer: str = "",
    context: str = "",
    brain_path: str | Path | None = None,
    dry_run: bool = False
) -> dict:
    """
    处理用户纠正行为，自动记录到经验库
    
    Args:
        user_input: 用户纠正输入
        previous_answer: AI之前的错误回答
        context: 上下文场景
        brain_path: 大脑文件路径，自动检测如果不提供
        dry_run: 只返回结果不写入文件
        
    Returns:
        dict: 处理结果
    """
    if not is_correction_behavior(user_input):
        return {"success": False, "reason": "not a correction behavior"}
    
    # 解析脑路径
    if brain_path is None:
        brain_path = resolve_brain_path()
    else:
        brain_path = Path(brain_path)
    
    if not brain_path.exists():
        return {"success": False, "reason": f"brain file not found at {brain_path}"}
    
    # 提取纠正信息
    correction_info = extract_correction_info(user_input, previous_answer, context)
    
    if dry_run:
        return {
            "success": True,
            "dry_run": True,
            "correction_info": correction_info,
            "brain_path": str(brain_path)
        }
    
    # 生成记忆ID
    memory_id = generate_memory_id()
    
    # 写入经验库
    title = f"Correction: {correction_info['error_scene'][:30]}"
    content = f"""
## Error Scene
{correction_info['error_scene']}

## Error Content
{correction_info['error_content']}

## Correction Points
{correction_info['correction_points']}

## Correct Solution
{correction_info['correct_solution']}
    """.strip()
    
    result = update_lessons_learned(
        brain_path=str(brain_path),
        memory_id=memory_id,
        title=title,
        content=content,
        keywords=correction_info["keywords"],
        correction_info=correction_info
    )
    
    return {
        "success": True,
        **result,
        "correction_info": correction_info,
        "memory_id": memory_id,
        "brain_path": str(brain_path)
    }


def main():
    parser = argparse.ArgumentParser(description="用户纠正行为记忆处理器")
    parser.add_argument(
        "input",
        type=str,
        nargs="?",
        help="用户纠正输入文本，不提供则从stdin读取"
    )
    parser.add_argument(
        "--previous-answer",
        type=str,
        default="",
        help="AI之前的错误回答内容"
    )
    parser.add_argument(
        "--context",
        type=str,
        default="",
        help="上下文场景描述"
    )
    parser.add_argument(
        "--brain-path",
        type=str,
        help="指定brain.md文件路径，自动检测如果不提供"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="测试模式，只分析不写入文件"
    )
    
    args = parser.parse_args()
    
    # 读取输入
    user_input = args.input
    if not user_input:
        if not sys.stdin.isatty():
            user_input = sys.stdin.read().strip()
        else:
            print("错误：请提供用户纠正输入文本", file=sys.stderr)
            parser.print_help()
            return 1
    
    # 处理纠正
    result = process_correction(
        user_input=user_input,
        previous_answer=args.previous_answer,
        context=args.context,
        brain_path=args.brain_path,
        dry_run=args.dry_run
    )
    
    if not result["success"]:
        print(f"处理失败：{result.get('reason', 'unknown error')}", file=sys.stderr)
        return 1
    
    if args.dry_run:
        print("测试模式，检测到纠正行为，提取信息如下：")
        corr_info = result["correction_info"]
        print(f"错误场景：{corr_info['error_scene']}")
        print(f"纠正要点：{corr_info['correction_points']}")
        print(f"正确方案：{corr_info['correct_solution']}")
        print(f"关键词：{', '.join(corr_info['keywords'])}")
        print(f"质量分数：{corr_info['quality_score']}")
        print(f"记忆强度：{corr_info['strength']}")
        print(f"脑路径：{result['brain_path']}")
    else:
        print(f"纠正记忆已成功记录：")
        print(f"记忆ID：{result['memory_id']}")
        print(f"纠正ID：{result.get('correction_id')}")
        print(f"写入路径：{result['path']}")
        print(f"添加经验条目：{result['items_added']} 条")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
