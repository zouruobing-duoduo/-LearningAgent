"""
协调者 Agent - 总调度中心
负责意图识别、状态管理、Agent 路由分发
"""
import logging
import os

from core.llm import chat_json
from core.state import (
    AgentResponse, Action, LearningContext, LearningState, AgentMessage,
)
from core.conversation import ConversationManager
from core.memory import Memory
from agents.socrates import SocratesAgent
from agents.examiner import ExaminerAgent
from agents.progress_tracker import ProgressTracker
from learning.syllabus import get_next_topic, get_topic_by_name, get_syllabus

logger = logging.getLogger(__name__)

INTENT_PROMPT = """你是一个意图识别器。根据用户消息和当前学习状态，判断用户意图。

当前状态: {state}
当前知识点: {topic}

用户消息: "{message}"

请以JSON格式输出：
{{
    "intent": "意图类型",
    "topic": "如果用户明确指定了要学习的知识点名称，填写，否则为null"
}}

可选的 intent 值：
- "start_learning": 用户明确想开始学习某个原理（如"开始学习"、"学习牛顿第三定律"、"我准备好了"）
- "start_diagnosis": 用户想重新诊断（如"重新诊断"、"重新评估"）
- "show_progress": 用户查看进度（如"进度"、"学了哪些"）
- "review": 用户想复习（如"复习"、"回顾"）
- "next_topic": 用户想学下一个知识点
- "help": 用户需要帮助（如"帮助"、"怎么用"）
- "chat": 闲聊或无法归类的其他内容

重要判断规则：
- 只有用户明确表达"我要学习xxx""开始学习xxx"时才用 start_learning
- 像"我不清楚""你来说下""还有其他例子吗""你来决策"这类对话性消息，都是 chat
- 不要把用户随口说的短语误判为 start_learning"""


HELP_TEXT = """🏛️ 我是苏格拉底，你的个性化学习伙伴。

📖 使用方式：
  • 发送「开始学习」- 开始学习下一个原理
  • 发送「学习 xxx」- 指定学习某个原理（学习中也可切换）
  • 发送「放弃」- 中止当前学习（不计入通过）
  • 发送「进度」- 查看学习进度
  • 发送「复习」- 复习已学内容
  • 发送「下一个」- 跳到下一个原理
  • 发送「更新大纲」- 重新生成学习大纲
  • 发送「重新诊断」- 重新评估你的认知水平

💡 学习流程：总体诊断（仅一次）→ 报原理名词 → 教学 → 考核 → 知识固化
每个阶段我都会通过提问引导你思考，而不是直接灌输答案。
学习过程中随时可以发「放弃」中止，或发「学习 xxx」切换到其他知识点。"""


class Coordinator:
    """
    协调者 - Multi-Agent 总调度中心
    不继承 BaseAgent，因为它不直接与 LLM 对话
    """

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self.conversation = ConversationManager(user_id)
        self.memory = Memory(self.conversation, user_id)

        # 从文件恢复学习上下文（重启后不丢失状态）
        import config
        context_file = os.path.join(config.DATA_DIR, f"context_{user_id}.json")
        self.context = LearningContext.load(context_file)

        # 初始化各 Agent（共享 conversation 和 memory）
        self.progress_tracker = ProgressTracker(self.conversation, self.memory)
        self.socrates = SocratesAgent(self.conversation, self.memory, self.progress_tracker)
        self.examiner = ExaminerAgent(self.conversation, self.memory)

        # 重启后恢复对话上下文：把最后一轮对话注入对话历史
        self._restore_conversation_context()

    def _restore_conversation_context(self):
        """重启后恢复对话上下文：将持久化的最后一轮对话注入内存"""
        if self.context.state == LearningState.IDLE:
            return
        # 根据当前状态确定应该恢复到哪个 Agent
        if self.context.state in (LearningState.DIAGNOSING, LearningState.TEACHING):
            agent_name = "socrates"
        elif self.context.state == LearningState.EXAMINING:
            agent_name = "examiner"
        else:
            return

        # 只有对话历史为空时才需要恢复（避免重复注入）
        if self.conversation.get_history(agent_name):
            return

        restored = False
        if self.context.last_user_message:
            self.conversation.add_message(agent_name, "user", self.context.last_user_message)
            restored = True
        if self.context.last_bot_reply:
            # 剥离可能残留的进度指示行，避免注入后重复
            clean = self.context.last_bot_reply.split("\n\n─────────────\n")[0] if "─────────────" in self.context.last_bot_reply else self.context.last_bot_reply
            self.conversation.add_message(agent_name, "assistant", clean)
            restored = True
        if restored:
            logger.info(f"已恢复{agent_name}的对话上下文（最后一轮）")

    def handle_message(self, text: str) -> str:
        """
        消息处理入口 - 路由到对应 Agent

        Args:
            text: 用户发送的消息

        Returns:
            回复文本
        """
        try:
            logger.info(f"当前状态: {self.context.state.value}, topic={self.context.current_topic}")

            # 优先检查中止指令（无论什么状态都可以中止）
            if self._is_abort_command(text):
                reply = self._abort_learning()
                self._save_last_round(text, reply)
                return reply

            # 学习中切换知识点：用户发"学习 xxx"直接切换到新知识点
            if self.context.state != LearningState.IDLE:
                switch_topic = self._extract_topic_switch(text)
                if switch_topic:
                    logger.info(f"学习中切换知识点: {self.context.current_topic} → {switch_topic}")
                    reply = self._start_learning(switch_topic)
                    self._save_last_round(text, reply)
                    return reply

            # 如果正在学习流程中，直接转发给当前 Agent
            if self.context.state != LearningState.IDLE:
                reply = self._route_to_current_agent(text)
                reply += self._compact_progress_line()
                self._save_last_round(text, reply)
                return reply

            # 安全网：如果状态是 IDLE 但有未完成的知识点，且用户消息不像指令，
            # 则认为是继续当前话题的对话（而不是重新开始）
            if self.context.current_topic and not self._is_command(text):
                logger.info(f"状态为IDLE但有未完成topic={self.context.current_topic}，继续当前话题")
                self.context.state = LearningState.TEACHING
                self.context.save()
                reply = self._route_to_current_agent(text)
                reply += self._compact_progress_line()
                self._save_last_round(text, reply)
                return reply

            # 空闲状态：先识别意图
            intent_result = self._detect_intent(text)
            intent = intent_result.get("intent", "chat")
            specified_topic = intent_result.get("topic")

            logger.info(f"识别意图: {intent}, topic={specified_topic}")

            if intent == "start_learning":
                reply = self._start_learning(specified_topic)
            elif intent == "start_diagnosis":
                reply = self._start_diagnosis()
            elif intent == "show_progress":
                reply = self.progress_tracker.get_progress_report(
                    current_topic=self.context.current_topic,
                    current_state=self.context.state.value if self.context.state else None,
                )
            elif intent == "review":
                reply = self._start_review()
            elif intent == "next_topic":
                reply = self._start_learning(None)
            elif intent == "help":
                reply = HELP_TEXT
            elif intent == "regenerate_syllabus":
                reply = self._regenerate_syllabus()
            else:
                reply = self._casual_chat(text)

            self._save_last_round(text, reply)
            return reply

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)
            return f"抱歉，我暂时遇到了一些问题：{str(e)}"

    def _save_last_round(self, user_message: str, bot_reply: str):
        """保存最后一轮对话（持久化，重启后可恢复上下文）"""
        # 剥离进度指示行再保存，避免重启恢复后重复
        clean_reply = bot_reply.split("\n\n─────────────\n")[0] if "─────────────" in bot_reply else bot_reply
        self.context.last_user_message = user_message
        self.context.last_bot_reply = clean_reply
        self.context.save()

    def _compact_progress_line(self) -> str:
        """生成紧凑的单行进度指示（仅在学习流程中显示）"""
        from learning.syllabus import get_topic_by_name, get_syllabus

        state = self.context.state
        topic = self.context.current_topic
        if not topic or state == LearningState.IDLE:
            return ""

        # 总进度
        syllabus = get_syllabus()
        total = len(syllabus)
        learned_count = len(self.progress_tracker.get_learned_topic_ids())

        # 当前知识点统计
        topic_info = get_topic_by_name(topic)
        tid = topic_info["id"] if topic_info else ""
        stats = self.progress_tracker.get_topic_stats(tid)
        outline = self.progress_tracker.get_topic_outline(tid)

        parts = [f"📊 {topic}"]
        if state.value == "teaching":
            if outline:
                covered = sum(1 for item in outline if item.get("covered"))
                parts.append(f"教学 {covered}/{len(outline)}节")
            else:
                teaching_rounds = stats.get("teaching_rounds", 0)
                parts.append(f"教学第{teaching_rounds}轮")
        elif state.value == "examining":
            exam_attempts = stats.get("exam_attempts", 0)
            EXAM_TOTAL = 3
            parts.append(f"考核 {exam_attempts}/{EXAM_TOTAL}题")
        elif state.value == "diagnosing":
            parts.append("诊断中")
        parts.append(f"总进度 {learned_count}/{total}")
        return "\n\n─────────────\n" + " | ".join(parts)

    def _detect_intent(self, text: str) -> dict:
        """意图识别"""
        # 简单关键词匹配（快速路径，避免不必要的 LLM 调用）
        text_lower = text.strip().lower()
        if text_lower in ("开始学习", "开始", "学习", "我准备好了"):
            return {"intent": "start_learning", "topic": None}
        if text_lower in ("重新诊断", "重新评估", "诊断"):
            return {"intent": "start_diagnosis", "topic": None}
        if text_lower in ("进度", "学习进度", "查看进度"):
            return {"intent": "show_progress", "topic": None}
        if text_lower in ("复习", "回顾", "我要复习"):
            return {"intent": "review", "topic": None}
        if text_lower in ("下一个", "下一个知识点", "继续"):
            return {"intent": "next_topic", "topic": None}
        if text_lower in ("帮助", "help", "怎么用"):
            return {"intent": "help", "topic": None}
        if text_lower in ("更新大纲", "重新大纲", "刷新大纲"):
            return {"intent": "regenerate_syllabus", "topic": None}
        if text_lower.startswith("学习 ") or text_lower.startswith("学习"):
            topic_name = text.strip()[2:].strip()
            if topic_name:
                return {"intent": "start_learning", "topic": topic_name}

        # 复杂意图用 LLM 识别
        try:
            messages = [
                {"role": "system", "content": INTENT_PROMPT.format(
                    state=self.context.state.value,
                    topic=self.context.current_topic or "无",
                    message=text,
                )},
                {"role": "user", "content": text},
            ]
            return chat_json(messages)
        except Exception as e:
            logger.error(f"意图识别失败: {e}")
            return {"intent": "chat", "topic": None}

    def _is_diagnosed(self) -> bool:
        """检查是否已完成总体诊断"""
        return self.memory.long_term.cognitive_level > 0

    def _start_diagnosis(self) -> str:
        """启动总体认知诊断（一次性）"""
        self.context.state = LearningState.DIAGNOSING
        self.context.current_topic = None
        self.context.save()
        self.socrates.clear_history()
        logger.info("开始总体认知诊断")

        response = self.socrates.run(
            "请开始评估我的总体认知水平。",
            self.context,
        )
        return response.reply

    def _is_command(self, text: str) -> bool:
        """判断用户消息是否是明确的指令（而非对话延续）"""
        text_lower = text.strip().lower()
        commands = (
            "开始学习", "开始", "学习", "我准备好了",
            "进度", "学习进度", "查看进度",
            "复习", "回顾", "我要复习",
            "下一个", "下一个知识点",
            "帮助", "help", "怎么用",
            "更新大纲", "重新大纲", "刷新大纲",
            "重新诊断", "重新评估", "诊断",
            "放弃", "跳过", "不学了", "中止", "换一个",
        )
        if text_lower in commands:
            return True
        if text_lower.startswith("学习 ") or text_lower.startswith("学习"):
            return True
        return False

    def _is_abort_command(self, text: str) -> bool:
        """判断是否为中止学习的指令"""
        text_lower = text.strip().lower()
        abort_commands = ("放弃", "跳过", "不学了", "中止", "换一个", "退出学习", "停止学习")
        return text_lower in abort_commands and self.context.state != LearningState.IDLE

    def _abort_learning(self) -> str:
        """中止当前学习，不计入考核通过"""
        topic = self.context.current_topic or "当前知识点"
        old_state = self.context.state.value
        self.context.state = LearningState.IDLE
        self.context.current_topic = None
        self.context.save()
        self.socrates.clear_history()
        self.examiner.clear_history()
        logger.info(f"用户中止学习: topic={topic}, 原状态={old_state}，不计入通过")

        return (
            f"好的，已中止「{topic}」的学习，该知识点不会被标记为已通过。\n\n"
            "你可以：\n"
            "  • 发送「开始学习」- 继续学习下一个原理\n"
            "  • 发送「学习 xxx」- 指定学习其他原理\n"
            "  • 发送「进度」- 查看学习进度"
        )

    def _extract_topic_switch(self, text: str) -> str | None:
        """从消息中提取切换知识点的请求，返回知识点名称或 None"""
        text_lower = text.strip().lower()
        if text_lower.startswith("学习 ") or text_lower.startswith("学习"):
            topic_name = text.strip()[2:].strip()
            if topic_name:
                return topic_name
        return None

    def _start_learning(self, topic_name: str = None) -> str:
        """开始学习一个原理
        如果未诊断，先进行总体诊断；如果已诊断，直接报原理名词进入教学
        """
        from learning.syllabus import get_topic_by_name, get_next_topic

        # 未诊断过 → 先进行总体诊断
        if not self._is_diagnosed():
            return self._start_diagnosis()

        if topic_name:
            topic = get_topic_by_name(topic_name)
            if not topic:
                return f"没找到和「{topic_name}」相关的原理。发送「帮助」查看使用方式。"
        else:
            learned_ids = self.progress_tracker.get_learned_topic_ids()
            topic = get_next_topic(learned_ids)
            if not topic:
                return "🎉 恭喜！你已经学完了当前大纲的所有原理！发送「更新大纲」生成新的学习计划，或「复习」来巩固已学内容。"

        # 重置上下文，跳过诊断直接进入教学
        self.context.reset_for_new_topic(topic["name"], skip_diagnosis=True)
        # 设置难度为诊断结果
        self.context.difficulty_level = self.memory.long_term.cognitive_level
        self.context.diagnosis_result = f"总体认知层次: {self.memory.long_term.cognitive_level}/5"
        self.socrates.clear_history()
        self.examiner.clear_history()

        category = topic.get("category", "")
        description = topic.get("description", "")
        difficulty = topic.get("difficulty", "")
        logger.info(f"开始学习: {topic['name']} (领域:{category}, 难度{difficulty})")

        # 记录知识点开始学习
        self.progress_tracker.track_topic_start(topic["id"], topic["name"])

        # 生成二级大纲（子目录）
        outline = self._generate_topic_outline(topic)
        if outline:
            self.progress_tracker.set_topic_outline(topic["id"], outline)

        # 先抛出原理名词 + 大纲概览
        intro = f"📚 今天我们要学习的原理是：\n\n【{topic['name']}】"
        if category:
            intro += f"\n领域：{category}"
        if description:
            intro += f"\n{description}"

        # 展示大纲
        if outline:
            intro += "\n\n📋 学习路线：\n"
            for item in outline:
                intro += f"  {item['id']}. {item['title']}\n"

        intro += "\n你对这个概念有什么了解吗？请随便说说你的理解，知道多少说多少。"
        return intro

    def _start_review(self) -> str:
        """开始复习"""
        due = self.progress_tracker.get_due_reviews()
        if not due:
            return "当前没有需要复习的知识点。继续学习新知识吧！发送「开始学习」。"

        # 取第一个待复习的知识点
        review_item = due[0]
        self.context.reset_for_new_topic(review_item["name"])
        self.socrates.clear_history()
        self.examiner.clear_history()

        logger.info(f"开始复习: {review_item['name']}")

        response = self.socrates.run(
            f"我要复习「{review_item['name']}」，这是第{review_item['review_round']}轮复习。",
            self.context,
        )
        return response.reply

    def _route_to_current_agent(self, text: str) -> str:
        """根据当前状态路由消息到对应 Agent"""
        from learning.syllabus import get_topic_by_name

        state = self.context.state

        if state in (LearningState.DIAGNOSING, LearningState.TEACHING):
            response = self.socrates.run(text, self.context)
            # 记录教学轮次 + 更新子目录覆盖
            if state == LearningState.TEACHING and self.context.current_topic:
                topic_info = get_topic_by_name(self.context.current_topic)
                if topic_info:
                    self.progress_tracker.track_teaching_round(topic_info["id"], self.context.current_topic)
                    # 解析并更新子目录覆盖状态
                    covered_ids = response.data.get("covered_ids", [])
                    if covered_ids:
                        self.progress_tracker.mark_subtopic_covered(topic_info["id"], covered_ids)
        elif state == LearningState.EXAMINING:
            # 如果 examiner 还没有对话历史，说明是刚从教学转过来的
            # 用户的回复（如"准备好了"）不作为考题答案，而是触发出第一题
            if not self.conversation.get_history("examiner"):
                response = self.examiner.run(
                    f"请开始对用户关于「{self.context.current_topic}」的掌握程度进行考核。",
                    self.context,
                )
            else:
                response = self.examiner.run(text, self.context)
        else:
            return self._casual_chat(text)

        # 处理 Agent 返回的动作
        return self._handle_action(response)

    def _handle_action(self, response: AgentResponse) -> str:
        """处理 Agent 返回的动作，驱动状态转换"""
        from learning.syllabus import get_topic_by_name

        action = response.action

        if action == Action.CONTINUE:
            return response.reply

        elif action == Action.DIAGNOSIS_DONE:
            # 总体诊断完成 → 存储结果到用户画像，进入空闲状态
            level = response.data.get("cognitive_level", 3)
            self.memory.long_term.cognitive_level = level
            self.memory.long_term.save()
            self.context.diagnosis_result = f"总体认知层次: {level}/5"
            self.context.difficulty_level = max(1, min(5, level))
            self.context.state = LearningState.IDLE
            self.context.save()
            logger.info(f"总体诊断完成: 认知层次={level}, 回到空闲")

            # 存储诊断结果到记忆
            if self.memory:
                self.memory.store_conversation_snippet(
                    "总体诊断",
                    f"诊断结果: 认知层次 {level}/5",
                    "coordinator",
                )

            return (
                response.reply
                + f"\n\n📊 诊断完成！你的总体认知层次：{level}/5"
                + "\n我会根据这个水平为你调整教学难度。"
                + "\n\n发送「开始学习」开始学习第一个原理！"
            )

        elif action == Action.TEACHING_DONE:
            # 教学完成 → 进入考核（但不立即出题，等用户回复后再出第一题）
            summary = self.conversation.get_summary("socrates", max_messages=10)
            self.context.teaching_summary = summary or "已完成教学"
            self.context.state = LearningState.EXAMINING
            self.context.save()
            logger.info("教学完成, 进入考核")

            return response.reply + "\n\n📝 接下来，让我们检验一下你的理解程度。准备好了就说一声！"

        elif action == Action.EXAM_PASSED:
            # 考核通过 → 生成知识总结 → 知识点掌握
            mastery = response.data.get("mastery", 3)
            topic = self.context.current_topic

            # 在清空对话历史前，生成知识总结卡片
            knowledge_summary = self._generate_knowledge_summary(topic)

            self.context.state = LearningState.IDLE
            self.context.current_topic = None  # 知识点完成，清空当前话题
            self.context.save()

            # 记录学习进度
            topic_info = get_topic_by_name(topic)
            topic_id = topic_info["id"] if topic_info else topic
            self.progress_tracker.record_learned(topic_id, topic, mastery)
            self.progress_tracker.track_exam_attempt(topic_id, topic, passed=True)

            # 存储知识到向量记忆（用知识总结替代教学摘要，内容更结构化）
            if self.memory:
                store_content = knowledge_summary or self.context.teaching_summary or ""
                self.memory.store_knowledge(topic, store_content)
                self.memory.long_term.total_topics_learned += 1
                self.memory.long_term.update_topic_history(
                    topic, store_content[:200], mastery
                )

            # 清空对话历史（一个知识点学完了）
            self.socrates.clear_history()
            self.examiner.clear_history()
            logger.info(f"知识点「{topic}」已掌握，清空对话历史")

            stars = "⭐" * mastery
            result = response.reply + f"\n\n🎉 恭喜！你已掌握「{topic}」！掌握度: {stars}"

            # 追加知识总结卡片
            if knowledge_summary:
                result += f"\n\n{'─' * 20}\n{knowledge_summary}"

            result += "\n\n发送「开始学习」继续学习下一个知识点，或「进度」查看学习进度。"
            return result

        elif action == Action.EXAM_FAILED:
            # 考核未通过 → 回到教学（但不立即发新教学内容，等用户回复后再继续）
            weakness = response.data.get("weakness", "")
            self.context.state = LearningState.TEACHING
            self.context.retry_count += 1
            self.context.save()
            self.context.difficulty_level = max(1, self.context.difficulty_level - 1)

            # 记录考核未通过
            topic_info = get_topic_by_name(self.context.current_topic)
            if topic_info:
                self.progress_tracker.track_exam_attempt(topic_info["id"], self.context.current_topic, passed=False)
            # 记录薄弱点，下次用户回复时 socrates 会用到
            self.context.diagnosis_result = (
                (self.context.diagnosis_result or "") + f" 薄弱点: {weakness}"
            )
            logger.info(f"考核未通过(第{self.context.retry_count}次), 薄弱点: {weakness}")

            return (
                response.reply
                + "\n\n🔄 没关系，我们换个角度再来理解一下。你觉得哪里最困惑？"
            )

        return response.reply

    def _regenerate_syllabus(self) -> str:
        """重新生成学习大纲"""
        from learning.syllabus import regenerate_syllabus
        learned_names = [t["name"] for t in self.progress_tracker.get_all_learned()]
        syllabus = regenerate_syllabus(learned_names)
        names = [f"{i+1}. {t['name']}" for i, t in enumerate(syllabus[:10])]
        return (
            f"📚 学习大纲已更新！共 {len(syllabus)} 个原理，前 10 个：\n"
            + "\n".join(names)
            + "\n\n发送「开始学习」开始吧！"
        )

    def _generate_topic_outline(self, topic: dict) -> list[dict]:
        """用 LLM 为知识点生成二级大纲（子目录）"""
        from core.llm import chat_json

        topic_name = topic.get("name", "")
        category = topic.get("category", "")
        description = topic.get("description", "")
        level = self.context.difficulty_level

        prompt = f"""为知识点【{topic_name}】生成一个结构化的二级教学大纲。
领域：{category}
描述：{description}
用户认知层次：{level}/5

要求：
1. 生成 4-8 个子目录，覆盖该知识点从"为什么需要它"到"深入理解"的完整路径
2. 子目录必须按教学逻辑排序：背景动机 → 核心概念 → 数学原理 → 推导过程 → 应用实例 → 边界与局限
3. 每个子目录是一个独立的教学单元，不能太大也不能太碎

返回 JSON 数组格式，每项包含 id 和 title：
[{{"id": "1", "title": "背景与动机"}}, {{"id": "2", "title": "核心概念定义"}}, ...]
只返回 JSON，不要其他内容。"""

        try:
            messages = [{"role": "user", "content": prompt}]
            result = chat_json(messages)
            if isinstance(result, list) and len(result) >= 3:
                # 确保格式正确，加上 covered 字段
                outline = []
                for item in result:
                    outline.append({
                        "id": str(item.get("id", "")),
                        "title": item.get("title", ""),
                        "covered": False,
                    })
                logger.info(f"生成二级大纲: {topic_name}, {len(outline)} 个子目录")
                return outline
        except Exception as e:
            logger.error(f"生成二级大纲失败: {e}")

        # 兜底：生成默认大纲
        return [
            {"id": "1", "title": "背景与动机", "covered": False},
            {"id": "2", "title": "核心概念", "covered": False},
            {"id": "3", "title": "数学原理与公式推导", "covered": False},
            {"id": "4", "title": "应用实例", "covered": False},
            {"id": "5", "title": "边界条件与局限", "covered": False},
        ]

    def _casual_chat(self, text: str) -> str:
        """闲聊模式（带上一轮上下文，避免丢失对话连续性）"""
        from core.llm import chat

        messages = [
            {"role": "system", "content": (
                "你是苏格拉底，一位友善的学习伙伴，帮助用户掌握世界万物原理。"
                "用户目前没有在学习流程中。"
                "如果用户想聊天，简短回复即可。"
                "适当引导用户开始学习。"
                "回复要简洁。"
            )},
        ]

        # 注入上一轮对话上下文（让LLM理解用户在回应什么）
        if self.context.last_bot_reply:
            messages.append({"role": "assistant", "content": self.context.last_bot_reply[:500]})
        messages.append({"role": "user", "content": text})

        return chat(messages)

    def _generate_knowledge_summary(self, topic: str) -> str:
        """生成结构化知识总结卡片（含个人薄弱点分析）"""
        from core.llm import chat

        teaching_summary = self.context.teaching_summary or ""

        # 获取考核过程摘要（薄弱点主要在考核中暴露）
        exam_summary = self.conversation.get_summary("examiner", max_messages=10) or ""

        # 提取已记录的薄弱点
        weakness_info = ""
        if self.context.diagnosis_result and "薄弱点" in self.context.diagnosis_result:
            weakness_info = self.context.diagnosis_result

        prompt = f"""请为用户刚学完的知识点【{topic}】生成一份结构化的知识总结卡片。

以下是教学过程的摘要：
{teaching_summary[:2000]}

以下是考核过程的摘要（注意用户回答中暴露的薄弱环节）：
{exam_summary[:1000]}

已识别的薄弱点记录：{weakness_info}

请按以下结构输出总结（使用 Markdown 格式）：

📖 **知识总结：{topic}**

**1. 核心定义**
用一两句话精准定义这个原理/概念的本质。

**2. 数学表达与推导**
给出核心公式，简要展示关键推导步骤（从什么出发 → 经过什么变换 → 得到什么结论）。

**3. 直觉理解**
用最通俗的语言或类比，说明这个原理"到底在说什么"。

**4. 关键要点**
列出 3-5 个必须记住的核心要点。

**5. 应用场景**
给出 2-3 个典型应用场景（优先关联智能驾驶/车辆工程）。

**6. 易混淆/易错点**
指出常见的误解或容易搞混的概念。

**7. 🎯 你的薄弱点与强化建议**
根据教学和考核过程中用户的实际表现，分析：
- 用户在哪些子概念上理解不够深入或回答有偏差
- 用户在哪些环节需要较多引导才能理解
- 针对每个薄弱点，给出具体的强化建议（如：建议重点复习xxx、尝试自己推导xxx公式、思考xxx在xx场景下如何应用）
注意：这部分必须基于教学/考核过程中的实际表现，不要泛泛而谈。如果用户表现很好没有明显薄弱点，就写"整体掌握扎实"并指出可以进一步深入的方向。

要求：
- 简洁精炼，每个部分 2-4 句话即可，不要长篇大论
- 公式要完整但不需要重新推导每一步
- 薄弱点分析必须具体、有针对性，而非笼统建议
- 这是一份"速查卡片"，用户以后可以快速回顾"""

        try:
            messages = [{"role": "user", "content": prompt}]
            summary = chat(messages)
            return summary
        except Exception as e:
            logger.error(f"生成知识总结失败: {e}")
            return ""
