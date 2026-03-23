# Memory Skills 使用示例

本文档提供Memory Skills的完整使用示例和常见问题解答。

## 快速开始

### 1. 初始化大脑

首次使用时，需要初始化大脑：

```bash
cd memory-skills
python scripts/load_brain.py
```

输出示例：
```json
{
  "status": "success",
  "brain": {
    "version": "1.0",
    "memory_count": 0,
    "category_count": 6,
    "project_count": 0,
    "last_updated": "2025-03-19"
  },
  "recent_memories": [],
  "cue_network": {
    "categories": ["coding", "design", "config", "docs", "debug", "other"],
    "projects": [],
    "top_keywords": []
  }
}
```

### 2. 创建第一个记忆

```bash
python scripts/create_memory.py \
  --category coding \
  --project memory-skills \
  --keywords "记忆,压缩,遗忘" \
  --title "记忆压缩机制实现" \
  --brain-dominant left \
  --quality-score 85
```

输入内容（从stdin）：
```
# 记忆压缩机制实现

## 背景
需要实现一个智能压缩机制，将长记忆压缩为简洁摘要。

## 需求
- 保留核心信息（标题、代码块、结论）
- 压缩描述性内容
- 压缩后约为原长度的1/3

## 解决方案
使用正则表达式解析Markdown结构，保留关键元素，压缩段落。

## 要点
- YAML元数据完整保留
- 代码块完整保留
- 段落压缩为摘要
```

输出示例：
```json
{
  "status": "success",
  "memory": {
    "id": "mem_20250319_143000_001",
    "title": "记忆压缩机制实现",
    "path": ".memory/memories/coding/mem_20250319_143000_001.md",
    "category": "coding",
    "project": "memory-skills",
    "keywords": ["记忆", "压缩", "遗忘"],
    "brain_dominant": "left",
    "quality_score": 85,
    "created_at": "2025-03-19T14:30:00Z"
  },
  "brain_updated": true,
  "cue_network_updated": true
}
```

### 3. 检索记忆

```bash
python scripts/search_memory.py \
  --category coding \
  --keywords "压缩,遗忘"
```

输出示例：
```json
{
  "status": "success",
  "query": {
    "category": "coding",
    "project": null,
    "keywords": ["压缩", "遗忘"]
  },
  "results": [
    {
      "id": "mem_20250319_143000_001",
      "title": "记忆压缩机制实现",
      "path": ".memory/memories/coding/mem_20250319_143000_001.md",
      "category": "coding",
      "project": "memory-skills",
      "match_score": 60,
      "match_details": {
        "category_match": 40,
        "project_match": 0,
        "keyword_match": 20,
        "semantic_match": 0,
        "total_score": 60
      },
      "summary": "需要实现一个智能压缩机制，将长记忆压缩为简洁摘要...",
      "quality_score": 85
    }
  ],
  "total_count": 1
}
```

### 4. 压缩记忆

当记忆过长时，可以压缩：

```bash
python scripts/compress.py \
  --memory .memory/memories/coding/20250301_old.md
```

输出示例：
```json
{
  "status": "success",
  "compression": {
    "original_length": 3000,
    "compressed_length": 1000,
    "compression_ratio": 0.33,
    "space_info": {
      "current_length": 3000,
      "compressed_length": 1000,
      "new_content_length": 0,
      "has_space": true,
      "can_compress": true
    }
  },
  "archive": {
    "archived": true,
    "archive_path": "archive/20250301_old_20250319_143000.md"
  },
  "output_path": ".memory/memories/coding/20250301_old.md"
}
```

## 完整工作流程示例

### 场景：开发用户认证功能

#### 步骤1：加载大脑

```bash
python scripts/load_brain.py
```

#### 步骤2：检索相关记忆

```bash
python scripts/search_memory.py \
  --category coding \
  --project web-app \
  --keywords "认证,JWT,登录"
```

#### 步骤3：创建新记忆

```bash
python scripts/create_memory.py \
  --category coding \
  --project web-app \
  --keywords "认证,JWT,登录,安全" \
  --title "用户认证功能实现" \
  --brain-dominant left \
  --quality-score 90
```

输入内容：
```
# 用户认证功能实现

## 背景
需要为web-app项目实现用户认证功能，支持JWT令牌。

## 需求
- 用户登录/注册
- JWT令牌生成和验证
- 密码加密存储
- 会话管理

## 思考过程

### 左脑分析
1. 选择JWT作为认证方案
2. 使用bcrypt加密密码
3. 实现中间件验证令牌

### 右脑感知
- 需要考虑安全性
- 用户体验要流畅
- 错误处理要友好

## 解决方案

### 代码实现
```python
import jwt
from datetime import datetime, timedelta
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm="HS256")
    return encoded_jwt

def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=["HS256"])
        return payload
    except jwt.ExpiredSignatureError:
        return None
```

## 要点
- JWT过期时间设置为24小时
- 密码使用bcrypt加密
- 令牌存储在HTTP-only Cookie中
```

#### 步骤4：验证记忆已创建

```bash
python scripts/search_memory.py \
  --category coding \
  --project web-app
```

## 常见问题

### Q1: 如何判断是否需要创建记忆？

使用价值评估标准：
- 复用性（40%）：是否可复用于其他场景？
- 复杂度（30%）：解决方案的复杂程度？
- 独特性（20%）：是否包含独特见解？
- 时效性（10%）：记忆的有效期？

综合评分 >= 70：创建新记忆
50 <= 评分 < 70：压缩后创建
评分 < 50：不创建记忆

### Q2: 如何选择记忆类别？

- `coding`：代码实现、算法、架构
- `design`：UI设计、交互设计、视觉设计
- `config`：配置文件、环境设置、部署配置
- `docs`：文档编写、注释、说明
- `debug`：问题排查、错误修复、调试
- `other`：其他类型

### Q3: 如何选择脑主导？

- `left`：逻辑分析、算法实现、技术方案
- `right`：直觉感知、设计创意、用户体验
- `both`：综合思考、平衡决策

### Q4: 记忆太多怎么办？

1. 使用压缩功能压缩旧记忆
2. 系统会自动归档强度低于0.1的记忆
3. 定期清理低质量记忆

### Q5: 如何更新已有记忆？

1. 使用 `compress.py` 压缩旧记忆
2. 创建新记忆补充新信息
3. 或手动编辑记忆文件，然后更新brain.md索引

### Q6: 线索网络如何工作？

线索网络包含三个维度：
- 类别索引：按类别组织记忆
- 项目索引：按项目组织记忆
- 关键词索引：按关键词组织记忆

检索时会综合匹配三个维度，计算匹配度评分。

### Q7: 遗忘机制如何工作？

记忆强度会随时间衰减：
```
R = e^(-t/S)
```
- R = 记忆保留率
- t = 距上次访问的天数
- S = 记忆稳定性 = quality_score / 10

强度 >= 0.3：正常保留
0.1 <= 强度 < 0.3：标记为"待压缩"
强度 < 0.1：归档到 archive/

## 配置参数说明

在 `brain.md` 中可配置：

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

## 最佳实践

1. **每次会话开始先加载大脑**
   ```bash
   python scripts/load_brain.py
   ```

2. **创建记忆前先检索**
   ```bash
   python scripts/search_memory.py --category <类别> --keywords <关键词>
   ```

3. **客观评估记忆价值**
   - 不要过度评分
   - 基于实际复用价值

4. **关键词要准确**
   - 选择最具代表性的词
   - 3-5个关键词最佳

5. **定期维护**
   - 压缩低价值记忆
   - 归档过期记忆
   - 更新线索网络

## 故障排除

### 问题：brain.md文件损坏

解决方案：
1. 备份现有brain.md
2. 删除brain.md
3. 重新运行 `load_brain.py` 初始化
4. 手动恢复重要记忆索引

### 问题：记忆文件找不到

解决方案：
1. 检查brain.md中的路径是否正确
2. 检查文件是否被移动或删除
3. 使用 `search_memory.py` 重新检索

### 问题：编码错误

解决方案：
1. 确保所有文件使用UTF-8编码
2. 脚本会自动尝试GBK编码
3. 手动转换文件编码

## 进阶用法

### 批量创建记忆

```bash
for file in memories/*.md; do
  python scripts/create_memory.py \
    --category other \
    --title "$(basename $file .md)" \
    --content "$(cat $file)"
done
```

### 导出记忆索引

```bash
python scripts/load_brain.py | jq '.brain' > brain_status.json
```

### 搜索特定项目的所有记忆

```bash
python scripts/search_memory.py --project my-project
```
