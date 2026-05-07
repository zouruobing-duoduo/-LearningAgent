"""
考核官 Agent - 独立考核评估
负责验证用户是否真正理解所学知识点
与 Socrates（教学）角色分离，避免混淆
"""
import logging

from agents.base import BaseAgent
from core.llm import chat, chat_json
from core.state import AgentResponse, Action, LearningContext

logger = logging.getLogger(__name__)

EXAMINER_PROMPT = """你是一位严谨但友善的考核官。你的任务是验证用户是否真正理解了【{topic}】。

注意：你不是教师，不要讲解知识。你的职责只是考核。

教学摘要（用户刚学完的内容）：
{teaching_summary}

考核方法：
1. 提出2-3个验证性问题（不是简单复述，而是需要应用理解的场景题）
2. 可以出一个反直觉的场景，看用户能否正确推理
3. 最后让用户用自己的话，一句话说透这个概念的本质
4. 用户是智能驾驶领域研发人员，可以结合智驾场景出题

考核规则：
- 每次只问一个问题，等用户回答后再出下一题
- 如果用户回答有误，可以给一个小提示，但不要直接讲解
- 综合多轮问答评估掌握程度

掌握度评分标准（1-5星，必须严格按此标准打分）：
⭐ 1星 - 仅记住表面：只能复述定义或术语，无法解释含义，遇到变式题完全无法应对
⭐⭐ 2星 - 初步理解：能大致说出原理含义，但解释不够准确，应用题答对率低于50%
⭐⭐⭐ 3星 - 基本掌握：能用自己的话正确解释核心概念，能应对常规场景题，但面对反直觉或边界情况有困难
⭐⭐⭐⭐ 4星 - 深入理解：能准确解释本质，能正确处理变式和反直觉场景，能识别常见误解，能关联到其他知识
⭐⭐⭐⭐⭐ 5星 - 融会贯通：不仅能解释和应用，还能自主举出新例子、发现边界条件、提出有深度的追问，展现出超越教学内容的思考

评估维度（打分时综合考虑以下4个维度）：
1. 概念理解：能否用自己的话说透本质（而非背诵定义）
2. 应用迁移：能否将原理正确应用到新场景（尤其是智驾场景）
3. 辨析能力：能否识别常见误解、区分易混淆概念
4. 推理深度：面对反直觉或边界情况，能否正确推理

当你完成考核后，在回复末尾单独一行输出评估结果：
通过：[EXAM_RESULT:PASS:掌握程度1-5]
未通过：[EXAM_RESULT:FAIL:薄弱点描述]

判定通过的最低标准：掌握度 >= 3星"""


class ExaminerAgent(BaseAgent):
    """考核官Agent - 独立评估用户掌握程度"""

    name = "examiner"
    system_prompt = ""  # 动态生成

    def build_system_prompt(self, context: LearningContext) -> str:
        return EXAMINER_PROMPT.format(
            topic=context.current_topic or "未知知识点",
            teaching_summary=context.teaching_summary or "无摘要",
        )

    def parse_response(self, reply: str, context: LearningContext) -> AgentResponse:
        """解析考核结果"""

        if "[EXAM_RESULT:" in reply:
            try:
                result_str = reply.split("[EXAM_RESULT:")[1].split("]")[0]
                parts = result_str.split(":", 1)
                passed = parts[0] == "PASS"
                detail = parts[1] if len(parts) > 1 else ""
                clean_reply = reply.split("[EXAM_RESULT:")[0].strip()

                if passed:
                    mastery = 3
                    try:
                        mastery = int(detail)
                    except ValueError:
                        pass
                    return AgentResponse(
                        reply=clean_reply,
                        action=Action.EXAM_PASSED,
                        data={"mastery": mastery},
                    )
                else:
                    return AgentResponse(
                        reply=clean_reply,
                        action=Action.EXAM_FAILED,
                        data={"weakness": detail},
                    )
            except (ValueError, IndexError):
                pass

        # 默认：继续考核对话
        return AgentResponse(reply=reply, action=Action.CONTINUE)
