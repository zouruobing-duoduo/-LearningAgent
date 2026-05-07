"""
学习大纲 - 由苏格拉底动态制定
大纲涵盖世界万物原理（物理、数学、化学、经济等），由 LLM 根据用户水平和学习历史动态生成。
大纲具有逻辑性和连续性：从基础思维方法出发，逐步深入各领域核心原理。
"""
import json
import os
import logging

import config
from core.llm import chat_json

logger = logging.getLogger(__name__)

# 大纲缓存文件
SYLLABUS_FILE = os.path.join(config.DATA_DIR, "syllabus.json")


def _load_syllabus() -> list[dict]:
    """从文件加载已生成的大纲"""
    if os.path.exists(SYLLABUS_FILE):
        try:
            with open(SYLLABUS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"加载大纲失败: {e}")
    return []


def _save_syllabus(syllabus: list[dict]):
    """保存大纲到文件"""
    try:
        with open(SYLLABUS_FILE, "w", encoding="utf-8") as f:
            json.dump(syllabus, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"保存大纲失败: {e}")


SYLLABUS_GENERATION_PROMPT = """你是苏格拉底，一位帮助用户掌握事物本质的智慧导师。
用户背景：智能驾驶领域研发人员，硕士，车辆工程，想掌握事物本质，形成底层逻辑架构。

请为用户制定一份学习大纲，要求：
1. 涵盖世界万物原理：包括思维方法、数学、统计学、物理、化学、经济学、生物学、人工智能等多个领域的核心原理
2. 由浅入深，有逻辑连续性：从基础思维方法 → 数理基础 → 各领域核心原理 → 跨领域融合
3. 每个知识点就是一个"原理"或"定律"或"核心概念"
4. 大约 30-40 个知识点

{learned_context}

请以 JSON 数组格式输出，每个元素：
{{
    "id": "编号如 t01, t02...",
    "name": "原理名称（简短有力，如'第一性原理'、'熵增定律'、'供需定律'）",
    "description": "一句话描述这个原理的核心",
    "category": "所属领域（思维方法/数学/统计学/物理/化学/生物/经济/哲学/人工智能/系统科学等）",
    "difficulty": 难度1-5
}}

只输出 JSON 数组，不要其他文字。"""


def generate_syllabus(learned_topics: list[str] = None) -> list[dict]:
    """
    让 LLM 生成学习大纲（有逻辑连续性）
    如果已有缓存大纲且未学完，直接返回缓存
    """
    # 检查缓存
    cached = _load_syllabus()
    if cached:
        return cached

    # 构建已学上下文
    learned_ctx = ""
    if learned_topics:
        learned_ctx = f"用户已学过以下知识点：{', '.join(learned_topics)}。请在此基础上继续规划，不要重复。"

    logger.info("正在生成学习大纲...")
    messages = [
        {"role": "system", "content": SYLLABUS_GENERATION_PROMPT.format(
            learned_context=learned_ctx
        )},
        {"role": "user", "content": "请为我制定学习大纲"},
    ]

    try:
        syllabus = chat_json(messages)
        if isinstance(syllabus, list) and len(syllabus) > 0:
            _save_syllabus(syllabus)
            logger.info(f"大纲生成成功，共 {len(syllabus)} 个知识点")
            return syllabus
    except Exception as e:
        logger.error(f"生成大纲失败: {e}")

    # 失败时返回基础默认大纲
    return _get_default_syllabus()


def _get_default_syllabus() -> list[dict]:
    """默认大纲（LLM 不可用时的兜底方案）"""
    default = [
        {"id": "t01", "name": "第一性原理", "description": "回归事物最基本的条件，从源头思考问题", "category": "思维方法", "difficulty": 1},
        {"id": "t02", "name": "熵增定律", "description": "孤立系统的熵只增不减，万物趋向无序", "category": "物理", "difficulty": 2},
        {"id": "t03", "name": "能量守恒定律", "description": "能量不会凭空产生或消失，只会转化", "category": "物理", "difficulty": 2},
        {"id": "t04", "name": "供需定律", "description": "价格由供给和需求的平衡决定", "category": "经济", "difficulty": 1},
        {"id": "t05", "name": "复利效应", "description": "微小的持续增长经过时间积累产生巨大变化", "category": "数学", "difficulty": 1},
        {"id": "t06", "name": "进化论（自然选择）", "description": "适者生存，物种通过变异和选择不断演化", "category": "生物", "difficulty": 2},
        {"id": "t07", "name": "牛顿三定律", "description": "描述物体运动规律的三条基本定律", "category": "物理", "difficulty": 2},
        {"id": "t08", "name": "概率与贝叶斯思维", "description": "用概率更新认知，理性决策的基础", "category": "数学", "difficulty": 3},
        {"id": "t09", "name": "大数定律", "description": "样本量足够大时，样本均值趋近于总体期望", "category": "统计学", "difficulty": 2},
        {"id": "t10", "name": "中心极限定理", "description": "大量独立随机变量之和趋向正态分布，统计推断的基石", "category": "统计学", "difficulty": 3},
        {"id": "t11", "name": "正态分布", "description": "自然界最普遍的分布，描述随机现象的钟形曲线", "category": "统计学", "difficulty": 2},
        {"id": "t12", "name": "回归分析", "description": "用数学模型描述变量间的因果或相关关系", "category": "统计学", "difficulty": 3},
        {"id": "t13", "name": "假设检验", "description": "用数据证据判断假设是否成立的科学方法", "category": "统计学", "difficulty": 3},
        {"id": "t14", "name": "方差与标准差", "description": "衡量数据离散程度，理解不确定性的核心工具", "category": "统计学", "difficulty": 2},
        {"id": "t15", "name": "神经网络与反向传播", "description": "模拟生物神经元的计算模型，通过梯度下降自动学习特征", "category": "人工智能", "difficulty": 3},
        {"id": "t16", "name": "梯度下降", "description": "沿损失函数梯度方向迭代优化参数，机器学习的核心优化方法", "category": "人工智能", "difficulty": 3},
        {"id": "t17", "name": "过拟合与正则化", "description": "模型过度记忆训练数据而丧失泛化能力，及其约束方法", "category": "人工智能", "difficulty": 2},
        {"id": "t18", "name": "Transformer与注意力机制", "description": "通过自注意力捕捉序列全局依赖，大语言模型的基础架构", "category": "人工智能", "difficulty": 4},
        {"id": "t19", "name": "强化学习", "description": "智能体通过与环境交互获得奖励信号来学习最优策略", "category": "人工智能", "difficulty": 4},
    ]
    _save_syllabus(default)
    return default


def get_syllabus() -> list[dict]:
    """获取当前大纲（优先缓存，否则生成）"""
    cached = _load_syllabus()
    if cached:
        return cached
    return generate_syllabus()


def get_topic_by_id(topic_id: str) -> dict | None:
    """根据 ID 获取知识点"""
    for topic in get_syllabus():
        if topic.get("id") == topic_id:
            return topic
    return None


def get_topic_by_name(name: str) -> dict | None:
    """根据名称模糊搜索知识点"""
    name_lower = name.lower()
    for topic in get_syllabus():
        tname = topic.get("name", "")
        tdesc = topic.get("description", "")
        if name_lower in tname.lower() or name_lower in tdesc.lower():
            return topic
    return None


def get_next_topic(learned_ids: list[str]) -> dict | None:
    """获取下一个未学习的知识点（按大纲顺序）"""
    for topic in get_syllabus():
        if topic.get("id") not in learned_ids:
            return topic
    return None


def get_all_topics() -> list[dict]:
    """获取所有知识点列表"""
    return get_syllabus()


def regenerate_syllabus(learned_topics: list[str] = None) -> list[dict]:
    """强制重新生成大纲（用户要求更新大纲时调用）"""
    # 删除缓存
    if os.path.exists(SYLLABUS_FILE):
        os.remove(SYLLABUS_FILE)
    return generate_syllabus(learned_topics)
