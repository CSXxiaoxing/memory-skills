#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
compress.py - 记忆压缩辅助工具

新架构: LLM主导 + Python辅助
- Python负责: 文件读取、结构提取、数据准备、结果保存
- LLM负责: 压缩决策、语义理解、内容压缩

工作模式:
1. --prepare: 准备压缩上下文,返回给LLM处理
2. --apply: 应用LLM的压缩结果
3. --legacy: 旧版机械压缩(保留向后兼容)
"""

import os
import sys
import re
import json
import argparse
import shutil
import yaml
from datetime import datetime
from pathlib import Path

script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from project_utils import read_file_safely, get_memory_dir, resolve_brain_path


def extract_structure(content):
    """
    提取文档结构(供LLM分析)
    
    Returns:
        dict: 结构化数据
    """
    structure = {
        'yaml_frontmatter': '',
        'headings': [],
        'code_blocks': [],
        'paragraphs': [],
        'lists': []
    }
    
    # 提取YAML前置元数据
    yaml_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
    if yaml_match:
        structure['yaml_frontmatter'] = '---\n' + yaml_match.group(1) + '\n---\n\n'
        content_after_yaml = content[yaml_match.end():]
    else:
        content_after_yaml = content
    
    # 提取代码块(完整保留)
    code_block_pattern = r'```[\s\S]*?```'
    code_blocks = re.findall(code_block_pattern, content_after_yaml)
    structure['code_blocks'] = code_blocks
    
    # 移除代码块后的内容
    content_no_code = re.sub(code_block_pattern, '', content_after_yaml)
    
    # 提取标题
    heading_pattern = r'^(#{1,6})\s+(.+)$'
    headings = re.findall(heading_pattern, content_no_code, re.MULTILINE)
    structure['headings'] = [{'level': len(h[0]), 'text': h[1]} for h in headings]
    
    # 提取列表项
    list_pattern = r'^[-*+]\s+.+$|^\d+\.\s+.+$'
    lists = re.findall(list_pattern, content_no_code, re.MULTILINE)
    structure['lists'] = lists
    
    # 提取段落
    paragraphs = re.split(r'\n\n+', content_no_code)
    for para in paragraphs:
        para = para.strip()
        # 跳过标题、列表和空段落
        if para and not re.match(r'^#{1,6}\s+', para) and not re.match(list_pattern, para):
            structure['paragraphs'].append(para)
    
    return structure


def analyze_for_compression(memory_path):
    """
    分析记忆文件,准备压缩上下文
    
    Args:
        memory_path: 记忆文件路径
    
    Returns:
        dict: 分析结果
    """
    content = read_file_safely(memory_path)
    
    if content is None:
        return {
            'status': 'error',
            'error': 'FILE_NOT_FOUND',
            'message': f'记忆文件不存在: {memory_path}'
        }
    
    # 提取结构
    structure = extract_structure(content)
    
    # 统计信息
    stats = {
        'total_length': len(content),
        'yaml_length': len(structure['yaml_frontmatter']),
        'code_block_count': len(structure['code_blocks']),
        'code_block_total_length': sum(len(cb) for cb in structure['code_blocks']),
        'heading_count': len(structure['headings']),
        'paragraph_count': len(structure['paragraphs']),
        'list_count': len(structure['lists'])
    }
    
    # 估算可压缩空间
    non_code_length = stats['total_length'] - stats['code_block_total_length']
    estimated_compressed_length = stats['code_block_total_length'] + (non_code_length // 3)
    
    stats['estimated_compressed_length'] = estimated_compressed_length
    stats['compression_ratio'] = estimated_compressed_length / stats['total_length'] if stats['total_length'] > 0 else 0
    
    # 加载提示词模板
    script_dir = Path(__file__).parent
    prompt_path = script_dir.parent / 'prompts' / 'compress_prompt.md'
    
    prompt_template = None
    if prompt_path.exists():
        prompt_template = read_file_safely(str(prompt_path))
    
    # 构建结构分析文本
    structure_analysis = f"""
文档统计:
- 总长度: {stats['total_length']} 字符
- YAML元数据: {stats['yaml_length']} 字符
- 代码块: {stats['code_block_count']} 个,共 {stats['code_block_total_length']} 字符
- 标题: {stats['heading_count']} 个
- 段落: {stats['paragraph_count']} 个
- 列表: {stats['list_count']} 个

预估压缩:
- 压缩后长度: 约 {estimated_compressed_length} 字符
- 压缩比: {stats['compression_ratio']:.1%}

标题结构:
{chr(10).join(f"  {'#' * h['level']} {h['text']}" for h in structure['headings'])}

代码块位置:
{chr(10).join(f"  - 代码块 {i+1}: {len(cb)} 字符" for i, cb in enumerate(structure['code_blocks']))}
"""
    
    return {
        'status': 'ready_for_llm',
        'memory_path': memory_path,
        'content': content,
        'structure': structure,
        'stats': stats,
        'structure_analysis': structure_analysis,
        'prompt_template': prompt_template
    }


def prepare_compression_prompt(analysis_result):
    """
    准备完整的压缩提示词
    
    Args:
        analysis_result: analyze_for_compression的返回结果
    
    Returns:
        str: 完整的提示词
    """
    if analysis_result['status'] != 'ready_for_llm':
        return None
    
    template = analysis_result['prompt_template']
    if not template:
        # 使用默认提示词
        template = """# 记忆压缩任务

## 原始记忆内容

{memory_content}

## 文档结构分析

{structure_analysis}

## 压缩要求

1. 完整保留YAML前置元数据
2. 完整保留所有代码块
3. 完整保留所有标题结构
4. 压缩描述性段落为摘要(保留首句+关键信息)
5. 目标: 压缩到原长度的1/3

直接输出压缩后的markdown文档。"""
    
    # 填充模板
    prompt = template.format(
        memory_content=analysis_result['content'],
        structure_analysis=analysis_result['structure_analysis']
    )
    
    return prompt


def apply_compression(memory_path, compressed_content, archive_original=True):
    """
    应用LLM的压缩结果
    
    Args:
        memory_path: 原始记忆路径
        compressed_content: LLM压缩后的内容
        archive_original: 是否归档原始文件
    
    Returns:
        dict: 应用结果
    """
    # 验证压缩内容
    if not compressed_content or not compressed_content.strip():
        return {
            'status': 'error',
            'error': 'EMPTY_CONTENT',
            'message': '压缩内容为空'
        }
    
    # 读取原始内容用于对比
    original_content = read_file_safely(memory_path)
    original_length = len(original_content) if original_content else 0
    compressed_length = len(compressed_content)
    
    # 归档原始文件
    archived_path = None
    if archive_original and os.path.exists(memory_path):
        memory_dir = os.path.dirname(memory_path)
        brain_dir = os.path.dirname(memory_dir)
        archive_dir = os.path.join(brain_dir, 'archive')
        
        # 确保归档目录存在
        os.makedirs(archive_dir, exist_ok=True)
        
        # 生成归档文件名
        filename = os.path.basename(memory_path)
        name, ext = os.path.splitext(filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        archived_name = f"{name}_{timestamp}{ext}"
        archived_path = os.path.join(archive_dir, archived_name)
        
        # 移动原始文件
        shutil.move(memory_path, archived_path)
    
    # 保存压缩内容
    with open(memory_path, 'w', encoding='utf-8') as f:
        f.write(compressed_content)
    
    return {
        'status': 'success',
        'memory_path': memory_path,
        'compression': {
            'original_length': original_length,
            'compressed_length': compressed_length,
            'compression_ratio': compressed_length / original_length if original_length > 0 else 0,
            'space_saved': original_length - compressed_length
        },
        'archive': {
            'archived': archived_path is not None,
            'archive_path': archived_path
        }
    }


def get_all_memory_files(brain_path: Path, category: str = None, quality_threshold: int = None) -> list[Path]:
    """
    获取所有符合条件的记忆文件
    
    Args:
        brain_path: 大脑目录路径
        category: 指定类别, None表示所有类别
        quality_threshold: 质量分数阈值, 只压缩低于此分数的记忆
    
    Returns:
        list[Path]: 记忆文件路径列表
    """
    memory_dir = get_memory_dir(str(brain_path))
    memory_files = []
    
    # 遍历所有类别目录
    for cat_dir in memory_dir.iterdir():
        if not cat_dir.is_dir():
            continue
        if category and cat_dir.name != category:
            continue
            
        # 遍历目录下的md文件
        for file in cat_dir.glob('*.md'):
            if quality_threshold is not None:
                # 读取YAML元数据检查质量分数
                content = read_file_safely(str(file))
                if content:
                    yaml_match = re.match(r'^---\s*\n(.*?)\n---\s*\n', content, re.DOTALL)
                    if yaml_match:
                        try:
                            metadata = yaml.safe_load(yaml_match.group(1))
                            if metadata and metadata.get('quality_score', 100) >= quality_threshold:
                                continue  # 质量高于阈值,跳过
                        except:
                            pass  # 解析失败,继续处理
            
            memory_files.append(file)
    
    return memory_files


def batch_compress(brain_path: Path, category: str = None, quality_threshold: int = None, mode: str = 'legacy') -> dict:
    """
    批量压缩记忆
    
    Args:
        brain_path: 大脑目录路径
        category: 指定类别压缩
        quality_threshold: 质量分数阈值, 只压缩低于此分数的记忆
        mode: 压缩模式, legacy或prepare/apply
    
    Returns:
        dict: 压缩结果统计
    """
    memory_files = get_all_memory_files(brain_path, category, quality_threshold)
    total = len(memory_files)
    success = 0
    failed = 0
    total_original = 0
    total_compressed = 0
    
    results = []
    
    for file in memory_files:
        try:
            if mode == 'legacy':
                # 机械压缩
                content = read_file_safely(str(file))
                if not content:
                    failed += 1
                    continue
                    
                original_len = len(content)
                compressed_content = legacy_compress(content)
                compressed_len = len(compressed_content)
                
                # 归档并保存
                archive_dir = brain_path / 'archive'
                os.makedirs(archive_dir, exist_ok=True)
                
                filename = file.name
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                archived_name = f"{name}_{timestamp}{ext}"
                archived_path = archive_dir / archived_name
                
                shutil.move(str(file), str(archived_path))
                
                with open(file, 'w', encoding='utf-8') as f:
                    f.write(compressed_content)
                
                total_original += original_len
                total_compressed += compressed_len
                success += 1
                
                results.append({
                    'file': str(file),
                    'status': 'success',
                    'original_length': original_len,
                    'compressed_length': compressed_len,
                    'compression_ratio': compressed_len / original_len if original_len > 0 else 0
                })
                
        except Exception as e:
            failed += 1
            results.append({
                'file': str(file),
                'status': 'failed',
                'error': str(e)
            })
    
    return {
        'total': total,
        'success': success,
        'failed': failed,
        'total_original_length': total_original,
        'total_compressed_length': total_compressed,
        'total_space_saved': total_original - total_compressed,
        'average_compression_ratio': total_compressed / total_original if total_original > 0 else 0,
        'results': results
    }


def legacy_compress(content):
    """
    旧版机械压缩(向后兼容)
    
    Args:
        content: 原始内容
    
    Returns:
        str: 压缩后内容
    """
    structure = extract_structure(content)
    
    compressed = []
    
    # 添加YAML
    if structure['yaml_frontmatter']:
        compressed.append(structure['yaml_frontmatter'])
    
    # 移除YAML后的内容
    yaml_match = re.match(r'^---\s*\n.*?\n---\s*\n', content, re.DOTALL)
    if yaml_match:
        content_no_yaml = content[yaml_match.end():]
    else:
        content_no_yaml = content
    
    # 移除代码块
    content_no_code = re.sub(r'```[\s\S]*?```', '', content_no_yaml)
    
    # 按段落处理
    paragraphs = re.split(r'\n\n+', content_no_code)
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # 标题完整保留
        if re.match(r'^#{1,6}\s+', para):
            compressed.append(para)
            compressed.append('\n\n')
        # 列表项完整保留
        elif re.match(r'^[-*+]\s+', para) or re.match(r'^\d+\.\s+', para):
            compressed.append(para)
            compressed.append('\n\n')
        # 普通段落压缩
        else:
            # 按句子分割
            sentences = re.split(r'[。！？.!?]', para)
            sentences = [s.strip() for s in sentences if s.strip()]
            
            # 取前2个句子
            if len(sentences) > 2:
                summary = '。'.join(sentences[:2])
                if not summary.endswith('。'):
                    summary += '。'
                compressed.append('<!-- 压缩摘要 -->')
                compressed.append(summary)
                compressed.append('\n\n')
            else:
                compressed.append(para)
                compressed.append('\n\n')
    
    # 添加代码块
    for code_block in structure['code_blocks']:
        compressed.append(code_block)
        compressed.append('\n\n')
    
    return ''.join(compressed)


def main():
    """
    主函数: 命令行入口
    """
    parser = argparse.ArgumentParser(
        description='记忆压缩辅助工具 (LLM主导模式)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
工作模式:
  --prepare        准备压缩上下文,输出JSON给LLM处理
  --apply          从stdin读取LLM压缩结果并应用
  --legacy         使用旧版机械压缩(向后兼容)

批量压缩选项:
  --batch          批量压缩所有符合条件的记忆
  --all            压缩所有记忆(等价于 --batch)
  --category       指定压缩的类别(coding/design/docs等)
  --quality-threshold 只压缩质量分数低于此值的记忆(默认: 50)
  --brain-path     指定brain.md路径,默认自动检测

示例:
  # 新模式: LLM主导压缩单个文件
  python compress.py --memory file.md --prepare
  # (LLM处理输出)
  python compress.py --memory file.md --apply
  
  # 旧模式: 机械压缩单个文件
  python compress.py --memory file.md --legacy
  
  # 批量压缩所有记忆
  python compress.py --all --mode legacy
  
  # 批量压缩coding类别记忆
  python compress.py --batch --category coding
  
  # 批量压缩质量低于50分的记忆
  python compress.py --batch --quality-threshold 50
        """
    )
    
    parser.add_argument('--memory', type=str, help='记忆文件路径(单个压缩时必填)')
    parser.add_argument('--mode', type=str, choices=['prepare', 'apply', 'legacy'], 
                       default='legacy', help='工作模式')
    parser.add_argument('--no-archive', action='store_true', help='不归档原始文件')
    parser.add_argument('--output', type=str, help='输出路径(仅legacy模式)')
    
    # 批量压缩参数
    parser.add_argument('--batch', action='store_true', help='批量压缩记忆')
    parser.add_argument('--all', action='store_true', help='压缩所有记忆')
    parser.add_argument('--category', type=str, help='指定压缩的类别')
    parser.add_argument('--quality-threshold', type=int, default=50, help='质量分数阈值')
    parser.add_argument('--brain-path', type=str, help='指定brain.md路径')
    
    args = parser.parse_args()
    
    try:
        if args.mode == 'prepare':
            # 准备模式: 分析并返回给LLM
            analysis = analyze_for_compression(args.memory)
            
            if analysis['status'] == 'error':
                print(json.dumps(analysis, ensure_ascii=False, indent=2))
                sys.exit(1)
            
            # 准备提示词
            prompt = prepare_compression_prompt(analysis)
            
            # 输出JSON
            output = {
                'status': 'ready_for_llm',
                'memory_path': args.memory,
                'prompt': prompt,
                'stats': analysis['stats'],
                'instructions': {
                    'step1': 'LLM处理上述prompt',
                    'step2': 'LLM输出压缩后的markdown',
                    'step3': '使用 --apply 模式应用压缩结果'
                }
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
        
        elif args.mode == 'apply':
            # 应用模式: 从stdin读取LLM的压缩结果
            if sys.stdin.isatty():
                print(json.dumps({
                    'status': 'error',
                    'error': 'NO_STDIN',
                    'message': '请通过stdin提供压缩内容'
                }, ensure_ascii=False, indent=2))
                sys.exit(1)
            
            compressed_content = sys.stdin.read()
            
            result = apply_compression(
                args.memory, 
                compressed_content, 
                archive_original=not args.no_archive
            )
            
            print(json.dumps(result, ensure_ascii=False, indent=2))
        
        elif args.mode == 'legacy':
            # 旧版模式: 机械压缩
            content = read_file_safely(args.memory)
            
            if content is None:
                print(json.dumps({
                    'status': 'error',
                    'error': 'FILE_NOT_FOUND',
                    'message': f'记忆文件不存在: {args.memory}'
                }, ensure_ascii=False, indent=2))
                sys.exit(1)
            
            # 执行压缩
            compressed = legacy_compress(content)
            
            # 确定输出路径
            output_path = args.output if args.output else args.memory
            
            # 归档原始文件
            archived_path = None
            if not args.no_archive and os.path.exists(args.memory):
                memory_dir = os.path.dirname(args.memory)
                brain_dir = os.path.dirname(memory_dir)
                archive_dir = os.path.join(brain_dir, 'archive')
                os.makedirs(archive_dir, exist_ok=True)
                
                filename = os.path.basename(args.memory)
                name, ext = os.path.splitext(filename)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                archived_name = f"{name}_{timestamp}{ext}"
                archived_path = os.path.join(archive_dir, archived_name)
                
                shutil.move(args.memory, archived_path)
            
            # 保存压缩内容
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(compressed)
            
            # 输出结果
            output = {
                'status': 'success',
                'mode': 'legacy',
                'compression': {
                    'original_length': len(content),
                    'compressed_length': len(compressed),
                    'compression_ratio': len(compressed) / len(content) if content else 0
                },
                'archive': {
                    'archived': archived_path is not None,
                    'archive_path': archived_path
                },
                'output_path': output_path
            }
            
            print(json.dumps(output, ensure_ascii=False, indent=2))
    
    except Exception as e:
        error_output = {
            'status': 'error',
            'error': {
                'code': 'COMPRESS_FAILED',
                'message': str(e)
            }
        }
        print(json.dumps(error_output, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == '__main__':
    main()
