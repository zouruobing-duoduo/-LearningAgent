"""
Agent 基类
所有 Agent 继承此类，统一接口
"""
import logging
from abc import ABC, abstractmethod

from core.llm import chat, chat_json
from core.state import AgentResponse, LearningContext
from core.conversation import ConversationManager
from core.memory import Memory

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Agent 基类"""

    name: str = "base"
    system_prompt: str = ""

    def __init__(self, conversation: ConversationManager, memory: Memory = None):
        self.conversation = conversation
        self.memory = memory

    def run(self, user_message: str, context: LearningContext) -> AgentResponse:
        """
        处理用户消息，返回结构化响应

        Args:
            user_message: 用户发送的消息
            context: 当前学习上下文

        Returns:
            AgentResponse: 包含回复文本、动作指令、附加数据
        """
        # 构建 prompt（子类可覆盖 build_system_prompt 来动态生成）
        system_prompt = self.build_system_prompt(context)

        # 注入记忆上下文
        if self.memory:
            mem_ctx = self.memory.get_context_for_agent(
                self.name,
                query=user_message,
            )
            if mem_ctx.get("user_profile_summary"):
                system_prompt += f"\n\n[用户画像]\n{mem_ctx['user_profile_summary']}"
            if mem_ctx.get("related_memories"):
                system_prompt += "\n\n[相关记忆]\n" + "\n".join(mem_ctx["related_memories"])

        # 构建完整消息列表（system + history + user_message）
        messages = self.conversation.build_messages(
            agent_name=self.name,
            system_prompt=system_prompt,
            user_message=user_message,
        )

        # 调用 LLM
        reply = chat(messages)

        # 记录对话历史
        self.conversation.add_message(self.name, "user", user_message)
        self.conversation.add_message(self.name, "assistant", reply)

        # 解析响应（子类实现具体逻辑）
        return self.parse_response(reply, context)

    def build_system_prompt(self, context: LearningContext) -> str:
        """
        构建系统提示词，子类可覆盖以注入动态上下文
        """
        return self.system_prompt

    @abstractmethod
    def parse_response(self, reply: str, context: LearningContext) -> AgentResponse:
        """
        解析 LLM 的回复，提取动作指令
        子类必须实现此方法
        """
        pass

    def clear_history(self):
        """清除本 Agent 的对话历史"""
        self.conversation.clear_agent(self.name)
