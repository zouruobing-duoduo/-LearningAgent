"""
进度追踪 Agent - 学习进度管理 + 艾宾浩斯复习提醒
"""
import json
import os
import logging
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

import config
from agents.base import BaseAgent
from core.state import AgentResponse, Action, LearningContext

logger = logging.getLogger(__name__)

# 艾宾浩斯复习间隔（天）
REVIEW_INTERVALS = [1, 7, 16, 35]


class ProgressTracker(BaseAgent):
    """进度追踪Agent - 学习进度 + 复习管理"""

    name = "progress_tracker"
    system_prompt = ""

    def __init__(self, conversation=None, memory=None):
        super().__init__(conversation, memory)
        self._progress = self._load_progress()

    def _load_progress(self) -> dict:
        """加载学习进度"""
        if os.path.exists(config.PROGRESS_FILE):
            try:
                with open(config.PROGRESS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 兼容旧数据：确保 topic_stats 存在
                if "topic_stats" not in data:
                    data["topic_stats"] = {}
                return data
            except Exception as e:
                logger.error(f"加载进度失败: {e}")
        return {"learned": {}, "review_schedule": {}, "topic_stats": {}}

    def _save_progress(self):
        """保存学习进度"""
        try:
            with open(config.PROGRESS_FILE, "w", encoding="utf-8") as f:
                json.dump(self._progress, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存进度失败: {e}")

    def record_learned(self, topic_id: str, topic_name: str, mastery: int):
        """记录学习完成的知识点"""
        now = datetime.now()
        self._progress["learned"][topic_id] = {
            "name": topic_name,
            "mastery": mastery,
            "learned_at": now.isoformat(),
            "review_count": 0,
            "last_review": now.isoformat(),
        }
        # 设置艾宾浩斯复习计划
        self._schedule_review(topic_id, now)
        self._save_progress()
        logger.info(f"记录学习完成: {topic_name}, 掌握度={mastery}")

    def track_teaching_round(self, topic_id: str, topic_name: str):
        """记录一轮教学交互"""
        stats = self._get_or_create_stats(topic_id, topic_name)
        stats["teaching_rounds"] = stats.get("teaching_rounds", 0) + 1
        self._save_progress()

    def track_exam_attempt(self, topic_id: str, topic_name: str, passed: bool):
        """记录一次考核尝试"""
        stats = self._get_or_create_stats(topic_id, topic_name)
        stats["exam_attempts"] = stats.get("exam_attempts", 0) + 1
        if passed:
            stats["exam_passed"] = True
        self._save_progress()

    def track_topic_start(self, topic_id: str, topic_name: str):
        """记录知识点开始学习"""
        stats = self._get_or_create_stats(topic_id, topic_name)
        if "started_at" not in stats:
            stats["started_at"] = datetime.now().isoformat()
        self._save_progress()

    def set_topic_outline(self, topic_id: str, outline: list[dict]):
        """设置知识点的二级大纲
        outline 格式: [{"id": "1", "title": "背景与动机", "covered": False}, ...]
        """
        stats = self._get_or_create_stats(topic_id, "")
        stats["outline"] = outline
        stats["outline_total"] = len(outline)
        stats["outline_covered"] = 0
        self._save_progress()
        logger.info(f"设置知识点大纲: {topic_id}, {len(outline)} 个子目录")

    def mark_subtopic_covered(self, topic_id: str, subtopic_ids: list[str]):
        """标记子目录已覆盖"""
        stats = self._progress.get("topic_stats", {}).get(topic_id, {})
        outline = stats.get("outline", [])
        changed = False
        for item in outline:
            if item["id"] in subtopic_ids and not item.get("covered", False):
                item["covered"] = True
                changed = True
        if changed:
            stats["outline_covered"] = sum(1 for item in outline if item.get("covered"))
            self._save_progress()
            logger.info(f"子目录覆盖更新: {topic_id}, {stats['outline_covered']}/{stats['outline_total']}")

    def get_topic_outline(self, topic_id: str) -> list[dict]:
        """获取知识点大纲"""
        stats = self._progress.get("topic_stats", {}).get(topic_id, {})
        return stats.get("outline", [])

    def _get_or_create_stats(self, topic_id: str, topic_name: str) -> dict:
        """获取或创建知识点统计"""
        if topic_id not in self._progress["topic_stats"]:
            self._progress["topic_stats"][topic_id] = {
                "name": topic_name,
                "teaching_rounds": 0,
                "exam_attempts": 0,
                "exam_passed": False,
            }
        return self._progress["topic_stats"][topic_id]

    def get_topic_stats(self, topic_id: str) -> dict:
        """获取知识点统计数据"""
        return self._progress.get("topic_stats", {}).get(topic_id, {})

    def _schedule_review(self, topic_id: str, from_date: datetime):
        """设置复习计划"""
        if "review_schedule" not in self._progress:
            self._progress["review_schedule"] = {}

        learned = self._progress["learned"].get(topic_id, {})
        review_count = learned.get("review_count", 0)

        if review_count < len(REVIEW_INTERVALS):
            interval = REVIEW_INTERVALS[review_count]
            # 根据掌握程度调整间隔
            mastery = learned.get("mastery", 3)
            if mastery >= 4:
                interval = int(interval * 1.5)  # 掌握好，延长间隔
            elif mastery <= 2:
                interval = max(1, int(interval * 0.7))  # 掌握差，缩短间隔

            review_date = (from_date + timedelta(days=interval)).strftime("%Y-%m-%d")
            self._progress["review_schedule"][topic_id] = {
                "date": review_date,
                "review_round": review_count + 1,
            }

    def get_due_reviews(self) -> list[dict]:
        """获取今天到期的复习知识点"""
        today = datetime.now().strftime("%Y-%m-%d")
        due = []
        for topic_id, schedule in self._progress.get("review_schedule", {}).items():
            if schedule["date"] <= today:
                learned = self._progress["learned"].get(topic_id, {})
                due.append({
                    "topic_id": topic_id,
                    "name": learned.get("name", topic_id),
                    "mastery": learned.get("mastery", 0),
                    "review_round": schedule["review_round"],
                })
        return due

    def complete_review(self, topic_id: str, new_mastery: int):
        """完成一次复习"""
        if topic_id in self._progress["learned"]:
            self._progress["learned"][topic_id]["review_count"] += 1
            self._progress["learned"][topic_id]["mastery"] = new_mastery
            self._progress["learned"][topic_id]["last_review"] = datetime.now().isoformat()
            # 设置下次复习
            self._schedule_review(topic_id, datetime.now())
            # 移除已完成的复习安排
            self._progress.get("review_schedule", {}).pop(topic_id, None)
            self._save_progress()

    def get_learned_topic_ids(self) -> list[str]:
        """获取已学习的知识点ID列表"""
        return list(self._progress.get("learned", {}).keys())

    def get_progress_report(self, current_topic: str = None, current_state: str = None) -> str:
        """生成学习进度报告"""
        from learning.syllabus import get_syllabus

        learned = self._progress.get("learned", {})
        syllabus = get_syllabus()
        total = len(syllabus)
        learned_count = len(learned)

        if not syllabus:
            return "大纲为空，请先发送「开始学习」启动学习。"

        # ── 总体进度 ──
        pct = int(learned_count / total * 100) if total > 0 else 0
        bar_filled = pct // 10
        bar_empty = 10 - bar_filled
        progress_bar = "▓" * bar_filled + "░" * bar_empty
        lines = [
            f"📊 学习进度  {progress_bar}  {pct}%",
            f"已掌握 {learned_count}/{total} 个知识点\n",
        ]

        # ── 当前在学 ──
        if current_topic and current_state:
            state_label = {"diagnosing": "诊断中", "teaching": "学习中", "examining": "考核中"}.get(current_state, "进行中")
            lines.append(f"📖 当前：{current_topic}（{state_label}）\n")

        # ── 分领域进度 ──
        # 按 category 分组
        category_topics = defaultdict(list)
        for topic in syllabus:
            cat = topic.get("category", "其他")
            category_topics[cat].append(topic)

        lines.append("── 各领域进度 ──")
        for cat, topics in category_topics.items():
            cat_total = len(topics)
            cat_learned = sum(1 for t in topics if t["id"] in learned)
            cat_pct = int(cat_learned / cat_total * 100) if cat_total > 0 else 0

            # 领域标题 + 迷你进度
            cat_bar = "▓" * (cat_pct // 20) + "░" * (5 - cat_pct // 20)
            lines.append(f"\n{cat}  {cat_bar}  {cat_learned}/{cat_total}")

            for t in topics:
                tid = t["id"]
                name = t["name"]
                stats = self._progress.get("topic_stats", {}).get(tid, {})
                if tid in learned:
                    mastery = learned[tid].get("mastery", 0)
                    stars = "⭐" * mastery
                    outline = stats.get("outline", [])
                    if outline:
                        detail = f"{len(outline)}节"
                    else:
                        rounds = stats.get("teaching_rounds", 0)
                        detail = f"教学{rounds}轮" if rounds else ""
                    exams = stats.get("exam_attempts", 0)
                    if exams:
                        detail += f"·考核{exams}次"
                    suffix = f"（{detail}）" if detail else ""
                    lines.append(f"  ✅ {name} {stars}{suffix}")
                elif current_topic and name == current_topic:
                    state_label = {"diagnosing": "诊断中", "teaching": "学习中", "examining": "考核中"}.get(current_state, "进行中")
                    outline = stats.get("outline", [])
                    if outline:
                        covered = sum(1 for item in outline if item.get("covered"))
                        detail = f"{state_label}·{covered}/{len(outline)}节"
                    else:
                        rounds = stats.get("teaching_rounds", 0)
                        detail = f"{state_label}"
                        if rounds:
                            detail += f"·已教学{rounds}轮"
                    lines.append(f"  📖 {name}（{detail}）")
                elif stats:
                    # 曾经学过但中止了
                    outline = stats.get("outline", [])
                    if outline:
                        covered = sum(1 for item in outline if item.get("covered"))
                        lines.append(f"  △ {name}（{covered}/{len(outline)}节，未完成）")
                    else:
                        rounds = stats.get("teaching_rounds", 0)
                        lines.append(f"  △ {name}（已学{rounds}轮，未完成）")
                else:
                    lines.append(f"  ○ {name}")

        # ── 复习提醒 ──
        due = self.get_due_reviews()
        if due:
            lines.append(f"\n🔄 待复习（{len(due)} 个）：")
            for item in due:
                lines.append(f"  • {item['name']}（第{item['review_round']}轮）")

        return "\n".join(lines)

    def build_system_prompt(self, context: LearningContext) -> str:
        return self.system_prompt

    def parse_response(self, reply: str, context: LearningContext) -> AgentResponse:
        return AgentResponse(reply=reply, action=Action.SHOW_PROGRESS)
