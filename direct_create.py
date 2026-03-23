#!/usr/bin/env python3
import os
import re
import json
from datetime import datetime
from pathlib import Path

from scripts.project_utils import resolve_brain_path

script_dir = Path(__file__).parent

def read_file_safely(file_path):
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
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    microsecond = datetime.now().microsecond
    sequence = str(microsecond // 1000).zfill(3)
    return f"mem_{timestamp}_{sequence}"

def generate_filename(memory_id=None, title=None):
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

def create_memory_document(metadata, content):
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
    brain_dir = Path(brain_path).parent
    category_dir = brain_dir / memories_dir / category
    category_dir.mkdir(parents=True, exist_ok=True)
    save_path = category_dir / filename
    with open(save_path, 'w', encoding='utf-8') as f:
        f.write(document)
    return str(save_path)

def update_brain_index(brain_path, memory_metadata, operation='add'):
    if not os.path.exists(brain_path):
        return False
    content = read_file_safely(brain_path)
    if not content:
        return False
    if operation == 'add':
        new_row = f"| {memory_metadata['id']} | {memory_metadata['title']} | {memory_metadata['category']} | {memory_metadata.get('project', '')} | {memory_metadata.get('quality_score', 50)} | {memory_metadata.get('strength', 1.0)} | {memory_metadata['created_at'][:10]} | {memory_metadata.get('access_count', 1)} |\n"
        pattern = r'(## 📚 记忆索引表\s*\n\n\|.*?\|\n\|.*?\|\n)'
        match = re.search(pattern, content)
        if match:
            insert_pos = match.end()
            content = content[:insert_pos] + new_row + content[insert_pos:]
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
    now = datetime.now().strftime('%Y-%m-%d')
    pattern = r'(\| 最近更新 \| )([^\|]+)( \|)'
    match = re.search(pattern, content)
    if match:
        content = content[:match.start()] + f"| 最近更新 | {now} |" + content[match.end():]
    pattern = r'(## 🕐 最近活动\s*\n\n\|.*?\|\n\|.*?\|\n)'
    match = re.search(pattern, content)
    if match:
        operation_text = {'add': '创建', 'update': '更新', 'delete': '删除'}
        new_activity = f"| {now} | {operation_text.get(operation, '操作')} | {memory_metadata['id']} | {memory_metadata.get('title', '')} |\n"
        insert_pos = match.end()
        content = content[:insert_pos] + new_activity + content[insert_pos:]
    with open(brain_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

def update_cue_network(brain_path, category=None, project=None, keywords=None, memory_id=None, operation='add'):
    if not os.path.exists(brain_path):
        return False
    content = read_file_safely(brain_path)
    if not content:
        return False
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
    with open(brain_path, 'w', encoding='utf-8') as f:
        f.write(content)
    return True

# Metadata
metadata = {
    "category": "coding",
    "project": "skills体验",
    "title": "Python用户认证模块实现方案",
    "keywords": ["JWT", "bcrypt", "密码加密", "token刷新", "用户认证"],
    "brain_dominant": "left",
    "quality_score": 68
}

# Content
content = """## 背景
需要为Python项目实现用户认证模块，处理JWT token和密码加密。

## 需求
1. JWT token生成和验证
2. 密码加密存储（使用bcrypt）
3. Token刷新机制
4. 登录/注册API接口

## 解决方案

### JWT Token处理
```python
import jwt
from datetime import datetime, timedelta

SECRET_KEY = 'your-secret-key'
ALGORITHM = 'HS256'
TOKEN_EXPIRE_MINUTES = 30

def create_token(user_id: int) -> str:
    payload = {
        'user_id': user_id,
        'exp': datetime.utcnow() + timedelta(minutes=TOKEN_EXPIRE_MINUTES),
        'iat': datetime.utcnow()
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

def verify_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return {'valid': True, 'user_id': payload.get('user_id')}
    except jwt.ExpiredSignatureError:
        return {'valid': False, 'error': 'Token已过期'}
    except jwt.InvalidTokenError:
        return {'valid': False, 'error': '无效Token'}
```

### 密码加密（bcrypt）
```python
import bcrypt

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
```

### Token刷新机制
```python
def refresh_token(old_token: str) -> dict:
    payload = verify_token(old_token)
    if not payload['valid']:
        return payload
    new_token = create_token(payload['user_id'])
    return {'valid': True, 'token': new_token}
```

## 要点
- JWT secret key要保密，不要硬编码在代码中
- 密码加密必须使用bcrypt，不要使用简单hash
- Token过期时间根据业务需求调整
- refresh_token需要验证旧token有效性"""

# Generate IDs and timestamps
memory_id = generate_memory_id()
filename = generate_filename(memory_id=memory_id, title=metadata.get('title'))
now = datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')

# Complete metadata
metadata['id'] = memory_id
metadata['created_at'] = now
metadata['updated_at'] = now
metadata['access_count'] = 1
metadata['strength'] = 1.0

# Create document
document = create_memory_document(metadata, content)

# Save memory
brain_path = resolve_brain_path(start_path=Path.cwd())
save_path = save_memory(document, metadata['category'], filename, brain_path)
print(f"Memory saved to: {save_path}")

# Update brain index
brain_updated = update_brain_index(str(brain_path), metadata, operation='add')
print(f"Brain index updated: {brain_updated}")

# Update cue network
cue_updated = update_cue_network(
    str(brain_path),
    category=metadata['category'],
    project=metadata.get('project'),
    keywords=metadata.get('keywords', []),
    memory_id=memory_id,
    operation='add'
)
print(f"Cue network updated: {cue_updated}")

# Output result
result = {
    'status': 'success',
    'memory': {
        'id': memory_id,
        'title': metadata['title'],
        'path': save_path,
        'category': metadata['category'],
        'project': metadata.get('project', ''),
        'keywords': metadata.get('keywords', []),
        'quality_score': metadata['quality_score'],
        'created_at': metadata['created_at']
    }
}
print(json.dumps(result, ensure_ascii=False, indent=2))
