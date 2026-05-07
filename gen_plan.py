"""调用 DeepSeek 生成 Multi-Agent 方案"""
from openai import OpenAI

client = OpenAI(
    api_key="sk-64c29eb106964be2bd5147165bae73e1",
    base_url="https://api.deepseek.com",
)

prompt = """我要做一个飞书机器人形态的个性化学习Agent，名叫"苏格拉底"。请帮我设计一个Multi-Agent方案。

背景信息：
- 用户是智能驾驶领域研发人员，硕士，车辆工程专业，想掌握事物本质
- 每周学习一个物理知识点
- 采用苏格拉底式教学（追问启发，非灌输）
- 学完后将知识固化到飞书知识库
- 技术栈：Python + 飞书SDK长连接 + DeepSeek API
- 原生Python实现Multi-Agent，不用框架

请详细设计：
1. 需要哪些Agent，每个Agent的职责、输入输出
2. Agent之间如何协作，消息传递机制
3. 学习状态机的完整设计
4. 每个Agent的system prompt核心要点
5. 整体工作流程（从用户发起学习到知识固化的完整链路）
6. 你认为这个方案还需要考虑哪些我没想到的点

请给出专业、可落地的方案。"""

resp = client.chat.completions.create(
    model="deepseek-chat",
    messages=[
        {"role": "system", "content": "你是一个资深AI架构师，擅长Multi-Agent系统设计。请给出详细、专业、可落地的方案。"},
        {"role": "user", "content": prompt},
    ],
    temperature=0.7,
    max_tokens=4000,
)

print(resp.choices[0].message.content)
