"""
对话历史管理
每个 Agent 维护独立的对话历史（仅在内存中，不持久化）
长期知识通过 UserProfile 和 VectorStore 保存
每个知识点的学习（教学→考核→掌握）是一个完整话题，掌握后才清空
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConversationManager:
    """管理多个 Agent 的对话历史（纯内存，重启后重置）"""

    def __init__(self, user_id: str = "default"):
        self.user_id = user_id
        self._histories: dict[str, list[dict]] = {}

    def get_history(self, agent_name: str) -> list[dict]:
        """获取某个 Agent 的对话历史"""
        return self._histories.get(agent_name, [])

    def add_message(self, agent_name: str, role: str, content: str):
        """添加一条消息到指定 Agent 的对话历史"""
        if agent_name not in self._histories:
            self._histories[agent_name] = []
        self._histories[agent_name].append({"role": role, "content": content})

    def build_messages(
        self,
        agent_name: str,
        system_prompt: str,
        user_message: str,
        max_history: int = 20,
    ) -> list[dict]:
        """
        构建发送给 LLM 的完整消息列表
        = system_prompt + 最近的对话历史 + 当前用户消息
        """
        messages = [{"role": "system", "content": system_prompt}]

        history = self.get_history(agent_name)
        if len(history) > max_history:
            history = history[-max_history:]
        messages.extend(history)

        messages.append({"role": "user", "content": user_message})
        return messages

    def clear_agent(self, agent_name: str):
        """清除某个 Agent 的对话历史"""
        self._histories[agent_name] = []

    def clear_all(self):
        """清除所有对话历史"""
        self._histories = {}

    def get_summary(self, agent_name: str, max_messages: int = 5) -> Optional[str]:
        """获取某个 Agent 最近对话的简要摘要（用于跨 Agent 传递上下文）"""
        history = self.get_history(agent_name)
        if not history:
            return None
        recent = history[-max_messages:]
        parts = []
        for msg in recent:
            role_label = "用户" if msg["role"] == "user" else "助手"
            parts.append(f"{role_label}: {msg['content'][:200]}")
        return "\n".join(parts)
