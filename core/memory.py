"""
记忆模块 - 三层记忆架构
短期记忆：当前会话对话上下文
长期记忆：用户画像 + 学习历史
向量记忆：ChromaDB 语义检索
"""
import json
import os
import logging
from typing import Optional
from dataclasses import dataclass, field, asdict
from datetime import datetime

import config

logger = logging.getLogger(__name__)


# ========== 长期记忆：用户画像 ==========

@dataclass
class UserProfile:
    """用户画像 - 长期记忆"""
    cognitive_level: int = 0                   # 总体认知层次 1-5（0=未诊断）
    learning_style: str = ""                 # 学习风格描述
    strengths: list[str] = field(default_factory=list)    # 强项
    weaknesses: list[str] = field(default_factory=list)   # 弱项
    error_patterns: list[str] = field(default_factory=list)  # 常犯错误模式
    interests: list[str] = field(default_factory=list)    # 兴趣点
    insights: list[str] = field(default_factory=list)     # 关键洞察
    topic_history: dict = field(default_factory=dict)     # 知识点学习历史摘要
    total_topics_learned: int = 0
    last_active: str = ""

    def save(self):
        """持久化到文件"""
        self.last_active = datetime.now().isoformat()
        try:
            with open(config.USER_PROFILE_FILE, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存用户画像失败: {e}")

    @classmethod
    def load(cls) -> "UserProfile":
        """从文件加载"""
        if os.path.exists(config.USER_PROFILE_FILE):
            try:
                with open(config.USER_PROFILE_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
            except Exception as e:
                logger.error(f"加载用户画像失败: {e}")
        return cls()

    def add_insight(self, insight: str):
        """添加关键洞察（去重）"""
        if insight not in self.insights:
            self.insights.append(insight)
            if len(self.insights) > 50:
                self.insights = self.insights[-50:]
            self.save()

    def update_topic_history(self, topic: str, summary: str, mastery: int):
        """更新知识点学习记录"""
        self.topic_history[topic] = {
            "summary": summary,
            "mastery": mastery,
            "learned_at": datetime.now().isoformat(),
        }
        self.save()

    def get_summary(self) -> str:
        """生成用户画像摘要（供Agent注入prompt用）"""
        parts = []
        if self.learning_style:
            parts.append(f"学习风格: {self.learning_style}")
        if self.strengths:
            parts.append(f"强项: {', '.join(self.strengths[:5])}")
        if self.weaknesses:
            parts.append(f"弱项: {', '.join(self.weaknesses[:5])}")
        if self.interests:
            parts.append(f"兴趣点: {', '.join(self.interests[:5])}")
        if self.insights:
            parts.append(f"关键洞察: {'; '.join(self.insights[-3:])}")
        parts.append(f"已学习知识点数: {self.total_topics_learned}")
        return "\n".join(parts) if parts else "暂无用户画像数据"


# ========== 向量记忆：ChromaDB ==========

class VectorStore:
    """向量记忆 - ChromaDB 语义检索"""

    def __init__(self):
        self._collection = None
        self._client = None

    def _ensure_initialized(self):
        """延迟初始化 ChromaDB（避免import时就加载）"""
        if self._collection is not None:
            return
        try:
            import chromadb
            self._client = chromadb.PersistentClient(path=config.CHROMA_DB_DIR)
            self._collection = self._client.get_or_create_collection(
                name=config.CHROMA_COLLECTION_NAME,
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(f"ChromaDB 初始化成功, 已有 {self._collection.count()} 条记录")
        except Exception as e:
            logger.error(f"ChromaDB 初始化失败: {e}")
            self._collection = None

    def store(self, doc_id: str, content: str, metadata: Optional[dict] = None):
        """存储文档到向量库"""
        self._ensure_initialized()
        if self._collection is None:
            logger.warning("ChromaDB 不可用，跳过存储")
            return
        try:
            meta = metadata or {}
            meta["stored_at"] = datetime.now().isoformat()
            self._collection.upsert(
                ids=[doc_id],
                documents=[content],
                metadatas=[meta],
            )
        except Exception as e:
            logger.error(f"向量存储失败: {e}")

    def recall(self, query: str, top_k: int = 5, where: Optional[dict] = None) -> list[dict]:
        """根据语义相似度检索相关记忆"""
        self._ensure_initialized()
        if self._collection is None or self._collection.count() == 0:
            return []
        try:
            kwargs = {
                "query_texts": [query],
                "n_results": min(top_k, self._collection.count()),
            }
            if where:
                kwargs["where"] = where
            results = self._collection.query(**kwargs)
            items = []
            for i in range(len(results["ids"][0])):
                items.append({
                    "id": results["ids"][0][i],
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else None,
                })
            return items
        except Exception as e:
            logger.error(f"向量检索失败: {e}")
            return []

    def count(self) -> int:
        self._ensure_initialized()
        return self._collection.count() if self._collection else 0


# ========== 统一记忆接口 ==========

class Memory:
    """
    统一记忆管理器 - 所有 Agent 共享读写
    整合短期记忆（ConversationManager）、长期记忆（UserProfile）、向量记忆（VectorStore）
    """

    def __init__(self, conversation_manager, user_id: str = "default"):
        self.user_id = user_id
        self.short_term = conversation_manager   # 短期：对话上下文
        self.long_term = UserProfile.load()      # 长期：用户画像
        self.vector_store = VectorStore()        # 向量：语义检索

    def recall(self, query: str, top_k: int = 5) -> list[dict]:
        """根据语义相似度检索相关记忆"""
        return self.vector_store.recall(query, top_k)

    def store_knowledge(self, topic: str, content: str, metadata: Optional[dict] = None):
        """存储知识到向量库"""
        doc_id = f"knowledge_{topic}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        meta = metadata or {}
        meta["type"] = "knowledge"
        meta["topic"] = topic
        self.vector_store.store(doc_id, content, meta)

    def store_conversation_snippet(self, topic: str, snippet: str, agent_name: str):
        """存储对话片段到向量库（用于后续检索关联知识）"""
        doc_id = f"conv_{agent_name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
        self.vector_store.store(doc_id, snippet, {
            "type": "conversation",
            "topic": topic,
            "agent": agent_name,
        })

    def update_user_profile(self, key: str, value):
        """更新用户画像字段"""
        if hasattr(self.long_term, key):
            setattr(self.long_term, key, value)
            self.long_term.save()

    def get_context_for_agent(self, agent_name: str, query: str = "") -> dict:
        """
        为特定 Agent 组装上下文（短期+长期+向量检索结果）
        """
        context = {
            "user_profile_summary": self.long_term.get_summary(),
        }

        # 添加短期记忆：最近的对话摘要
        summary = self.short_term.get_summary(agent_name)
        if summary:
            context["recent_conversation"] = summary

        # 添加向量检索结果
        if query:
            related = self.recall(query, top_k=3)
            if related:
                context["related_memories"] = [
                    f"[{item['metadata'].get('type', '?')}] {item['content'][:200]}"
                    for item in related
                ]

        return context

    def save_all(self):
        """持久化所有记忆"""
        self.long_term.save()
