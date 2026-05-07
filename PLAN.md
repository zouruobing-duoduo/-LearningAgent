# 苏格拉底 - Multi-Agent 飞书学习机器人

## 一、Multi-Agent 架构设计

```
用户(飞书) <--消息--> 飞书长连接(WebSocket)
                          |
                    [Coordinator] ---- 意图识别 + 状态路由
                     /    |    \
                    /     |     \
         [Socrates] [Examiner] [ProgressTracker]
         诊断+教学   考核评估    进度跟踪(工具类)
              |
         [Librarian]
         知识提取+飞书知识库写入

         [记忆模块 Memory]
     短期记忆 | 长期记忆 | 向量数据库
    （对话上下文）（用户画像）（知识检索）
      ↑ 所有Agent共享读写 ↑
```


| Agent | 职责 | 输入 | 输出 |
|-------|------|------|------|
| Coordinator | 总协调器：意图识别、状态管理、路由分发 | 用户原始消息 + 系统状态 | 路由指令 + 状态变更 |
| Socrates | 苏格拉底式教学：诊断认知层次、追问启发教学 | 用户回答 + 学习上下文 + 二级大纲 | 启发式问题 / 知识讲解 + 子目录覆盖标记 |
| Examiner | 独立考核官：验证用户掌握程度，与教学角色分离 | 教学摘要 + 用户回答 | 考核评估结果 |
| Librarian | 知识管理：从对话提取结构化知识卡片 + 写入飞书知识库 | 对话历史 + 学习成果 | 知识卡片 + 知识库更新 |
| ProgressTracker | 学习进度跟踪 + 二级大纲管理 + 艾宾浩斯复习提醒 | 学习记录 + 子目录覆盖 | 进度报告 + 复习提醒 |
| **Memory** | **共享基础设施：短期对话上下文 + 长期用户画像 + 向量检索** | **对话历史/用户行为/知识内容** | **相关记忆检索结果** |

### 学习状态机

```
[IDLE] --开始学习--> [TEACHING]（已完成总体诊断后跳过单知识点诊断）
[IDLE] --首次/重新诊断--> [DIAGNOSING] --评估完成--> [IDLE]
[TEACHING] --所有子目录覆盖完成--> [EXAMINING]
[EXAMINING] --通过--> [IDLE]（记录掌握度 + 清空对话历史）
[EXAMINING] --未通过--> [TEACHING]（降低难度，补强薄弱点）
[任意学习状态] --放弃/跳过/不学了--> [IDLE]（不计入通过）
[任意学习状态] --"学习 xxx"--> [TEACHING]（切换知识点）
[任意状态] --"进度"--> 返回进度报告，不改变状态
[任意状态] --"复习"--> [TEACHING]（复习模式）
```

### 核心流程变更记录

- **诊断与教学分离**：诊断为一次性总体认知评估（结果存入用户画像），后续知识点直接进入教学
- **教学进度由大纲驱动**：每个知识点开始时 LLM 生成 4-8 个二级子目录，教学完成条件为所有子目录覆盖
- **对话上下文持久化**：last_bot_reply + last_user_message 持久化到文件，重启后注入对话历史保持连贯
- **消息去重持久化**：processed_message_ids 保存到 data/processed_messages.json，防止重启后重复处理

## 二、技术栈

- 语言：Python 3.12
- 飞书 SDK：lark-oapi（长连接模式，无需公网服务器）
- 大模型：DeepSeek API（deepseek-chat）
- 向量数据库：ChromaDB（本地嵌入式，无需额外服务）
- 数据存储：本地 JSON 文件（进度/状态/大纲/去重缓存）+ ChromaDB（向量检索）
- Agent 框架：原生 Python 实现（基于消息传递的 Agent 协作）

## 三、项目文件结构

```
LearningAgent/
  config.py                    # 全局配置
  main.py                      # 入口：启动飞书长连接 + 自动重启（指数退避）
  requirements.txt             # 依赖清单
  PLAN.md                      # 本文件

  agents/                      # Multi-Agent 核心
    base.py                    # Agent 基类（统一接口）
    coordinator.py             # 协调者：意图识别 + 状态机 + 路由 + 大纲生成 + 进度追踪
    socrates.py                # 苏格拉底：诊断 + 教学（含大纲注入 + 覆盖标记解析）
    examiner.py                # 考核官：独立考核评估
    librarian.py               # 图书管理员：知识提取 + 飞书知识库写入
    progress_tracker.py        # 进度跟踪 + 二级大纲管理 + 艾宾浩斯复习

  core/
    llm.py                     # DeepSeek API 封装
    state.py                   # 学习状态机 + AgentMessage + LearningContext（持久化）
    conversation.py            # 对话历史管理（每个Agent独立上下文）
    memory.py                  # 记忆模块（短期+长期+向量检索）

  feishu/
    client.py                  # 飞书客户端（长连接 + 消息收发 + 去重持久化）
    wiki.py                    # 飞书知识库 API 封装

  learning/
    syllabus.py                # 学习大纲（世界万物原理知识点列表）

  data/                        # 运行时数据（自动生成）
    progress.json              # 学习进度 + 复习计划 + 知识点统计 + 二级大纲
    syllabus.json              # 大纲缓存
    context_{user_id}.json     # 学习上下文（状态 + 当前知识点 + 最后一轮对话）
    processed_messages.json    # 消息去重缓存（持久化）
    conversations/             # 对话历史
    user_profile.json          # 用户画像（长期记忆）
    chroma_db/                 # ChromaDB 向量数据库存储

  .qoder/skills/               # Qoder Skill（自动化 SOP）
    deploy/SKILL.md            # 部署服务
    sync-wiki/SKILL.md         # 同步经验到飞书知识库
    add-topic/SKILL.md         # 添加知识点
```

## 四、核心设计

### 4.1 Agent 基类 (`agents/base.py`)

```python
class BaseAgent:
    name: str
    system_prompt: str

    def run(self, user_message, context) -> AgentResponse:
        """接收消息 -> 构建prompt -> 调用LLM -> 解析响应"""

    def build_system_prompt(self, context) -> str:
        """动态构建system prompt，注入上下文（如当前知识点、难度等级、二级大纲）"""

    def parse_response(self, reply, context) -> AgentResponse:
        """解析LLM回复，提取动作指令（子类实现）"""
```

### 4.2 Socrates Agent 设计要点

负责诊断 + 教学，考核由独立的 Examiner 承担：
- **诊断阶段**：一次性总体诊断，评估认知层次（1-5级），结果存入用户画像
- **教学阶段**：
  - 开始时注入二级大纲（4-8个子目录），Prompt 中标注覆盖状态（✅/○）
  - 每轮回复输出 `[COVERED:1,2]` 标记已覆盖的子目录
  - 所有子目录覆盖后输出 `[TEACHING_COMPLETE]`
- **教学内容要求**（9项）：
  1. 全局视角：先建立知识地图感
  2. 完整推理链条：假设→定义→推导→结论，不跳步
  3. 原理本质定义
  4. 数学公式与详细推导过程（逐步骤，标注每步依据）
  5. 核心定理与推论
  6. 跨界类比与连接（关联智能驾驶/车辆工程）
  7. 生动举例
  8. 深入拓展（因果链）
  9. 延续性提问保持上下文
- **5级教学策略**：每级有差异化的全局视角、推理链、公式、语言、节奏指引
- **节奏控制**：一问一答，每条回复最多一个问题

### 4.3 Examiner Agent 设计要点

独立考核官，与 Socrates 角色分离：
- 提出2-3个验证性场景题（非简单复述）
- 可结合智驾场景出题
- 每次只问一个问题，等用户回答后再出下一题
- 综合多轮问答评估掌握程度（1-5星）

### 4.4 学习流程控制

- **中止学习**：用户发"放弃/跳过/不学了/中止"→ 回到 IDLE，不计入通过
- **指定知识点**：用户发"学习 xxx"→ 模糊匹配大纲知识点
- **学习中切换**：正在学某知识点时发"学习 xxx"→ 直接切换

### 4.5 二级大纲与教学进度

```
开始学习知识点
    ↓
LLM 生成 4-8 个子目录（背景动机→核心概念→数学推导→应用→边界）
    ↓
每轮教学注入大纲状态 → Socrates 聚焦未覆盖子目录
    ↓
每轮回复解析 [COVERED:x,y] → 标记子目录已覆盖
    ↓
所有子目录覆盖 → 允许教学完成
```

进度指示（每轮回复末尾）：
```
─────────────
📊 Transformer与注意力机制 | 教学 3/6节 | 总进度 0/19
```

### 4.6 学习进度追踪（ProgressTracker）

**多层级进度**：
- 总体：已掌握/总数 + 百分比进度条
- 分领域：按类别（物理、统计学、AI 等）分组
- 知识点级：教学子目录覆盖数、考核次数、掌握度星级
- 4种状态：○ 未开始 / 📖 进行中 / △ 未完成 / ✅ 已掌握

**知识点统计**（topic_stats）：
- teaching_rounds：教学交互轮数
- exam_attempts：考核尝试次数
- outline：二级大纲及覆盖状态
- started_at：开始时间

### 4.7 艾宾浩斯复习机制

```
复习间隔：第1天 -> 第7天 -> 第16天 -> 第35天
根据掌握程度调整：
  掌握好 -> 延长间隔
  掌握差 -> 缩短间隔，重新进入教学
```

### 4.8 记忆模块设计 (`core/memory.py`)

记忆分三层，所有 Agent 共享读写：

**短期记忆**：当前会话的对话上下文，每个 Agent 独立历史

**长期记忆**：用户画像（认知层次、学习风格、强项弱项）

**向量记忆**：ChromaDB，知识点/对话片段的语义检索

### 4.9 服务稳定性

- **自动重启**：main.py 中 while True 循环 + 指数退避（5s→10s→20s→max 60s）
- **对话上下文恢复**：LearningContext 持久化 last_bot_reply / last_user_message，重启后注入对话历史
- **消息去重持久化**：processed_message_ids 保存到文件，防止重启后飞书重推旧消息导致重复回复

### 4.10 知识点大纲

当前覆盖领域：思维方法、物理、经济、数学、生物、统计学、人工智能

共 19 个知识点（t01-t19），通过 `/add-topic` Skill 可扩展。
添加知识点必须同时更新 `learning/syllabus.py`（代码默认大纲）和 `data/syllabus.json`（缓存文件）。

## 五、Skill 体系

| Skill | 触发方式 | 功能 |
|-------|---------|------|
| deploy | 代码修改后、用户说"部署/重启" | 停旧进程→启动 main.py→验证 WebSocket |
| sync-wiki | 经验更新后、用户说"同步知识库" | 检查新经验→运行 sync_to_wiki.py→验证 |
| add-topic | 用户说"添加知识点/补充原理" | 确认信息→编辑 syllabus.py + syllabus.json→部署 |

## 六、实施状态

### Phase 1：基础框架 ✅
- 飞书长连接、DeepSeek 封装、Agent 基类、状态机、对话管理、记忆模块

### Phase 2：Multi-Agent 核心 ✅
- Coordinator + Socrates + Examiner + ProgressTracker
- 完整学习流程：诊断→教学→考核→记录

### Phase 2.5：稳定性与流程增强 ✅
- 消息去重、会话超时管理
- 诊断与教学分离（一次性总体诊断）
- 5级教学策略、教学节奏控制（一问一答）
- 学习中止、指定知识点、学习中切换
- 自动重启 + 指数退避
- 对话上下文恢复（last_bot_reply 持久化）
- 消息去重缓存持久化
- 教学增强：全局视角、完整推理链条、公式详细推导
- 二级大纲驱动教学进度（子目录覆盖机制）
- 多层级学习进度可视化（每轮进度指示 + 完整进度报告）

### Phase 3：知识库集成 🔲
- Librarian Agent（知识提取 + 飞书知识库写入）

### Phase 4：增强优化 🔲
- 物理专家验证 Agent
- 艾宾浩斯定时推送复习提醒
- 学习报告生成（每周进度总结）
