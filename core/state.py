"""
学习状态机
管理用户在学习流程中的状态转换
"""
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import json
import os
import uuid
import logging

logger = logging.getLogger(__name__)


class LearningState(Enum):
    """学习状态"""
    IDLE = "idle"                    # 空闲，等待用户发起学习
    DIAGNOSING = "diagnosing"        # 诊断中，评估用户认知层次
    TEACHING = "teaching"            # 教学中，苏格拉底式教学
    EXAMINING = "examining"          # 考核中，验证理解程度
    SAVING = "saving"                # 固化中，写入知识库（Phase 3 Librarian）


class Action(Enum):
    """​Agent 返回的动作指令"""
    CONTINUE = "continue"            # 继续当前 Agent 对话
    DIAGNOSIS_DONE = "diagnosis_done"  # 诊断完成，进入教学
    TEACHING_DONE = "teaching_done"  # 教学完成，进入考核
    EXAM_PASSED = "exam_passed"      # 考核通过，提取知识
    EXAM_FAILED = "exam_failed"      # 考核未通过，回到教学
    SAVE_DONE = "save_done"          # 知识固化完成（Phase 3）
    SHOW_PROGRESS = "show_progress"  # 显示学习进度
    START_REVIEW = "start_review"    # 开始复习
    NEXT_TOPIC = "next_topic"        # 下一个知识点
    RESET = "reset"                  # 重置到空闲


@dataclass
class AgentMessage:
    """​Agent 间统一消息协议"""
    sender: str                           # 发送Agent名称
    receiver: str                         # 接收Agent名称
    msg_type: str = "data"                # "command" | "data" | "response"
    payload: dict = field(default_factory=dict)   # 消息内容
    context: dict = field(default_factory=dict)   # 传递的上下文
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])


@dataclass
class AgentResponse:
    """Agent 的统一响应结构"""
    reply: str                              # 回复用户的文本
    action: Action = Action.CONTINUE        # 下一步动作
    data: dict = field(default_factory=dict)  # 传递给下一个Agent的数据


@dataclass
class LearningContext:
    """当前学习上下文 — 持久化到文件，重启后恢复"""
    state: LearningState = LearningState.IDLE
    current_topic: Optional[str] = None      # 当前学习的知识点
    diagnosis_result: Optional[str] = None   # 诊断结果摘要
    teaching_summary: Optional[str] = None   # 教学内容摘要
    difficulty_level: int = 3                # 难度等级 1-5，3为默认
    retry_count: int = 0                     # 考核重试次数
    last_bot_reply: Optional[str] = None     # 最后一次bot回复（持久化，重启后恢复上下文）
    last_user_message: Optional[str] = None  # 最后一次用户消息（持久化，重启后恢复上下文）
    _file_path: str = field(default="", repr=False)  # 持久化文件路径

    def save(self):
        """持久化到文件"""
        if not self._file_path:
            return
        try:
            with open(self._file_path, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存学习上下文失败: {e}")

    @classmethod
    def load(cls, file_path: str) -> "LearningContext":
        """从文件加载，不存在则返回默认"""
        ctx = cls()
        ctx._file_path = file_path
        if os.path.exists(file_path):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                ctx.state = LearningState(data.get("state", "idle"))
                ctx.current_topic = data.get("current_topic")
                ctx.diagnosis_result = data.get("diagnosis_result")
                ctx.teaching_summary = data.get("teaching_summary")
                ctx.difficulty_level = data.get("difficulty_level", 3)
                ctx.retry_count = data.get("retry_count", 0)
                ctx.last_bot_reply = data.get("last_bot_reply")
                ctx.last_user_message = data.get("last_user_message")
                if ctx.current_topic:
                    logger.info(f"恢复学习上下文: state={ctx.state.value}, topic={ctx.current_topic}")
            except Exception as e:
                logger.error(f"加载学习上下文失败: {e}")
        return ctx

    def reset_for_new_topic(self, topic: str, skip_diagnosis: bool = False):
        """开始新知识点时重置上下文"""
        self.state = LearningState.TEACHING if skip_diagnosis else LearningState.DIAGNOSING
        self.current_topic = topic
        self.teaching_summary = None
        self.retry_count = 0
        self.save()

    def to_dict(self) -> dict:
        return {
            "state": self.state.value,
            "current_topic": self.current_topic,
            "diagnosis_result": self.diagnosis_result,
            "teaching_summary": self.teaching_summary,
            "difficulty_level": self.difficulty_level,
            "retry_count": self.retry_count,
            "last_bot_reply": self.last_bot_reply,
            "last_user_message": self.last_user_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LearningContext":
        ctx = cls()
        ctx.state = LearningState(data.get("state", "idle"))
        ctx.current_topic = data.get("current_topic")
        ctx.diagnosis_result = data.get("diagnosis_result")
        ctx.teaching_summary = data.get("teaching_summary")
        ctx.difficulty_level = data.get("difficulty_level", 3)
        ctx.retry_count = data.get("retry_count", 0)
        ctx.last_bot_reply = data.get("last_bot_reply")
        ctx.last_user_message = data.get("last_user_message")
        return ctx
