#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_stats.py - 记忆统计报告导出工具
支持导出JSON和HTML格式的统计报告
"""

import os
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime

# 导入工具模块
script_dir = Path(__file__).parent
sys.path.insert(0, str(script_dir))
from project_utils import resolve_brain_path, _collect_memory_statistics, read_file_safely
from stats import show_statistics as get_detailed_stats

def export_json(stats: dict, output_path: str = None) -> str:
    """导出统计报告为JSON格式"""
    if not output_path:
        output_path = f"memory_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    return output_path

def export_html(stats: dict, output_path: str = None) -> str:
    """导出统计报告为HTML格式"""
    if not output_path:
        output_path = f"memory_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"
    
    category_counts = stats.get('category_counts', {})
    total = stats.get('total_count', 0)
    
    # 生成类别统计HTML
    category_rows = ""
    for cat, count in category_counts.items():
        percentage = (count / total * 100) if total > 0 else 0
        category_rows += f"""
        <tr>
            <td>{cat}</td>
            <td>{count}</td>
            <td>{percentage:.1f}%</td>
        </tr>
        """
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>记忆技能统计报告</title>
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f5f5f5;
            }}
            .container {{
                background: white;
                border-radius: 8px;
                padding: 30px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.1);
            }}
            h1 {{
                color: #2c3e50;
                margin-bottom: 10px;
                font-size: 28px;
            }}
            .subtitle {{
                color: #7f8c8d;
                margin-bottom: 30px;
                font-size: 14px;
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 30px;
            }}
            .stat-card {{
                background: #f8f9fa;
                padding: 20px;
                border-radius: 8px;
                text-align: center;
            }}
            .stat-value {{
                font-size: 32px;
                font-weight: bold;
                color: #3498db;
                margin-bottom: 5px;
            }}
            .stat-label {{
                font-size: 14px;
                color: #7f8c8d;
            }}
            h2 {{
                color: #2c3e50;
                margin: 30px 0 15px 0;
                font-size: 20px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-bottom: 30px;
            }}
            th, td {{
                padding: 12px 15px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }}
            th {{
                background-color: #f8f9fa;
                font-weight: 600;
                color: #2c3e50;
            }}
            tr:hover {{
                background-color: #f8f9fa;
            }}
            .footer {{
                text-align: center;
                margin-top: 30px;
                padding-top: 20px;
                border-top: 1px solid #eee;
                color: #7f8c8d;
                font-size: 12px;
            }}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🧠 记忆技能统计报告</h1>
            <p class="subtitle">生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            
            <div class="stats-grid">
                <div class="stat-card">
                    <div class="stat-value">{stats.get('total_count', 0)}</div>
                    <div class="stat-label">总记忆数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('standalone_count', 0)}</div>
                    <div class="stat-label">独立记忆数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('fragment_count', 0)}</div>
                    <div class="stat-label">碎片记忆数</div>
                </div>
                <div class="stat-card">
                    <div class="stat-value">{stats.get('docs_extra_count', 0)}</div>
                    <div class="stat-label">文档类记忆数</div>
                </div>
            </div>
            
            <h2>📊 类别分布</h2>
            <table>
                <thead>
                    <tr>
                        <th>类别</th>
                        <th>数量</th>
                        <th>占比</th>
                    </tr>
                </thead>
                <tbody>
                    {category_rows}
                </tbody>
            </table>
            
            <div class="footer">
                由 memory-skills 技能自动生成
            </div>
        </div>
    </body>
    </html>
    """
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)
    
    return output_path

def main():
    parser = argparse.ArgumentParser(description="导出记忆统计报告")
    parser.add_argument("--format", choices=["json", "html"], default="json", help="导出格式")
    parser.add_argument("--output", help="输出文件路径")
    parser.add_argument("--brain-path", help="指定brain.md路径")
    
    args = parser.parse_args()
    
    # 解析brain路径
    brain_path = resolve_brain_path(explicit_path=args.brain_path)
    
    # 获取统计数据
    stats = get_detailed_stats(str(brain_path))
    
    # 导出
    if args.format == "json":
        output_file = export_json(stats, args.output)
    else:
        output_file = export_html(stats, args.output)
    
    print(json.dumps({
        "status": "success",
        "format": args.format,
        "output_file": str(Path(output_file).resolve())
    }, ensure_ascii=False))

if __name__ == "__main__":
    main()
