#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
load_brain.py - 加载大脑状态

功能：
- 读取并解析brain.md文件
- 解析YAML前置元数据
- 解析记忆索引和线索网络
- 加载最近活跃的记忆
- 输出大脑状态摘要（JSON格式）
- 处理文件不存在的初始化
"""

import os
import sys
import re
import json
from datetime import datetime
from pathlib import Path


def parse_yaml_frontmatter(content):
    """
    解析YAML前置元数据
    
    Args:
        content: 文件内容
    
    Returns:
        tuple: (yaml_data, remaining_content)
    """
    # 匹配 --- 之间的YAML内容
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, content, re.DOTALL)
    
    if not match:
        return {}, content
    
    yaml_str = match.group(1)
    remaining = content[match.end():]
    
    # 简单解析YAML（不使用yaml库）
    yaml_data = {}
    for line in yaml_str.split('\n'):
        if ':' in line:
            key, value = line.split(':', 1)
            yaml_data[key.strip()] = value.strip()
    
    return yaml_data, remaining


def parse_markdown_table(content, table_header):
    """
    解析Markdown表格
    
    Args:
        content: 文件内容
        table_header: 表格标题（如"类别索引"）
    
    Returns:
        list: 表格数据列表
    """
    # 查找表格位置
    pattern = rf'###\s+{table_header}\s*\n\n\|.*?\|\n\|.*?\|\n((?:\|.*?\|\n)+)'
    match = re.search(pattern, content)
    
    if not match:
        return []
    
    table_content = match.group(1)
    rows = []
    
    for line in table_content.strip().split('\n'):
        if line.startswith('|'):
            # 分割表格列
            cells = [cell.strip() for cell in line.split('|')[1:-1]]
            if cells and cells[0] and cells[0] != '-':
                rows.append(cells)
    
    return rows


def parse_memory_index(content):
    """
    解析记忆索引表
    
    Args:
        content: 文件内容
    
    Returns:
        list: 记忆索引列表
    """
    rows = parse_markdown_table(content, "记忆索引表")
    
    memories = []
    for row in rows:
        if len(row) >= 8:
            try:
                memory = {
                    'id': row[0],
                    'title': row[1],
                    'category': row[2],
                    'project': row[3],
                    'quality': int(row[4]) if row[4].isdigit() else 0,
                    'strength': float(row[5]) if row[5].replace('.', '').isdigit() else 1.0,
                    'created_at': row[6],
                    'access_count': int(row[7]) if row[7].isdigit() else 0
                }
                memories.append(memory)
            except (ValueError, IndexError):
                continue
    
    return memories


def parse_cue_network(content):
    """
    解析线索网络
    
    Args:
        content: 文件内容
    
    Returns:
        dict: 线索网络数据
    """
    cue_network = {
        'categories': [],
        'projects': [],
        'keywords': []
    }
    
    # 解析类别索引
    category_rows = parse_markdown_table(content, "类别索引")
    for row in category_rows:
        if len(row) >= 3 and row[0] != '-':
            cue_network['categories'].append({
                'name': row[0],
                'count': int(row[1]) if row[1].isdigit() else 0,
                'brain_dominant': row[2]
            })
    
    # 解析项目索引
    project_rows = parse_markdown_table(content, "项目索引")
    for row in project_rows:
        if len(row) >= 3 and row[0] != '-':
            cue_network['projects'].append({
                'name': row[0],
                'count': int(row[1]) if row[1].isdigit() else 0,
                'last_active': row[2]
            })
    
    # 解析关键词索引
    keyword_rows = parse_markdown_table(content, "关键词索引")
    for row in keyword_rows:
        if len(row) >= 2 and row[0] != '-':
            cue_network['keywords'].append({
                'word': row[0],
                'frequency': int(row[1]) if row[1].isdigit() else 0
            })
    
    return cue_network


def parse_system_status(content):
    """
    解析系统状态
    
    Args:
        content: 文件内容
    
    Returns:
        dict: 系统状态
    """
    status = {
        'total_memories': 0,
        'total_cues': 0,
        'last_updated': '',
        'system_version': 'v1.0'
    }
    
    # 查找系统状态表格
    pattern = r'##\s+📊\s+系统状态\s*\n\n\|.*?\|\n\|.*?\|\n((?:\|.*?\|\n)+)'
    match = re.search(pattern, content)
    
    if match:
        table_content = match.group(1)
        for line in table_content.strip().split('\n'):
            if line.startswith('|'):
                cells = [cell.strip() for cell in line.split('|')[1:-1]]
                if len(cells) >= 2:
                    key = cells[0]
                    value = cells[1]
                    if '总记忆数' in key:
                        status['total_memories'] = int(value) if value.isdigit() else 0
                    elif '总线索数' in key:
                        status['total_cues'] = int(value) if value.isdigit() else 0
                    elif '最近更新' in key:
                        status['last_updated'] = value
                    elif '系统版本' in key:
                        status['system_version'] = value
    
    return status


def get_recent_memories(memories, count=5):
    """
    获取最近活跃的记忆
    
    Args:
        memories: 记忆索引列表
        count: 返回数量
    
    Returns:
        list: 最近记忆列表
    """
    # 按创建时间降序排序
    sorted_memories = sorted(
        memories,
        key=lambda m: m.get('created_at', ''),
        reverse=True
    )
    
    return sorted_memories[:count]


def initialize_brain(brain_path):
    """
    初始化大脑文件
    
    Args:
        brain_path: brain.md文件路径
    
    Returns:
        dict: 初始化后的大脑数据
    """
    brain_dir = Path(brain_path).parent
    memories_dir = brain_dir / 'memories'
    
    # 创建目录结构
    for category in ['coding', 'design', 'config', 'docs', 'debug', 'other']:
        category_dir = memories_dir / category
        category_dir.mkdir(parents=True, exist_ok=True)
    
    archive_dir = brain_dir / 'archive'
    archive_dir.mkdir(parents=True, exist_ok=True)
    
    references_dir = brain_dir / 'references'
    references_dir.mkdir(parents=True, exist_ok=True)
    
    # 创建默认brain.md
    now = datetime.now().strftime('%Y-%m-%d')
    default_content = f"""---
version: 1.0
created_at: {now}
updated_at: {now}
---

# 🧠 大脑状态文档 (Brain.md)

## 📊 系统状态

| 指标 | 数值 |
|------|------|
| 总记忆数 | 0 |
| 总线索数 | 0 |
| 最近更新 | {now} |
| 系统版本 | v1.0 |

## ⚙️ 配置参数

```yaml
# 记忆管理参数
memory:
  max_per_category: 50      # 每个类别最大记忆数
  compression_threshold: 500  # 压缩阈值（行数）
  archive_after_days: 30     # 归档天数
  
# 线索网络参数
cue_network:
  max_keywords: 100         # 最大关键词数
  min_frequency: 2          # 最小出现频率
  decay_factor: 0.95        # 衰减因子
  
# 遗忘曲线参数
forgetting:
  half_life: 7              # 半衰期（天）
  min_strength: 0.1         # 最小强度阈值
```

## 🕸️ 线索网络

### 类别索引

| 类别 | 数量 | 脑主导 |
|------|------|--------|
| coding | 0 | 左脑 |
| design | 0 | 右脑 |
| config | 0 | 左脑 |
| docs | 0 | 右脑 |
| debug | 0 | 左脑 |
| other | 0 | 右脑 |

### 项目索引

| 项目 | 数量 | 最后活跃 |
|------|------|----------|
| - | 0 | - |

### 关键词索引

| 关键词 | 频率 |
|--------|------|
| - | 0 |

## 📚 记忆索引表

| ID | 标题 | 类别 | 项目 | 质量 | 强度 | 创建时间 | 访问次数 |
|----|------|------|------|------|------|----------|----------|

## 🕐 最近活动

| 时间 | 操作 | 记忆ID | 详情 |
|------|------|--------|------|
| {now} | 初始化 | - | 系统初始化完成 |
"""
    
    # 写入文件
    with open(brain_path, 'w', encoding='utf-8') as f:
        f.write(default_content)
    
    print(f"✅ 大脑初始化完成: {brain_path}")
    
    # 返回初始化数据
    return {
        'yaml': {'version': '1.0', 'created_at': now, 'updated_at': now},
        'status': {
            'total_memories': 0,
            'total_cues': 0,
            'last_updated': now,
            'system_version': 'v1.0'
        },
        'memories': [],
        'cue_network': parse_cue_network(default_content)
    }


def load_brain(brain_path):
    """
    加载大脑文件
    
    Args:
        brain_path: brain.md文件路径
    
    Returns:
        dict: 大脑数据结构
    
    Raises:
        FileNotFoundError: 文件不存在时自动初始化
    """
    # 检查文件是否存在
    if not os.path.exists(brain_path):
        print(f"⚠️  大脑文件不存在，正在初始化...")
        return initialize_brain(brain_path)
    
    # 读取文件
    try:
        with open(brain_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except UnicodeDecodeError:
        # 尝试其他编码
        with open(brain_path, 'r', encoding='gbk') as f:
            content = f.read()
    
    # 解析YAML前置元数据
    yaml_data, remaining = parse_yaml_frontmatter(content)
    
    # 解析系统状态
    status = parse_system_status(remaining)
    
    # 解析记忆索引
    memories = parse_memory_index(remaining)
    
    # 解析线索网络
    cue_network = parse_cue_network(remaining)
    
    return {
        'yaml': yaml_data,
        'status': status,
        'memories': memories,
        'cue_network': cue_network
    }


def main():
    """
    主函数：加载大脑并输出状态
    """
    # 获取brain.md路径
    script_dir = Path(__file__).parent
    brain_path = script_dir.parent / 'brain.md'
    
    try:
        # 加载大脑
        brain_data = load_brain(str(brain_path))
        
        # 获取最近记忆
        recent_memories = get_recent_memories(brain_data['memories'], count=5)
        
        # 构建输出
        output = {
            'status': 'success',
            'brain': {
                'version': brain_data['yaml'].get('version', '1.0'),
                'memory_count': brain_data['status']['total_memories'],
                'category_count': len(brain_data['cue_network']['categories']),
                'project_count': len([p for p in brain_data['cue_network']['projects'] if p['name'] != '-']),
                'last_updated': brain_data['status']['last_updated']
            },
            'recent_memories': [
                {
                    'id': m['id'],
                    'title': m['title'],
                    'category': m['category'],
                    'project': m['project'],
                    'quality': m['quality']
                }
                for m in recent_memories
            ],
            'cue_network': {
                'categories': [c['name'] for c in brain_data['cue_network']['categories']],
                'projects': [p['name'] for p in brain_data['cue_network']['projects'] if p['name'] != '-'],
                'top_keywords': [k['word'] for k in brain_data['cue_network']['keywords'][:10] if k['word'] != '-']
            }
        }
        
        # 输出JSON
        print(json.dumps(output, ensure_ascii=False, indent=2))
        
    except Exception as e:
        # 错误输出
        error_output = {
            'status': 'error',
            'error': {
                'code': 'LOAD_FAILED',
                'message': str(e)
            }
        }
        print(json.dumps(error_output, ensure_ascii=False, indent=2))
        sys.exit(1)


if __name__ == '__main__':
    main()
