# Memory Skills

基于人脑记忆机制的项目级 AI 持久化记忆系统，目标是让 AI 在同一项目里「越用越懂你」。

## 核心能力

- 项目级隔离记忆：每个项目独立 `.memory/`，不混淆
- 触发即写入：每次触发记忆行为都写入，不只第一条
- 零散记忆池：小改动进入 `fragment_memory.md`，超限自动遗忘低价值并压缩
- 纠错经验库：错误/修复/纠正沉淀到 `lessons_learned.md`
- 偏好画像：`user_profile.md` 持续累积用户偏好
- 低 token 上下文：`context_pack.py` 输出限长记忆上下文
- 脑刷新闭环：`create_memory -> refresh_brain -> context_pack`

## 关键脚本

- `scripts/load_brain.py`：加载/初始化 `brain.md`
- `scripts/create_memory.py`：创建记忆（支持 quick/create/evaluate）
- `scripts/search_memory.py`：检索记忆（含 profile/lessons/fragment 辅助候选）
- `scripts/memory_extensions.py`：零散记忆与纠错记忆扩展
- `scripts/context_pack.py`：构建限长上下文包
- `scripts/session_summary.py`：会话总结写入 `user_profile.md`
- `scripts/refresh_brain.py`：写后刷新（会话总结 + 上下文包）

## 推荐执行顺序

1. 任务前加载上下文
```bash
python scripts/load_brain.py
python scripts/context_pack.py --max-chars 1400 --format text
```

2. 任务中写记忆
```bash
python scripts/create_memory.py \
  --category coding \
  --project my-project \
  --title "修复鉴权回归" \
  --content "..." \
  --mode quick
```

3. 任务后刷新大脑
```bash
python scripts/refresh_brain.py --max-chars 900 --format text
```

4. 会话结束总结（可选）
```bash
python scripts/session_summary.py --lookback-hours 8
```

## 默认配置在哪里

默认值统一定义在：

- `scripts/memory_defaults.py`（单一默认源）

项目运行时配置快照在：

- `.memory/brain.md` 的 `## ⚙️ 配置参数` 区块

## 默认参数（当前）

### 记忆管理
- `memory.max_per_category = 50`
- `memory.compression_threshold = 500`
- `memory.archive_after_days = 30`

### 线索网络
- `cue_network.max_keywords = 100`
- `cue_network.min_frequency = 2`
- `cue_network.decay_factor = 0.95`

### 遗忘参数
- `forgetting.half_life = 7`
- `forgetting.min_strength = 0.1`

### 扩展参数
- `fragment_memory.max_chars = 3000`
- `context_pack.max_chars = 1400`
- `refresh_brain.max_chars = 900`
- `session_summary.lookback_hours = 8`
- `session_summary.max_memories = 30`
- `session_summary.max_rows = 20`

## 目录结构（项目内）

```text
<project-root>/
└── .memory/
    ├── brain.md
    ├── user_profile.md
    ├── lessons_learned.md
    ├── fragment_memory.md
    ├── memories/
    │   ├── coding/
    │   ├── design/
    │   ├── config/
    │   ├── docs/
    │   ├── debug/
    │   └── other/
    └── archive/
```

## 设计原则

- 记忆优先：记忆既生命
- 触发即写：触发后不能跳过写入
- 用后刷新：写完必须刷新脑上下文
- 低占用：上下文包严格限长，避免挤占思考 token

