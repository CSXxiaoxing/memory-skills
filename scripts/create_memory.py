#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
create_memory.py - 记忆创建辅助工具

新架构: LLM主导 + Python辅助
- Python负责: 文件操作、索引更新、数据准备
- LLM负责: 价值评估、关键词提取、内容优化

工作模式:
1. --prepare: 准备创建上下文,返回给LLM评估
2. --create: 创建记忆(使用LLM提供的元数据)
3. --evaluate: 准备价值评估上下文
4. --extract-keywords: 准备关键词提取上下文
"""

import os
import sys
import re
import json
import argparse
from collections import Counter
from datetime import datetime
from pathlib import Path

# 导入load_brain模块
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from load_brain import load_brain
from project_utils import resolve_brain_path, find_project_root


DEFAULT_CATEGORIES = ["coding", "design", "config", "docs", "debug", "other"]
CATEGORY_BRAIN_DOMINANT = {
    "coding": "left",
    "config": "left",
    "debug": "left",
    "design": "right",
    "docs": "right",
    "other": "both",
}


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


def generate_memory_id():
    """
    生成唯一记忆ID
    
    格式: mem_YYYYMMDD_HHMMSS_序号
    
    Returns:
        str: 记忆ID
    """
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    microsecond = datetime.now().microsecond
    sequence = str(microsecond // 1000).zfill(3)
    
    return f"mem_{timestamp}_{sequence}"


def generate_filename(title=None, memory_id=None):
    """
    生成文件名
    
    格式: YYYYMMDD_HHMMSS_简短标识.md
    
    Args:
        title: 标题(用于提取标识)
    
    Returns:
        str: 文件名
    """
    if memory_id:
        return f"{memory_id}.md"

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    
    if title:
        identifier = re.sub(r'[^\w\u4e00-\u9fff]', '', title)[:20]
        if not identifier:
            identifier = 'memory'
    else:
        identifier = 'memory'
    
    return f"{timestamp}_{identifier}.md"


def normalize_category(category: str | None) -> str:
    if not category:
        return "other"
    category = category.strip().lower()
    return category if category in DEFAULT_CATEGORIES else "other"


def normalize_keywords(raw_keywords):
    if raw_keywords is None:
        return []
    if isinstance(raw_keywords, list):
        items = raw_keywords
    elif isinstance(raw_keywords, str):
        items = [kw.strip() for kw in raw_keywords.split(",")]
    else:
        items = [str(raw_keywords)]
    # Remove empties, preserve order
    seen = set()
    cleaned = []
    for kw in items:
        kw = kw.strip()
        if not kw or kw in seen:
            continue
        seen.add(kw)
        cleaned.append(kw)
    return cleaned


def infer_title(content: str | None, fallback: str = "未命名记忆") -> str:
    if not content:
        return fallback
    # First markdown H1
    m = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if m:
        return m.group(1).strip()[:100]
    # First non-empty line
    for line in content.splitlines():
        line = line.strip()
        if line:
            return line[:100]
    return fallback


def simple_keyword_extraction(text: str, max_keywords: int = 5) -> list[str]:
    """
    Lightweight keyword extraction without external dependencies.
    """
    if not text:
        return []

    text = re.sub(r"```[\s\S]*?```", " ", text)
    tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_\-+#]{1,}", text)
    tokens = [t.lower() if re.match(r"[A-Za-z]", t) else t for t in tokens]

    stopwords = {
        "the", "and", "with", "for", "from", "this", "that", "these", "those",
        "using", "use", "used", "into", "over", "under", "about", "need",
        "实现", "方案", "模块", "功能", "系统", "处理", "问题", "需求", "需要",
        "通过", "进行", "使用", "内容", "方法", "设计", "相关", "参考", "部分",
    }

    filtered = [t for t in tokens if t not in stopwords and len(t) >= 2]
    if not filtered:
        return []

    counts = Counter(filtered)
    # Prefer higher frequency and longer tokens
    ranked = sorted(counts.items(), key=lambda x: (x[1], len(x[0])), reverse=True)
    return [kw for kw, _ in ranked[:max_keywords]]


def estimate_quality_score(content: str) -> int:
    if not content:
        return 30
    length = len(content)
    has_code = "```" in content
    has_headings = bool(re.search(r"^#{2,}\s+", content, re.MULTILINE))

    score = 50
    if length > 800:
        score += 10
    if length > 1500:
        score += 10
    if has_code:
        score += 10
    if has_headings:
        score += 5
    if length < 200:
        score -= 15

    return max(0, min(100, score))


def create_memory_document(metadata, content):
    """
    创建记忆文档
    
    Args:
        metadata: 元数据字典
        content: 正文内容
    
    Returns:
        str: 完整的Markdown文档
    """
    yaml_lines = ['---']
    yaml_lines.append(f"id: {metadata.get('id', '')}")
    yaml_lines.append(f"title: {metadata.get('title', '')}")
    yaml_lines.append(f"category: {metadata.get('category', 'other')}")
    yaml_lines.append(f"project: {metadata.get('project', '')}")
    yaml_lines.append(f"brain_dominant: {metadata.get('brain_dominant', 'both')}")
    
    keywords = metadata.get('keywords', [])
    if keywords:
        keywords_str = ', '.join(keywords)
        yaml_lines.append(f"keywords: [{keywords_str}]")
    else:
        yaml_lines.append("keywords: []")
    
    yaml_lines.append(f"quality_score: {metadata.get('quality_score', 50)}")
    yaml_lines.append(f"created_at: {metadata.get('created_at', '')}")
    yaml_lines.append(f"updated_at: {metadata.get('updated_at', '')}")
    yaml_lines.append(f"access_count: {metadata.get('access_count', 1)}")
    yaml_lines.append(f"strength: {metadata.get('strength', 1.0)}")
    yaml_lines.append('---')
    yaml_lines.append('')
    
    document = '\n'.join(yaml_lines) + '\n' + content
    
    return document


def save_memory(document, category, filename, brain_path, memories_dir='memories'):
    """
    保存记忆文档
    
    Args:
        document: 文档内容
        category: 类别
        filename: 文件名
        memories_dir: 记忆仓库目录
    
    Returns:
        str: 保存路径
    """
    brain_dir = Path(brain_path).parent
    category_dir = brain_dir / memories_dir / category
    
    category_dir.mkdir(parents=True, exist_ok=True)
    
    save_path = category_dir / filename
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(document)
    
    return str(save_path)


def update_brain_index(brain_path, memory_metadata, operation='add'):
    """
    更新大脑索引
    
    Args:
        brain_path: brain.md路径
        memory_metadata: 记忆元数据
        operation: 操作类型(add/update/delete)
    
    Returns:
        bool: 是否成功
    """
    if not os.path.exists(brain_path):
        return False
    
    content = read_file_safely(brain_path)
    if not content:
        return False
    
    # 更新记忆索引表
    if operation == 'add':
        title = memory_metadata.get('title') or ''
        created_at = memory_metadata.get('created_at', '')
        created_date = created_at[:10] if isinstance(created_at, str) else ''
        new_row = (
            f"| {memory_metadata.get('id', '')} | {title} | {memory_metadata.get('category', 'other')} | "
            f"{memory_metadata.get('project', '')} | {memory_metadata.get('quality_score', 50)} | "
            f"{memory_metadata.get('strength', 1.0)} | {created_date} | "
            f"{memory_metadata.get('access_count', 1)} |\n"
        )
        
        pattern = r'(## 📚 记忆索引表\s*\n\n\|.*?\|\n\|.*?\|\n)'
        match = re.search(pattern, content)
        
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + new_row + content[insert_pos:]
        else:
            # 兜底: 追加索引表
            content += (
                "\n## 📚 记忆索引表\n\n"
                "| ID | 标题 | 类别 | 项目 | 质量 | 强度 | 创建时间 | 访问次数 |\n"
                "|----|------|------|------|------|------|----------|----------|\n"
                + new_row
            )
    
    # 更新总记忆数
    pattern = r'(\| 总记忆数 \| )(\d+)( \|)'
    match = re.search(pattern, content)
    if match:
        current_count = int(match.group(2))
        if operation == 'add':
            new_count = current_count + 1
        elif operation == 'delete':
            new_count = max(0, current_count - 1)
        else:
            new_count = current_count
        content = content[:match.start()] + f"| 总记忆数 | {new_count} |" + content[match.end():]
    
    # 更新最近更新时间
    now = datetime.now().strftime('%Y-%m-%d')
    pattern = r'(\| 最近更新 \| )([^\|]+)( \|)'
    match = re.search(pattern, content)
    if match:
        content = content[:match.start()] + f"| 最近更新 | {now} |" + content[match.end():]
    
    # 更新最近活动
    pattern = r'(## 🕐 最近活动\s*\n\n\|.*?\|\n\|.*?\|\n)'
    match = re.search(pattern, content)
    if match:
        operation_text = {
            'add': '创建',
            'update': '更新',
            'delete': '删除'
        }
        new_activity = f"| {now} | {operation_text.get(operation, '操作')} | {memory_metadata.get('id', '')} | {memory_metadata.get('title', '')} |\n"
        insert_pos = match.end()
        content = content[:insert_pos] + new_activity + content[insert_pos:]
    else:
        content += (
            "\n## 🕐 最近活动\n\n"
            "| 时间 | 操作 | 记忆ID | 详情 |\n"
            "|------|------|--------|------|\n"
            f"| {now} | 创建 | {memory_metadata.get('id', '')} | {memory_metadata.get('title', '')} |\n"
        )
    
    # 写回文件
    with open(brain_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True


def update_cue_network(brain_path, category=None, project=None, keywords=None, memory_id=None, operation='add'):
    """
    更新线索网络
    
    Args:
        brain_path: brain.md路径
        category: 类别
        project: 项目
        keywords: 关键词列表
        memory_id: 记忆ID
        operation: 操作类型
    
    Returns:
        bool: 是否成功
    """
    if not os.path.exists(brain_path):
        return False
    
    content = read_file_safely(brain_path)
    if not content:
        return False
    
    # 更新类别索引
    if category:
        pattern = rf'(\| {category} \| )(\d+)( \|)'
        match = re.search(pattern, content)
        if match:
            current_count = int(match.group(2))
            if operation == 'add':
                new_count = current_count + 1
            elif operation == 'delete':
                new_count = max(0, current_count - 1)
            else:
                new_count = current_count
            content = content[:match.start()] + f"| {category} | {new_count} |" + content[match.end():]
        else:
            # 兜底: 追加类别索引
            table_pattern = r'(### 类别索引\s*\n\n\|.*?\|\n\|.*?\|\n)'
            table_match = re.search(table_pattern, content)
            if table_match:
                new_row = f"| {category} | 1 | {CATEGORY_BRAIN_DOMINANT.get(category, 'both')} |\n"
                insert_pos = table_match.end()
                content = content[:insert_pos] + new_row + content[insert_pos:]
    
    # 更新项目索引
    if project and project != '-':
        pattern = rf'(\| {re.escape(project)} \| )(\d+)( \|)'
        match = re.search(pattern, content)
        
        now = datetime.now().strftime('%Y-%m-%d')
        
        if match:
            current_count = int(match.group(2))
            if operation == 'add':
                new_count = current_count + 1
            elif operation == 'delete':
                new_count = max(0, current_count - 1)
            else:
                new_count = current_count
            
            full_pattern = rf'\| {re.escape(project)} \| \d+ \| [^\|]+ \|'
            full_match = re.search(full_pattern, content)
            if full_match:
                content = content[:full_match.start()] + f"| {project} | {new_count} | {now} |" + content[full_match.end():]
        else:
            if operation == 'add':
                table_pattern = r'(### 项目索引\s*\n\n\|.*?\|\n\|.*?\|\n)'
                table_match = re.search(table_pattern, content)
                if table_match:
                    new_row = f"| {project} | 1 | {now} |\n"
                    insert_pos = table_match.end()
                    content = content[:insert_pos] + new_row + content[insert_pos:]
    
    # 更新关键词索引
    if keywords:
        for keyword in keywords:
            pattern = rf'(\| {re.escape(keyword)} \| )(\d+)( \|)'
            match = re.search(pattern, content)
            
            if match:
                current_count = int(match.group(2))
                if operation == 'add':
                    new_count = current_count + 1
                elif operation == 'delete':
                    new_count = max(0, current_count - 1)
                else:
                    new_count = current_count
                content = content[:match.start()] + f"| {keyword} | {new_count} |" + content[match.end():]
            else:
                if operation == 'add':
                    table_pattern = r'(### 关键词索引\s*\n\n\|.*?\|\n\|.*?\|\n)'
                    table_match = re.search(table_pattern, content)
                    if table_match:
                        new_row = f"| {keyword} | 1 |\n"
                        insert_pos = table_match.end()
                        content = content[:insert_pos] + new_row + content[insert_pos:]
    
    # 写回文件
    with open(brain_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return True


def prepare_evaluation_context(content, category, project, title):
    """
    准备价值评估上下文
    
    Args:
        content: 记忆内容
        category: 类别
        project: 项目
        title: 标题
    
    Returns:
        dict: 评估上下文
    """
    # 加载提示词模板
    prompt_path = script_dir.parent / 'prompts' / 'evaluate_quality.md'
    prompt_template = None
    if prompt_path.exists():
        prompt_template = read_file_safely(str(prompt_path))
    
    return {
        'status': 'ready_for_llm',
        'content': content,
        'category': category,
        'project': project,
        'title': title,
        'prompt_template': prompt_template
    }


def prepare_keyword_extraction_context(content, category, project, title):
    """
    准备关键词提取上下文
    
    Args:
        content: 记忆内容
        category: 类别
        project: 项目
        title: 标题
    
    Returns:
        dict: 关键词提取上下文
    """
    # 加载提示词模板
    prompt_path = script_dir.parent / 'prompts' / 'extract_keywords.md'
    prompt_template = None
    if prompt_path.exists():
        prompt_template = read_file_safely(str(prompt_path))
    
    return {
        'status': 'ready_for_llm',
        'content': content,
        'category': category,
        'project': project,
        'title': title,
        'prompt_template': prompt_template
    }


def main():
    """
    主函数: 命令行入口
    """
    parser = argparse.ArgumentParser(
        description='记忆创建辅助工具 (LLM主导模式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作模式:
  --prepare        准备创建上下文(包含评估和关键词提取)
  --create         创建记忆(使用LLM提供的完整元数据)
  --evaluate       仅准备价值评估上下文
  --extract-kw     仅准备关键词提取上下文

示例:
  # 准备上下文
  python create_memory.py --category coding --title "标题" --content "内容" --prepare
  
  # 快速创建(推荐)
  python create_memory.py --category coding --title "标题" --content "内容" --mode quick

  # 创建记忆
  python create_memory.py --metadata '{"id":"...", "category":"coding", ...}' --create

  # 强制写入(无视 no_memory 结果)
  python create_memory.py --metadata '{...}' --create --force-write
        """
    )
    
    parser.add_argument('--category', type=str, help='类别')
    parser.add_argument('--project', type=str, help='项目')
    parser.add_argument('--keywords', type=str, help='关键词(逗号分隔)')
    parser.add_argument('--title', type=str, help='标题')
    parser.add_argument('--content', type=str, help='内容')
    parser.add_argument('--brain-dominant', type=str,
                       choices=['left', 'right', 'both'], help='脑主导')
    parser.add_argument('--quality-score', type=int, default=None, help='质量评分')
    parser.add_argument('--mode', type=str, choices=['prepare', 'create', 'evaluate', 'extract-kw', 'quick'],
                       default='prepare', help='工作模式')
    parser.add_argument('--metadata', type=str, help='完整元数据JSON(仅create模式)')
    parser.add_argument('--brain-path', type=str, help='brain.md路径')
    parser.add_argument('--project-root', type=str, help='项目根目录(可选,用于自动定位brain)')
    parser.add_argument('--force-write', action='store_true', help='强制写入(即使评估决定不写)')
    
    args = parser.parse_args()
    
    # 获取brain.md路径
    if args.brain_path:
        brain_path = resolve_brain_path(explicit_path=args.brain_path)
    else:
        brain_path = resolve_brain_path(start_path=args.project_root or os.getcwd())

    # Ensure brain initialized
    load_brain(str(brain_path))
    
    try:
        if args.mode == 'prepare':
            # 准备模式: 返回评估和关键词提取上下文
            content = args.content or ''
            
            # 准备评估上下文
            eval_context = prepare_evaluation_context(
                content, args.category, args.project, args.title
            )
            
            # 准备关键词提取上下文
            kw_context = prepare_keyword_extraction_context(
                content, args.category, args.project, args.title
            )
            
            output = {
                'status': 'ready_for_llm',
                'evaluation': {
                    'prompt': eval_context['prompt_template'].format(
                        memory_content=content,
                        category=args.category or '未指定',
                        project=args.project or '未指定',
                        title=args.title or '未指定'
                    ) if eval_context['prompt_template'] else None
                },
                'keyword_extraction': {
                    'prompt': kw_context['prompt_template'].format(
                        memory_content=content,
                        category=args.category or '未指定',
                        project=args.project or '未指定',
                        title=args.title or '未指定'
                    ) if kw_context['prompt_template'] else None
                },
                'instructions': {
                    'step1': 'LLM评估记忆价值(使用evaluation.prompt)',
                    'step2': 'LLM提取关键词(使用keyword_extraction.prompt)',
                    'step3': '使用 --create 模式创建记忆,传入完整元数据'
                }
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        elif args.mode == 'evaluate':
            # 仅评估模式
            content = args.content or ''
            
            eval_context = prepare_evaluation_context(
                content, args.category, args.project, args.title
            )
            
            prompt = eval_context['prompt_template'].format(
                memory_content=content,
                category=args.category or '未指定',
                project=args.project or '未指定',
                title=args.title or '未指定'
            ) if eval_context['prompt_template'] else None
            
            output = {
                'status': 'ready_for_llm',
                'prompt': prompt
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        elif args.mode == 'extract-kw':
            # 仅关键词提取模式
            content = args.content or ''
            
            kw_context = prepare_keyword_extraction_context(
                content, args.category, args.project, args.title
            )
            
            prompt = kw_context['prompt_template'].format(
                memory_content=content,
                category=args.category or '未指定',
                project=args.project or '未指定',
                title=args.title or '未指定'
            ) if kw_context['prompt_template'] else None
            
            output = {
                'status': 'ready_for_llm',
                'prompt': prompt
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        elif args.mode == 'quick':
            # 快速创建模式: 无需LLM评估,直接写入
            content = args.content
            if not content and not sys.stdin.isatty():
                content = sys.stdin.read()
            if not content or not content.strip():
                print(json.dumps({
                    'status': 'error',
                    'error': 'EMPTY_CONTENT',
                    'message': '内容为空,无法创建记忆'
                }, ensure_ascii=False, indent=2))
                sys.exit(1)

            project_root = find_project_root(args.project_root or os.getcwd())

            metadata = {
                'title': args.title or infer_title(content),
                'category': normalize_category(args.category),
                'project': args.project or project_root.name,
                'keywords': normalize_keywords(args.keywords) or simple_keyword_extraction(content),
                'brain_dominant': args.brain_dominant or CATEGORY_BRAIN_DOMINANT.get(
                    normalize_category(args.category), 'both'
                ),
                'quality_score': args.quality_score if args.quality_score is not None else estimate_quality_score(content),
            }

            # 生成记忆ID和文件名
            memory_id = generate_memory_id()
            filename = generate_filename(memory_id=memory_id)

            now = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            metadata['id'] = memory_id
            metadata['created_at'] = now
            metadata['updated_at'] = now
            metadata['access_count'] = 1
            metadata['strength'] = 1.0

            document = create_memory_document(metadata, content)
            save_path = save_memory(document, metadata['category'], filename, brain_path)

            brain_updated = update_brain_index(str(brain_path), metadata, operation='add')
            cue_updated = update_cue_network(
                str(brain_path),
                category=metadata['category'],
                project=metadata.get('project'),
                keywords=metadata.get('keywords', []),
                memory_id=memory_id,
                operation='add'
            )

            output = {
                'status': 'success',
                'memory': {
                    'id': memory_id,
                    'title': metadata.get('title'),
                    'path': save_path,
                    'category': metadata['category'],
                    'project': metadata.get('project', ''),
                    'keywords': metadata.get('keywords', []),
                    'brain_dominant': metadata.get('brain_dominant', 'both'),
                    'quality_score': metadata.get('quality_score', 50),
                    'created_at': metadata['created_at']
                },
                'brain_updated': brain_updated,
                'cue_network_updated': cue_updated,
                'brain_path': str(brain_path)
            }

            print(json.dumps(output, ensure_ascii=False, indent=2))

        elif args.mode == 'create':
            # 创建模式: 使用LLM提供的完整元数据
            if not args.metadata:
                print(json.dumps({
                    'status': 'error',
                    'error': 'NO_METADATA',
                    'message': '请通过--metadata参数提供完整元数据JSON'
                }, ensure_ascii=False, indent=2))
                sys.exit(1)
            
            # 解析元数据
            try:
                metadata = json.loads(args.metadata)
            except json.JSONDecodeError as e:
                print(json.dumps({
                    'status': 'error',
                    'error': 'INVALID_JSON',
                    'message': str(e)
                }, ensure_ascii=False, indent=2))
                sys.exit(1)

            # 若评估明确要求不写，且未开启强制写入，则直接返回
            if not args.force_write:
                decision = metadata.get('decision')
                if decision == 'no_memory':
                    print(json.dumps({
                        'status': 'skipped',
                        'reason': 'decision=no_memory',
                        'message': '评估结果为 no_memory，未写入'
                    }, ensure_ascii=False, indent=2))
                    sys.exit(0)
            
            # 获取内容
            content = args.content
            if not content:
                if not sys.stdin.isatty():
                    content = sys.stdin.read()
                else:
                    content = f"# {metadata.get('title', '记忆')}\n\n## 背景\n\n## 需求\n\n## 解决方案\n\n## 要点\n"

            # 补全缺失字段
            project_root = find_project_root(args.project_root or os.getcwd())
            if not metadata.get('title'):
                metadata['title'] = args.title or infer_title(content)
            metadata['category'] = normalize_category(metadata.get('category') or args.category)
            metadata['project'] = metadata.get('project') or args.project or project_root.name
            metadata['keywords'] = normalize_keywords(metadata.get('keywords') or args.keywords)
            if not metadata['keywords']:
                metadata['keywords'] = simple_keyword_extraction(content)
            metadata['brain_dominant'] = metadata.get('brain_dominant') or args.brain_dominant or CATEGORY_BRAIN_DOMINANT.get(metadata['category'], 'both')
            if metadata.get('quality_score') is None:
                metadata['quality_score'] = args.quality_score if args.quality_score is not None else estimate_quality_score(content)

            # 生成记忆ID和文件名
            memory_id = metadata.get('id') or generate_memory_id()
            filename = generate_filename(metadata.get('title'), memory_id=memory_id)
            
            # 生成时间戳
            now = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
            
            # 完善元数据
            metadata['id'] = memory_id
            metadata['created_at'] = metadata.get('created_at') or now
            metadata['updated_at'] = metadata.get('updated_at') or now
            metadata['access_count'] = metadata.get('access_count', 1)
            metadata['strength'] = metadata.get('strength', 1.0)
            
            # 创建记忆文档
            document = create_memory_document(metadata, content)
            
            # 保存记忆
            save_path = save_memory(document, metadata['category'], filename, brain_path)
            
            # 更新大脑索引
            brain_updated = update_brain_index(str(brain_path), metadata, operation='add')
            
            # 更新线索网络
            cue_updated = update_cue_network(
                str(brain_path),
                category=metadata['category'],
                project=metadata.get('project'),
                keywords=metadata.get('keywords', []),
                memory_id=memory_id,
                operation='add'
            )
            
            # 构建输出
            output = {
                'status': 'success',
                'memory': {
                    'id': memory_id,
                    'title': metadata.get('title'),
                    'path': save_path,
                    'category': metadata['category'],
                    'project': metadata.get('project', ''),
                    'keywords': metadata.get('keywords', []),
                    'brain_dominant': metadata.get('brain_dominant', 'both'),
                    'quality_score': metadata.get('quality_score', 50),
                    'created_at': metadata['created_at']
                },
                'brain_updated': brain_updated,
                'cue_network_updated': cue_updated
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
    
    except Exception as e:
        error_output = {
            'status': 'error',
            'error': {
                'code': 'CREATE_FAILED',
                'message': str(e)
            }
        }
        print(json.dumps(error_output, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == '__main__':
    main()
