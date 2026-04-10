---
name: memory-skills
description: |
  基于人脑记忆机制的项目级AI持久化记忆技能，模拟“左右脑”协同：分类记忆、零散记忆、纠错记忆、压缩与遗忘。
  目标是让加载本技能的AI「越用越懂你」，并在每次使用后回写和刷新记忆库。

  **核心特性**：每个项目有独立的项目级记忆存储，项目之间不混淆。

  **触发条件**（满足任一即调用）：
  - 关键词触发："记住"、"记忆"、"记一下"、"存一下"、"之前"、"上次"、"曾经"、"过去"、"之前的"、"以前的"、"历史的"、"过往的"、"之前做过"、"上次做的"、"过去的"、"之前遇到"、"之前解决"、"之前写的"、"之前实现"、"压缩记忆"、"整理记忆"、"清理记忆"、"精简记忆"
  - 操作触发："查找记忆"、"搜索记忆"、"压缩记忆"、"整理记忆"、"导出记忆"、"备份记忆"、"记忆统计"、"统计记忆"、"查看记忆"、"记忆导出"、"记忆备份"、"记忆搜索"、"记忆查找"、"执行压缩"、"压缩所有记忆"
  - 状态触发："加载大脑"、"查看记忆库"、"代码变更"、"追踪修改"、"自动记忆"、"记忆同步"、"同步记忆"
  - 上下文触发：涉及当前项目或指定项目的之前解决方案、设计方案、代码实现、历史错误、过往经验、历史记录、之前遇到的问题、之前的修复方案
  - **触发即写入**：一旦触发，必须写入记忆内容，最低限度写入`fragment_memory.md`零散记忆池，高价值内容创建独立记忆文件（默认使用快速写入模式）
  - **用后必刷新**：完成本次任务后，必须刷新大脑上下文，确保后续思考带着新记忆

  **排除条件**（不触发此技能）：
  - 简单的代码片段生成、数据格式化、翻译、计算等低价值操作：默认不创建独立记忆，自动进入零散记忆池临时存储，超限后自动遗忘
  - 跨项目记忆混淆的请求（技能会明确拒绝）

  **核心能力**：
  - 🏠 项目级隔离存储：每个项目独立记忆，不混淆
  - 📝 结构化记忆文档：YAML+Markdown格式
  - 🔍 智能语义检索：意图理解+多级匹配+中英文同义词扩展+语义相似度计算
  - 🗜️ LLM语义压缩：保留代码块和核心信息
  - 🧩 零散记忆池：小改动进入 `fragment_memory.md`，超限自动遗忘+压缩
  - 📚 纠错经验库：错误、修复、纠正沉淀到 `lessons_learned.md`，自动关联相似历史错误避免重复犯错
  - 🧠 类脑记忆系统：工作/情景/语义/程序四级存储
  - 📊 节点追踪：任务节点完成后自动记录
  - 📈 统计分析：实时统计记忆分布，支持JSON/HTML格式报告导出
  - 🔄 遗忘机制：冲突遗忘+时间遗忘+自主决策遗忘
  - 🔁 自动同步：记忆创建/删除自动同步索引，从源头避免统计不一致
  - ⚡ 降级兼容：Python不可用时LLM直接处理
  - 🧠 脑刷新闭环：`create_memory -> refresh_brain -> context_pack`

  **记忆优先级**：最高。记忆既生命。没有记忆，你不知道你是谁、你在做什么、你做过什么。
---


# Execution Contract (Critical)

Always treat this skill as **write-on-trigger**:

1. If the request triggers memory behavior, you must write a new memory entry for this turn.
2. Before reasoning, always load compact context first:
   `python scripts/context_pack.py --max-chars 1400 --format text`
3. Use `python scripts/create_memory.py --mode quick ...` as the default write path.
4. If using `--mode create` with LLM metadata, do not skip writes by default when `decision=no_memory`.
5. Only skip when the user explicitly requests no memory, or when `--respect-no-memory` is explicitly set.
6. Small low-value changes should be routed to `fragment_memory.md` automatically (default cap: 3000 chars).
7. Mistakes/corrections must be captured in `lessons_learned.md` to avoid repeating failures.
8. After each write, ensure profile accumulation is updated (via `user_profile.md`) so the assistant learns user preferences over time.
9. After memory write, refresh the brain context for next reasoning step:
   `python scripts/refresh_brain.py --max-chars 900 --format text`
10. At session end (or major milestone), persist session summary:
   `python scripts/session_summary.py --lookback-hours 8`

New supporting memory files:

- `fragment_memory.md`: scattered small changes (default max 3000 chars, auto-forget low-value notes first, then compress)
- `lessons_learned.md`: error/correction lessons to prevent repeated mistakes
- `user_profile.md`: evolving user preference profile
- `python scripts/refresh_brain.py --max-chars 900`: post-write refresh (optional session summary + compact context rebuild)
- `python scripts/session_summary.py --lookback-hours 8`: end-of-session preference digest

Fragment routing controls:

- default: small low-value notes route to `fragment_memory.md`
- force standalone memory: `python scripts/create_memory.py ... --disable-fragment-routing`
- change fragment cap: `python scripts/create_memory.py ... --fragment-max-chars 3000`

Default limits source:

- `scripts/memory_defaults.py` is the single source of default values.
- `brain.md` `## ⚙️ 配置参数` is the per-project runtime config snapshot.

# Memory Skills - 基于人脑记忆机制的AI记忆技能

## 🏠 架构：项目级隔离存储

**核心设计**：每个项目有独立的项目级记忆存储，项目之间不混淆。

```
项目A/
├── .memory/              # 项目A的记忆存储
│   ├── brain.md          # 项目级大脑
│   └── memories/         # 项目A的记忆
│       └── coding/
│           └── mem_xxx.md
└── src/

项目B/
├── .memory/              # 项目B的记忆存储（与项目A完全隔离）
│   ├── brain.md
│   └── memories/
│       └── design/
│           └── mem_yyy.md
└── src/
```

**规则**：
- ✅ 同一项目的记忆互相关联
- ✅ 不同项目的记忆完全隔离
- ✅ 跨项目检索需要显式指定
- ❌ 不会混淆不同项目的记忆

**检测当前项目**：按以下顺序检测项目根目录：
1. `.git` 存在 → 使用 Git 仓库根目录（最高优先）
2. `package.json` / `Cargo.toml` / `go.mod` 存在 → 使用项目根目录
3. 已存在 `.memory/brain.md` → 作为兼容回退使用
4. 使用当前工作目录

## ⚠️ 执行前必读

**🔴 强制第一步：检测并加载当前项目的大脑**

在执行任何任务之前，必须先检测项目并加载大脑状态：

```bash
# 检测当前项目
# 1. 向上查找 .git 所在目录（优先）
# 2. 或查找 package.json/Cargo.toml/go.mod 所在目录
# 3. 或回退到已存在的 .memory/brain.md 所在目录
# 4. 或使用当前工作目录

# 加载项目级大脑
python scripts/load_brain.py
```

如需显式指定项目根目录或brain路径：
```bash
python scripts/load_brain.py --project-root <项目根目录>
# 或
python scripts/load_brain.py --brain-path <brain.md路径>
```

**🔍 项目检测规则**：
1. 向上查找 `.git` → 使用 Git 仓库根目录（唯一存储根）
2. 向上查找项目配置文件 → 使用项目根目录
3. 仅在无 `.git/配置文件` 时，回退到 `.memory/brain.md`
4. 使用当前工作目录

**🧭 唯一存储约束**：
- 记忆只写入 `<项目根>/.memory/`，禁止写入技能目录或子目录的独立 `.memory/`
- 如果存在旧版 `<项目根>/brain.md` / `<项目根>/memories`，会自动迁移到 `<项目根>/.memory/`
- 如果存在子目录 shadow `.memory/`，会自动并入根 `.memory/` 并清理重复目录

**📁 项目级记忆结构**：
```
<项目根目录>/
├── .memory/                    # 项目记忆存储
│   ├── brain.md               # 项目级大脑索引
│   ├── memories/              # 项目记忆
│   │   ├── coding/
│   │   ├── design/
│   │   ├── config/
│   │   ├── docs/
│   │   ├── debug/
│   │   └── other/
│   └── archive/               # 归档记忆
└── <项目文件...>
```

**⚠️ Python 环境降级说明**

如果 Python 脚本执行失败（例如 `python: command not found`），技能将自动降级：
- LLM 直接读取/写入 brain.md 和记忆文件
- 保持相同的 YAML frontmatter 和 Markdown 格式
- 关键操作会添加注释说明变更内容
- 显示警告提示建议检查 Python 环境

**🔄 空大脑初始化**

如果 brain.md 处于初始状态（无记忆），技能将：
1. 创建 1-2 个示例记忆用于演示检索功能
2. 更新 brain.md 索引以反映这些记忆
3. 继续正常执行用户任务

**不执行此步骤将导致无法访问历史记忆！**

---

## ✅ 强制写入规则（解决“触发但不写入/只写第一条”）

**只要触发了本技能，必须写入记忆，且每次触发都要写入新记录。**

### 1) 默认使用快速写入（不依赖评估）
当触发条件满足时，**优先执行快速创建**：
```bash
python scripts/create_memory.py \
  --category <类别> \
  --project <项目> \
  --title <标题> \
  --content <内容> \
  --mode quick
```

### 2) 禁止“只写第一条”
- 同一会话中多次触发 → **逐条写入**，不得合并或跳过
- 不得以“已写过/重复/价值低”为理由阻止写入  

### 3) 允许最小化记忆，但不能不写
- 如果内容较短/价值难评估 → 仍写入（质量分可自动估算）
- 用户显式说“记住/记一下/存一下”时，**必须写入**

### 4) 只有两种情况可以完全不写
- 用户明确说“不要记录/不要记住/别存”
- 明确是排除条件（如单纯翻译/计算/格式化），且未触发任何记忆触发关键词
- ⚠️ 注意：只要触发了记忆技能，即便是低价值内容也会写入`fragment_memory.md`零散记忆池，不会完全丢失

### 5) 写入失败的兜底
- 若 Python 脚本失败，按降级流程由 LLM 直接写入 `.memory/brain.md` 和 `.memory/memories/<category>/`  
- 写入后 **必须更新索引表和关键词索引**

---

## 工作流程

### 🏗️ 新架构: LLM主导 + Python辅助

**核心原则**:
- **LLM负责**: 决策、理解、判断、语义处理
- **Python负责**: 文件操作、结构提取、数据准备、结果保存

```
┌─────────────┐
│  LLM思考层  │ ← 决策、理解、判断
└──────┬──────┘
       │
┌──────▼──────┐
│ Python执行层│ ← 文件操作、数据准备
└─────────────┘
```

---

### 阶段1：思考理解（左右脑并行）

#### 🧠 左脑：逻辑分析

执行以下分析：

1. **需求分解**：将用户需求拆解为具体任务
2. **类别判断**：确定记忆类别
   - `coding`：代码实现、算法、架构
   - `design`：UI设计、交互设计、视觉设计
   - `config`：配置文件、环境设置、部署配置
   - `docs`：文档编写、注释、说明
   - `debug`：问题排查、错误修复、调试
   - `other`：其他类型
3. **项目识别**：识别当前项目名称
4. **关键词提取**：提取3-5个核心关键词

#### 🎨 右脑：直觉感知

执行以下感知：

1. **模式识别**：识别是否与历史记忆相似
2. **价值预判**：预判记忆的价值和重要性
3. **线索联想**：联想相关的记忆线索

#### 🔄 空大脑初始化

**检查大脑状态**：在开始处理前，先检查 brain.md 是否包含任何记忆。

如果 brain.md 中 `总记忆数: 0`（初始状态）：

1. **创建示例记忆**：为用户创建一个与当前任务相关的示例记忆
2. **更新索引**：在 brain.md 的记忆索引表中添加新记忆条目
3. **继续处理**：使用新创建的示例记忆继续执行任务

**示例记忆模板**：
```markdown
---
id: mem_YYYYMMDD_XXXXXX_001
category: <推断的类别>
project: <当前项目或"general">
brain_dominant: left
keywords: [<关键词1>, <关键词2>, <关键词3>]
quality_score: 50
created_at: YYYY-MM-DDTHH:MM:SSZ
updated_at: YYYY-MM-DDTHH:MM:SSZ
access_count: 1
strength: 1.0
---

# <标题>

## 背景
<简要描述这是一个示例记忆>

## 需求
<用户当前的需求摘要>

## 解决方案
<基于用户需求的初步解决方案>

## 要点
- 这是一个示例记忆
- 后续可以替换或删除
```

**注意**：示例记忆的质量分数为 50（中等），确保不会长期保留。真实记忆创建后可以删除或替换。

### 阶段2：价值评估（LLM主导）

#### ⚠️ Python 降级工作流程

当 Python 脚本执行失败时，使用以下降级流程：

**创建记忆降级**：
```markdown
1. LLM 直接创建记忆文件（YAML + Markdown）
2. LLM 直接更新 brain.md 索引
3. 添加注释说明变更：`<!-- LLM直接更新: 时间戳 -->`
```

**检索记忆降级**：
```markdown
1. LLM 直接读取 brain.md 获取索引
2. LLM 直接读取候选记忆文件
3. LLM 进行相关性判断和排序
```

**压缩记忆降级**：
```markdown
1. LLM 直接读取源记忆文件
2. LLM 执行压缩逻辑（保留YAML、代码块、标题）
3. LLM 直接写入压缩后的文件
```

#### 步骤1: Python准备评估上下文

```bash
python scripts/create_memory.py \
  --category <类别> \
  --project <项目> \
  --title <标题> \
  --content <内容> \
  --mode evaluate
```

返回评估提示词给LLM。

#### 步骤2: LLM执行价值评估

基于提示词,LLM对记忆进行四维度评分：

| 维度 | 权重 | 评分标准 |
|------|------|----------|
| **复用性** | 40% | 是否可复用于其他场景？<br>高(80-100)：通用解决方案<br>中(50-79)：特定场景方案<br>低(0-49)：一次性操作 |
| **复杂度** | 30% | 解决方案的复杂程度<br>高(80-100)：复杂架构/算法<br>中(50-79)：中等复杂度<br>低(0-49)：简单操作 |
| **独特性** | 20% | 是否包含独特见解？<br>高(80-100)：创新方案<br>中(50-79)：改进方案<br>低(0-49)：常规方案 |
| **时效性** | 10% | 记忆的有效期<br>高(80-100)：长期有效<br>中(50-79)：中期有效<br>低(0-49)：短期有效 |

**综合评分公式**：
```
quality_score = 复用性×0.4 + 复杂度×0.3 + 独特性×0.2 + 时效性×0.1
```

**记忆决策**：
- `quality_score >= 70`：创建独立记忆文件
- `50 <= quality_score < 70`：压缩后创建独立记忆文件
- `quality_score < 50`：自动进入零散记忆池，写入`fragment_memory.md`，不创建独立记忆文件

### 阶段3：记忆操作（LLM主导）

#### 操作1：检索记忆（新流程）

**增强语义检索算法**：

LLM 执行智能语义检索，不仅仅依赖关键词匹配：

```
1. **意图理解**：分析用户查询的真实意图
2. **语义扩展**：将查询扩展为同义词、近义词、相关概念
3. **多级匹配**：
   - 精确匹配：ID、标题完全一致
   - 模糊匹配：标题、关键词部分匹配
   - 语义匹配：内容含义相似（LLM判断）
4. **相关性评分**：
   - 类别匹配：+40分
   - 项目匹配：+30分
   - 关键词匹配：每个+5分（上限20分）
   - 语义相似度：+10分（LLM判断）
5. **排序输出**：按相关性评分降序排列

总分 = 类别分 + 项目分 + 关键词分 + 语义分
返回相关性最高的5条记忆
```

**快速搜索命令**：
```bash
# 按关键词搜索
python scripts/search_memory.py --keywords "JWT,认证" --mode quick

# 按类别搜索
python scripts/search_memory.py --category coding --mode quick

# 列出所有记忆
python scripts/search_memory.py --list-all
```

**步骤1: Python准备检索上下文**

```bash
python scripts/search_memory.py \
  --category <类别> \
  --project <项目> \
  --keywords <关键词1,关键词2,关键词3> \
  --query-intent <查询意图> \
  --mode prepare
```

返回候选记忆列表和检索提示词。

**步骤2: LLM判断相关性**

LLM基于候选记忆:
1. 理解查询意图
2. 判断每条记忆的相关性
3. 计算语义相似度
4. 返回最相关的5条记忆

**步骤3: Python应用结果**

```bash
python scripts/search_memory.py --mode apply
```

从stdin读取LLM的检索结果并输出。

**向后兼容**: 使用 `--mode legacy` 可使用旧版硬编码评分。

#### 操作4：记忆导出

导出记忆为指定格式，便于分享或备份：

```bash
python scripts/export_memory.py \
  --memory <记忆ID或文件路径> \
  --format <json|markdown|text>
```

**导出格式选项**：
- `json`：结构化JSON，便于程序处理
- `markdown`：原始Markdown格式
- `text`：纯文本摘要

#### 操作5：记忆统计

查看记忆系统状态和统计信息：

```bash
python scripts/stats.py
```

**统计内容**：
- 总记忆数量（按类别分布）
- 总关键词数量
- 记忆活跃度排行
- 遗忘曲线状态
- 存储空间使用情况

#### 操作6：记忆同步

同步 brain.md 索引与实际记忆文件：

```bash
python scripts/sync_index.py
```

**功能**：
- 检测 brain.md 中记录的ID与实际文件是否一致
- 自动修复索引不一致问题
- 列出孤立的记忆文件
- 清理无效索引条目

#### 操作7：批量操作

批量压缩、删除、或导出多个记忆：

```bash
# 批量压缩（按类别）
python scripts/batch.py --action compress --category coding

# 批量删除（低质量记忆）
python scripts/batch.py --action delete --condition "quality_score < 30"

# 批量导出
python scripts/batch.py --action export --output ./backup/
```

#### 操作8：自动记忆追踪（开发者模式）

**核心能力**：自动追踪代码变更，无需LLM参与上下文

```bash
# 检查变更并决策是否记忆
python scripts/auto_memory.py --check

# 安装Git Hook（自动触发）
python scripts/auto_memory.py --install-hook

# 查看遗忘统计
python scripts/forget_memory.py --stats

# 检查遗忘候选（dry-run）
python scripts/forget_memory.py --check

# 执行遗忘
python scripts/forget_memory.py --check --execute
```

**自动记忆触发条件**：
- Git commit后自动分析diff
- 变更复杂度≥35分时创建记忆
- 新增文件、删除文件、接口修改自动高优先级

**遗忘机制**：
- **冲突遗忘**：同文件新变更覆盖旧记忆
- **时间遗忘**：超过30天未访问+强度<0.2自动归档
- **覆盖遗忘**：高质量新记忆替代低质量旧记忆

**Diff记忆格式**：
```markdown
---
id: diff_20260321_112812_001
type: code_change
parent: diff_20260320_005
complexity_score: 65
---

# 代码变更记忆

## 变更文件
| 文件 | 增加 | 删除 |
|------|------|------|
| src/auth.py | +23 | -5 |

## Diff
```diff
- import hashlib
+ import bcrypt
```

#### 操作9：类脑记忆系统（核心升级）

**核心设计**：模拟人类大脑的记忆机制，4种记忆类型分级存储

```
┌─────────────────────────────────────────────────────────────┐
│                      类脑记忆模型                             │
├─────────────────────────────────────────────────────────────┤
│  工作记忆     │ 短期活跃 │ 高频更新 │ 当前任务 │ → 遗忘    │
│  情景记忆     │ 中期存储 │ 中频更新 │ 任务记录 │ → 归档    │
│  语义记忆     │ 长期存储 │ 低频更新 │ 知识方案 │ → 固化    │
│  程序记忆     │ 永久存储 │ 极低频   │ 工作流程 │ → 强化    │
└─────────────────────────────────────────────────────────────┘
```

**记忆命令**：

```bash
# 创建工作记忆（任务开始时）
python scripts/session_memory.py create --task "用户认证模块" --goal "实现JWT登录" --nodes "设计数据库结构,实现登录API,添加注册功能"

# 更新工作记忆（节点完成时）
python scripts/session_memory.py update --id <work_id> --node "设计数据库结构" --result "完成：用户表、角色表设计"

# 追加变更记录
python scripts/session_memory.py change --id <work_id> --type "文件修改" --desc "修改了auth.py添加JWT验证"

# 整合为情景记忆（任务完成时）
python scripts/session_memory.py consolidate --id <work_id> --to episodic

# 升级为语义记忆（长期知识）
python scripts/session_memory.py consolidate --id <epis_id> --to semantic

# 遗忘检查
python scripts/session_memory.py forget-check --id <mem_id> --type episodic

# 查看状态
python scripts/session_memory.py status
```

**实时变更追踪**：

```bash
# 检查变更并创建记忆
python scripts/realtime_tracker.py --check --since "10 minutes ago"

# 监控模式
python scripts/realtime_tracker.py --watch
```

**会话结束偏好总结（新增）**：

```bash
# 会话结束时，汇总最近 8 小时偏好并写入 user_profile.md
python scripts/session_summary.py --lookback-hours 8

# 带一个会话标签，便于后续检索
python scripts/session_summary.py --lookback-hours 8 --session-label "auth-refactor"

# 只预览不写入
python scripts/session_summary.py --lookback-hours 8 --dry-run
```

**LLM自主决策**：

在以下时机，LLM应主动判断是否需要记忆：

| 时机 | LLM决策 | 行动 |
|------|---------|------|
| 节点完成 | 记住结果？ | 更新工作记忆 |
| 任务完成 | 整合为长期记忆？ | 整合到情景/语义记忆 |
| 长时间未访问 | 遗忘还是保留？ | 归档或强化 |
| 重复遇到相同问题 | 已成为固定模式？ | 升级为程序记忆 |

**记忆优先级**：记忆机制优先级最高。只有存在记忆，你才知道你是谁、你在做什么、你做过什么。

#### 操作2：压缩记忆（新流程）

**用户指令触发方式**：
当用户说"压缩记忆"、"整理记忆"、"清理记忆"、"精简记忆"、"执行压缩"、"压缩所有记忆"时，自动执行记忆压缩操作。

**压缩命令**：
```bash
# 压缩指定记忆
python scripts/compress.py \
  --memory <记忆文件路径或ID> \
  --mode [prepare|apply|legacy]

# 批量压缩所有低质量记忆（quality_score < 50）
python scripts/compress.py --batch --quality-threshold 50

# 压缩指定类别的记忆
python scripts/compress.py --batch --category coding

# 快捷压缩所有记忆
python scripts/compress.py --all
```

**步骤1: Python准备压缩上下文**
```bash
python scripts/compress.py \
  --memory <记忆文件路径> \
  --mode prepare
```
返回记忆结构分析和压缩提示词。

**步骤2: LLM执行压缩**
LLM基于分析结果:
1. 判断哪些段落包含核心信息
2. 识别可压缩的描述性内容
3. 保留所有代码块和标题结构
4. 生成压缩后的markdown

**步骤3: Python应用压缩结果**
```bash
python scripts/compress.py \
  --memory <记忆文件路径> \
  --mode apply
```
从stdin读取LLM的压缩结果并保存。

**压缩策略**：
1. 完整保留YAML前置元数据
2. 完整保留所有标题结构
3. 完整保留所有代码块
4. 压缩描述性段落为摘要（保留首句+关键信息）
5. 删除过渡语句和重复内容
6. 标记压缩区域：`<!-- 压缩摘要 -->`

压缩后约为原长度的1/3。

**向后兼容**: 使用 `--mode legacy` 可使用旧版机械压缩。

#### 操作3：创建记忆（新流程）

**✅ 推荐：快速创建（无需LLM评估，确保写入成功）**

```bash
python scripts/create_memory.py \
  --category <类别> \
  --project <项目> \
  --title <标题> \
  --content <内容> \
  --mode quick
```

说明：
- 自动检测项目根目录并定位 `.memory/brain.md`
- 自动补全关键词、质量评分、脑主导等字段
- 适用于「触发了但未写入」的兜底写入场景
- 用户明确说“记住/记一下/存一下”时必须使用该方式写入

**步骤1: Python准备创建上下文**

```bash
python scripts/create_memory.py \
  --category <类别> \
  --project <项目> \
  --title <标题> \
  --content <内容> \
  --mode prepare
```

返回评估和关键词提取提示词。

**步骤2: LLM评估和提取**

LLM执行:
1. 价值评估（四维度评分）
2. 关键词提取（3-5个核心关键词）
3. 返回完整元数据JSON

**步骤3: Python创建记忆**

```bash
python scripts/create_memory.py \
  --metadata '<LLM返回的JSON>' \
  --content <内容> \
  --mode create
```

**强制写入（忽略 no_memory）**
```bash
python scripts/create_memory.py \
  --metadata '<LLM返回的JSON>' \
  --content <内容> \
  --mode create \
  --force-write
```

这会：
1. 生成唯一记忆ID：`mem_YYYYMMDD_HHMMSS_序号`
2. 创建记忆文档（YAML前置+正文）
3. 保存到对应类别目录
4. 更新 `brain.md` 索引
5. 更新线索网络

---

## 记忆文档格式

每个记忆文档遵循以下格式：

```markdown
---
id: mem_20250319_001
title: 标题
category: coding
project: my-project
brain_dominant: left
keywords: [关键词1, 关键词2, 关键3]
quality_score: 85
created_at: 2025-03-19T10:30:00Z
updated_at: 2025-03-19T10:30:00Z
access_count: 1
strength: 1.0
---

# 标题

## 背景
<需求背景描述>

## 需求
<具体需求说明>

## 思考过程

### 左脑分析
<逻辑分析结果>

### 右脑感知
<直觉感知结果>

## 解决方案
<具体实现方案>

## 要点
<关键要点总结>
```

---

## 线索网络

线索网络是记忆检索的核心，包含三个维度：

### 1. 类别索引

| 类别 | 数量 | 脑主导 |
|------|------|--------|
| coding | N | 左脑 |
| design | N | 右脑 |
| config | N | 左脑 |
| docs | N | 右脑 |
| debug | N | 左脑 |
| other | N | 右脑 |

### 2. 项目索引

记录每个项目的记忆数量和最后活跃时间。

### 3. 关键词索引

记录高频关键词及其出现频率，用于快速检索。

---

## 配置参数

在 `brain.md` 中可配置以下参数（默认值来源：`scripts/memory_defaults.py`）：

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

补充默认参数（脚本级）：
- `fragment_memory.md` 最大长度：`3000` 字符
- `context_pack.py --max-chars` 默认：`1400`
- `refresh_brain.py --max-chars` 默认：`900`
- `session_summary.py --lookback-hours` 默认：`8`

---

## 遗忘机制

记忆强度会随时间衰减，遵循艾宾浩斯遗忘曲线：

```
R = e^(-t/S)
```

其中：
- R = 记忆保留率
- t = 距上次访问的天数
- S = 记忆稳定性 = quality_score / 10

**遗忘处理**：
- `strength >= 0.3`：正常保留
- `0.1 <= strength < 0.3`：标记为"待压缩"
- `strength < 0.1`：归档到 `archive/`

---

## 使用示例

### 示例1：创建编码记忆（新流程）

```bash
# 1. 加载大脑
python scripts/load_brain.py

# 2. 准备创建上下文
python scripts/create_memory.py \
  --category coding \
  --project memory-skills \
  --title "记忆压缩机制实现" \
  --content "..." \
  --mode prepare

# 3. LLM评估和提取关键词(处理返回的提示词)

# 4. 创建记忆
python scripts/create_memory.py \
  --metadata '{"id":"...", "category":"coding", ...}' \
  --mode create
```

### 示例2：检索历史记忆（新流程）

```bash
# 1. 准备检索上下文
python scripts/search_memory.py \
  --category coding \
  --keywords "压缩,遗忘" \
  --query-intent "查找记忆压缩相关实现" \
  --mode prepare

# 2. LLM判断相关性(处理返回的提示词)

# 3. 应用检索结果
python scripts/search_memory.py --mode apply
```

### 示例3：压缩旧记忆（新流程）

```bash
# 1. 准备压缩上下文
python scripts/compress.py \
  --memory memories/coding/20250301_old.md \
  --mode prepare

# 2. LLM执行压缩(处理返回的提示词)

# 3. 应用压缩结果
python scripts/compress.py \
  --memory memories/coding/20250301_old.md \
  --mode apply
```

### 向后兼容示例

```bash
# 使用旧版硬编码评分检索
python scripts/search_memory.py \
  --category coding \
  --keywords "压缩,遗忘" \
  --mode legacy

# 使用旧版机械压缩
python scripts/compress.py \
  --memory .memory/memories/coding/20250301_old.md \
  --mode legacy
```

---

## 注意事项

1. **强制加载大脑**：每次会话开始必须先检测项目并加载 `brain.md`
2. **项目级隔离**：每个项目有独立的 `.memory/` 目录，记忆不混淆
3. **LLM主导决策**：压缩、检索、价值评估等需要理解的任务由LLM处理
4. **Python辅助执行**：文件操作、结构提取、数据准备由Python处理
5. **评分要客观**：价值评估要基于实际复用价值，不要过度评分
6. **关键词要准确**：关键词直接影响检索效果，选择最具代表性的词
7. **定期压缩**：当记忆数量接近上限时，主动压缩低价值记忆
8. **保持索引一致**：不要手动修改 `brain.md`，使用脚本操作
9. **向后兼容**：所有脚本都支持 `--mode legacy` 使用旧版方法
10. **环境降级**：Python不可用时自动降级，LLM直接处理文件
11. **空大脑处理**：brain.md为空时自动创建示例记忆
12. **新功能**：支持记忆导出(`export`)、统计(`stats`)、同步(`sync`)、批量操作(`batch`)
13. **跨项目需显式**：跨项目检索必须显式指定目标项目
14. **触发即写**：触发技能后必须写入记忆（推荐 `--mode quick`）
15. **逐条写入**：同一会话多次触发必须逐条写入，不得合并/跳过
16. **强制写入**：若评估返回 `no_memory`，但用户明确触发，则必须用 `--force-write`

---

## 架构优势

### 相比旧架构的改进

| 方面 | 旧架构 | 新架构 |
|------|--------|--------|
| **压缩** | Python机械截取 | LLM语义理解压缩 |
| **检索** | 硬编码评分规则 | LLM判断相关性 |
| **关键词** | 未实现 | LLM智能提取 |
| **价值评估** | 手动评分 | LLM四维度评估 |
| **Python角色** | 决策+执行 | 仅数据准备+执行 |
| **LLM角色** | 调用脚本 | 思考+决策 |

### 核心优势

1. **语义理解**: LLM能理解内容含义,而非机械处理
2. **智能决策**: 压缩、检索决策基于实际理解
3. **职责清晰**: LLM思考,Python执行,各司其职
4. **向后兼容**: 保留旧版方法,平滑过渡
5. **可扩展性**: 提示词模板化,易于优化
