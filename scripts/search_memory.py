#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
search_memory.py - 记忆检索辅助工具

新架构: LLM主导 + Python辅助
- Python负责: 文件读取、候选记忆提取、数据准备
- LLM负责: 相关性判断、语义理解、结果排序

工作模式:
1. --prepare: 准备检索上下文,返回候选记忆给LLM
2. --apply: 应用LLM的检索结果
3. --legacy: 旧版硬编码评分(向后兼容)
"""

import os
import sys
import re
import json
import argparse
from pathlib import Path
from datetime import datetime

# 导入load_brain模块
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from load_brain import load_brain
from project_utils import resolve_brain_path, get_memory_dir


def read_file_safely(file_path):
    """
    安全读取文件(支持多种编码)
    
    Args:
        file_path: 文件路径
    
    Returns:
        str: 文件内容
    """
    if not os.path.exists(file_path):
        return None
    
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin1']
    
    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    
    return None


def _strip_quotes(value: str) -> str:
    if not value:
        return value
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def extract_memory_metadata(memory_path):
    """
    从记忆文件提取元数据
    
    Args:
        memory_path: 记忆文件路径
    
    Returns:
        dict: 元数据
    """
    content = read_file_safely(memory_path)
    
    if not content:
        return None
    
    metadata = {
        'path': memory_path,
        'id': '',
        'title': '',
        'category': '',
        'project': '',
        'keywords': [],
        'quality_score': 50,
        'created_at': '',
        'strength': 1.0
    }
    
    # 提取YAML前置元数据
    yaml_match = re.match(r'^---\s*\n(.*?)\n---', content, re.DOTALL)
    if yaml_match:
        yaml_content = yaml_match.group(1)
        
        # 提取各个字段
        id_match = re.search(r'^id:\s*(.+)$', yaml_content, re.MULTILINE)
        if id_match:
            metadata['id'] = id_match.group(1).strip()
        
        title_match = re.search(r'^title:\s*(.+)$', yaml_content, re.MULTILINE)
        if title_match:
            metadata['title'] = _strip_quotes(title_match.group(1).strip())
        
        category_match = re.search(r'^category:\s*(.+)$', yaml_content, re.MULTILINE)
        if category_match:
            metadata['category'] = category_match.group(1).strip()
        
        project_match = re.search(r'^project:\s*(.+)$', yaml_content, re.MULTILINE)
        if project_match:
            metadata['project'] = _strip_quotes(project_match.group(1).strip())
        
        keywords_match = re.search(r'keywords:\s*\[(.*?)\]', yaml_content)
        if keywords_match:
            kw_str = keywords_match.group(1)
            metadata['keywords'] = [kw.strip() for kw in kw_str.split(',')]
        
        quality_match = re.search(r'^quality_score:\s*(\d+)', yaml_content, re.MULTILINE)
        if quality_match:
            metadata['quality_score'] = int(quality_match.group(1))
        
        created_match = re.search(r'^created_at:\s*(.+)$', yaml_content, re.MULTILINE)
        if created_match:
            metadata['created_at'] = created_match.group(1).strip()
        
        strength_match = re.search(r'^strength:\s*([\d.]+)', yaml_content, re.MULTILINE)
        if strength_match:
            metadata['strength'] = float(strength_match.group(1))
    
    # 如果没有标题,从第一个标题提取
    if not metadata['title']:
        title_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
        if title_match:
            metadata['title'] = title_match.group(1).strip()
    
    return metadata


def build_id_cache(memory_dir: Path):
    """
    Build a map of memory_id -> file path by scanning a category directory.
    """
    id_map = {}
    if not memory_dir.exists():
        return id_map
    for f in memory_dir.glob("*.md"):
        meta = extract_memory_metadata(str(f))
        if meta and meta.get("id"):
            id_map[meta["id"]] = str(f)
    return id_map


def resolve_memory_path(memory_id: str, category: str, brain_path: Path, id_cache: dict):
    memory_dir = get_memory_dir(brain_path) / category
    candidates = [memory_dir / f"{memory_id}.md"]
    if memory_id.startswith("mem_"):
        candidates.append(memory_dir / f"{memory_id[4:]}.md")
    for p in candidates:
        if p.exists():
            return str(p)

    # Fallback: scan category directory by YAML id
    if category not in id_cache:
        id_cache[category] = build_id_cache(memory_dir)
    return id_cache[category].get(memory_id)


def get_memory_summary(memory_path, max_length=200):
    """
    获取记忆摘要
    
    Args:
        memory_path: 记忆文件路径
        max_length: 最大长度
    
    Returns:
        str: 摘要
    """
    content = read_file_safely(memory_path)
    
    if not content:
        return ''
    
    # 移除YAML前置元数据
    content = re.sub(r'^---\s*\n.*?\n---\s*\n', '', content, flags=re.DOTALL)
    
    # 移除标题
    content = re.sub(r'^#+\s+.*?\n', '', content, flags=re.MULTILINE)
    
    # 移除代码块
    content = re.sub(r'```[\s\S]*?```', '', content)
    
    # 获取摘要
    summary = content.strip()[:max_length]
    
    return summary + '...' if len(summary) == max_length else summary


def scan_memories_from_disk(brain_path: Path, category: str | None = None):
    """
    Fallback: scan memory files directly when brain index is empty or out-of-sync.
    """
    memory_root = get_memory_dir(brain_path)
    if not memory_root.exists():
        return []

    categories = []
    if category:
        categories = [category]
    else:
        categories = [p.name for p in memory_root.iterdir() if p.is_dir()]

    scanned = []
    for cat in categories:
        cat_dir = memory_root / cat
        if not cat_dir.exists():
            continue
        for f in cat_dir.glob("*.md"):
            meta = extract_memory_metadata(str(f))
            if not meta:
                continue
            if not meta.get("category"):
                meta["category"] = cat
            meta["path"] = str(f)
            scanned.append(meta)

    return scanned


def collect_candidate_memories(brain_data, brain_path, category=None, project=None, keywords=None, max_candidates=20):
    """
    收集候选记忆
    
    Args:
        brain_data: 大脑数据
        category: 类别筛选
        project: 项目筛选
        keywords: 关键词列表
        max_candidates: 最大候选数
    
    Returns:
        list: 候选记忆列表
    """
    memories = brain_data.get('memories', [])
    candidates = []

    # Fallback: if brain index is empty, scan disk
    if not memories:
        disk_memories = scan_memories_from_disk(brain_path, category=category)
        for metadata in disk_memories:
            # 初步筛选(基于类别和项目)
            if category and metadata.get('category') != category:
                continue
            if project and metadata.get('project') != project:
                continue

            metadata['summary'] = get_memory_summary(metadata['path'])

            preliminary_score = 0
            if category and metadata.get('category') == category:
                preliminary_score += 40
            if project and metadata.get('project') == project:
                preliminary_score += 30
            if keywords:
                memory_keywords = set(metadata.get('keywords', []))
                target_keywords = set(keywords)
                matched = memory_keywords & target_keywords
                preliminary_score += min(20, len(matched) * 5)

            metadata['preliminary_score'] = preliminary_score
            candidates.append(metadata)

        candidates.sort(key=lambda m: m.get('preliminary_score', 0), reverse=True)
        return candidates[:max_candidates]

    id_cache = {}
    
    for memory in memories:
        memory_id = memory.get('id', '')
        memory_category = memory.get('category', 'other')
        
        memory_path = resolve_memory_path(memory_id, memory_category, brain_path, id_cache)
        if not memory_path:
            continue
        
        # 提取元数据
        metadata = extract_memory_metadata(str(memory_path))
        
        if not metadata:
            continue
        
        # 初步筛选(基于类别和项目)
        if category and metadata['category'] != category:
            continue
        
        if project and metadata['project'] != project:
            continue
        
        # 获取摘要
        metadata['summary'] = get_memory_summary(str(memory_path))
        
        # 计算初步匹配度(用于排序候选)
        preliminary_score = 0
        
        if category and metadata['category'] == category:
            preliminary_score += 40
        
        if project and metadata['project'] == project:
            preliminary_score += 30
        
        if keywords:
            memory_keywords = set(metadata['keywords'])
            target_keywords = set(keywords)
            matched = memory_keywords & target_keywords
            preliminary_score += min(20, len(matched) * 5)
        
        metadata['preliminary_score'] = preliminary_score
        
        candidates.append(metadata)
    
    # 按初步匹配度排序
    candidates.sort(key=lambda m: m['preliminary_score'], reverse=True)
    
    # 返回前N个候选
    return candidates[:max_candidates]


def prepare_search_context(brain_path, category=None, project=None, keywords=None, query_intent=None):
    """
    准备检索上下文
    
    Args:
        brain_path: brain.md路径
        category: 类别
        project: 项目
        keywords: 关键词
        query_intent: 查询意图
    
    Returns:
        dict: 检索上下文
    """
    # 加载大脑
    brain_data = load_brain(str(brain_path))
    
    # 收集候选记忆
    candidates = collect_candidate_memories(brain_data, brain_path, category, project, keywords)
    
    if not candidates:
        return {
            'status': 'no_candidates',
            'message': '没有找到候选记忆',
            'query': {
                'category': category,
                'project': project,
                'keywords': keywords
            }
        }
    
    # 加载提示词模板
    prompt_path = script_dir.parent / 'prompts' / 'search_prompt.md'
    prompt_template = None
    if prompt_path.exists():
        prompt_template = read_file_safely(str(prompt_path))
    
    # 构建候选记忆文本
    candidates_text = []
    for i, candidate in enumerate(candidates, 1):
        candidate_text = f"""
### 候选记忆 {i}

**ID**: {candidate['id']}
**标题**: {candidate['title']}
**类别**: {candidate['category']}
**项目**: {candidate['project']}
**关键词**: {', '.join(candidate['keywords']) if candidate['keywords'] else '无'}
**质量评分**: {candidate['quality_score']}
**创建时间**: {candidate['created_at']}
**摘要**: {candidate['summary']}
"""
        candidates_text.append(candidate_text)
    
    candidates_text_str = '\n'.join(candidates_text)
    
    return {
        'status': 'ready_for_llm',
        'query': {
            'category': category or '未指定',
            'project': project or '未指定',
            'keywords': keywords or [],
            'query_intent': query_intent or '未指定'
        },
        'candidates': candidates,
        'candidates_text': candidates_text_str,
        'prompt_template': prompt_template,
        'stats': {
            'total_candidates': len(candidates),
            'category_filtered': category is not None,
            'project_filtered': project is not None,
            'keyword_count': len(keywords) if keywords else 0
        }
    }


def prepare_search_prompt(context):
    """
    准备完整的检索提示词
    
    Args:
        context: prepare_search_context的返回结果
    
    Returns:
        str: 完整的提示词
    """
    if context['status'] != 'ready_for_llm':
        return None
    
    template = context['prompt_template']
    if not template:
        # 使用默认提示词
        template = """# 记忆检索任务

## 检索查询

**类别**: {category}
**项目**: {project}
**关键词**: {keywords}
**查询意图**: {query_intent}

## 候选记忆列表

{candidate_memories}

## 输出格式

返回JSON格式的结果,包含最相关的5条记忆。"""
    
    # 填充模板
    prompt = template.format(
        category=context['query']['category'],
        project=context['query']['project'],
        keywords=', '.join(context['query']['keywords']) if context['query']['keywords'] else '无',
        query_intent=context['query']['query_intent'],
        candidate_memories=context['candidates_text']
    )
    
    return prompt


def apply_search_results(results_json):
    """
    应用LLM的检索结果
    
    Args:
        results_json: LLM返回的JSON结果
    
    Returns:
        dict: 应用结果
    """
    try:
        results = json.loads(results_json)
        
        # 验证结果格式
        if 'results' not in results:
            return {
                'status': 'error',
                'error': 'INVALID_FORMAT',
                'message': '结果缺少results字段'
            }
        
        return {
            'status': 'success',
            'results': results['results'],
            'total_count': len(results['results'])
        }
    
    except json.JSONDecodeError as e:
        return {
            'status': 'error',
            'error': 'JSON_PARSE_ERROR',
            'message': str(e)
        }


def legacy_search(brain_data, brain_path, category=None, project=None, keywords=None):
    """
    旧版硬编码评分检索(向后兼容)
    
    Args:
        brain_data: 大脑数据
        category: 类别
        project: 项目
        keywords: 关键词列表
    
    Returns:
        list: 检索结果
    """
    memories = brain_data.get('memories', [])
    results = []
    
    id_cache = {}
    
    for memory in memories:
        memory_id = memory.get('id', '')
        memory_category = memory.get('category', 'other')
        
        memory_path = resolve_memory_path(memory_id, memory_category, brain_path, id_cache)
        if not memory_path:
            continue
        
        # 提取元数据
        metadata = extract_memory_metadata(str(memory_path))
        
        if not metadata:
            continue
        
        # 计算匹配度
        match_score = 0
        match_details = {
            'category_match': 0,
            'project_match': 0,
            'keyword_match': 0,
            'semantic_match': 0
        }
        
        # 类别匹配
        if category and metadata['category'] == category:
            match_score += 40
            match_details['category_match'] = 40
        
        # 项目匹配
        if project and metadata['project'] == project:
            match_score += 30
            match_details['project_match'] = 30
        
        # 关键词匹配
        if keywords:
            memory_keywords = set(metadata['keywords'])
            target_keywords = set(keywords)
            matched = memory_keywords & target_keywords
            keyword_score = min(20, len(matched) * 5)
            match_score += keyword_score
            match_details['keyword_match'] = keyword_score
        
        # 只保留有匹配的记忆
        if match_score > 0:
            metadata['match_score'] = match_score
            metadata['match_details'] = match_details
            metadata['summary'] = get_memory_summary(str(memory_path))
            results.append(metadata)
    
    # 按匹配度排序
    results.sort(key=lambda m: m['match_score'], reverse=True)
    
    # 返回最多5条
    return results[:5]


def main():
    """
    主函数: 命令行入口
    """
    parser = argparse.ArgumentParser(
        description='记忆检索辅助工具 (LLM主导模式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作模式:
  --prepare        准备检索上下文,输出JSON给LLM处理
  --apply          从stdin读取LLM检索结果并应用
  --legacy         使用旧版硬编码评分(向后兼容)

示例:
  # 新模式: LLM主导
  python search_memory.py --category coding --keywords "压缩,算法" --prepare
  # (LLM处理输出)
  
  # 旧模式: 硬编码评分
  python search_memory.py --category coding --keywords "压缩,算法" --legacy
        """
    )
    
    parser.add_argument('--category', type=str, help='类别筛选')
    parser.add_argument('--project', type=str, help='项目筛选')
    parser.add_argument('--keywords', type=str, help='关键词(逗号分隔)')
    parser.add_argument('--query-intent', type=str, help='查询意图')
    parser.add_argument('--mode', type=str, choices=['prepare', 'apply', 'legacy'],
                       default='prepare', help='工作模式')
    parser.add_argument('--brain-path', type=str, help='brain.md路径')
    parser.add_argument('--project-root', type=str, help='项目根目录(可选,用于自动定位brain)')
    
    args = parser.parse_args()
    
    # 获取brain.md路径
    if args.brain_path:
        brain_path = resolve_brain_path(explicit_path=args.brain_path)
    else:
        brain_path = resolve_brain_path(start_path=args.project_root or os.getcwd())
    
    # 解析关键词
    keywords = None
    if args.keywords:
        keywords = [kw.strip() for kw in args.keywords.split(',')]
    
    try:
        if args.mode == 'prepare':
            # 准备模式: 收集候选记忆并返回给LLM
            context = prepare_search_context(
                brain_path,
                category=args.category,
                project=args.project,
                keywords=keywords,
                query_intent=args.query_intent
            )
            
            if context['status'] == 'no_candidates':
                print(json.dumps(context, ensure_ascii=False, indent=2))
                sys.exit(0)
            
            # 准备提示词
            prompt = prepare_search_prompt(context)
            
            # 输出JSON
            output = {
                'status': 'ready_for_llm',
                'prompt': prompt,
                'query': context['query'],
                'stats': context['stats'],
                'instructions': {
                    'step1': 'LLM处理上述prompt',
                    'step2': 'LLM输出JSON格式的检索结果',
                    'step3': '使用 --apply 模式应用结果'
                }
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        elif args.mode == 'apply':
            # 应用模式: 从stdin读取LLM的检索结果
            if sys.stdin.isatty():
                print(json.dumps({
                    'status': 'error',
                    'error': 'NO_STDIN',
                    'message': '请通过stdin提供检索结果'
                }, ensure_ascii=False, indent=2))
                sys.exit(1)
            
            results_json = sys.stdin.read()
            result = apply_search_results(results_json)
            
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        elif args.mode == 'legacy':
            # 旧版模式: 硬编码评分
            brain_data = load_brain(str(brain_path))
            
            results = legacy_search(
                brain_data,
                brain_path,
                category=args.category,
                project=args.project,
                keywords=keywords
            )
            
            # 构建输出
            output = {
                'status': 'success',
                'mode': 'legacy',
                'query': {
                    'category': args.category,
                    'project': args.project,
                    'keywords': keywords
                },
                'results': [
                    {
                        'id': m['id'],
                        'title': m['title'],
                        'path': m['path'],
                        'category': m['category'],
                        'project': m['project'],
                        'match_score': m['match_score'],
                        'match_details': m['match_details'],
                        'summary': m['summary'],
                        'quality_score': m['quality_score']
                    }
                    for m in results
                ],
                'total_count': len(results)
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
    
    except Exception as e:
        error_output = {
            'status': 'error',
            'error': {
                'code': 'SEARCH_FAILED',
                'message': str(e)
            }
        }
        print(json.dumps(error_output, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == '__main__':
    main()
