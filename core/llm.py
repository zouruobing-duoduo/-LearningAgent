"""
DeepSeek API 统一封装层
所有 Agent 通过此模块调用大模型
"""
import json
import logging
from typing import Optional
from openai import OpenAI

import config

logger = logging.getLogger(__name__)

# 使用 OpenAI 兼容接口（DeepSeek 支持）
_client = OpenAI(
    api_key=config.DEEPSEEK_API_KEY,
    base_url=config.DEEPSEEK_BASE_URL,
)


def chat(
    messages: list[dict],
    model: str = config.DEEPSEEK_MODEL,
    temperature: float = config.DEEPSEEK_TEMPERATURE,
    max_tokens: int = config.DEEPSEEK_MAX_TOKENS,
    response_format: Optional[dict] = None,
) -> str:
    """
    调用 DeepSeek 大模型进行对话

    Args:
        messages: OpenAI 格式的消息列表 [{"role": "system"|"user"|"assistant", "content": "..."}]
        model: 模型名称
        temperature: 温度参数
        max_tokens: 最大生成token数
        response_format: 响应格式（如 {"type": "json_object"}）

    Returns:
        模型回复的文本内容
    """
    try:
        kwargs = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = _client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        logger.debug(f"LLM response: {content[:100]}...")
        return content

    except Exception as e:
        logger.error(f"LLM调用失败: {e}")
        raise


def chat_json(
    messages: list[dict],
    temperature: float = 0.3,
    max_tokens: int = config.DEEPSEEK_MAX_TOKENS,
) -> dict:
    """
    调用大模型并返回 JSON 格式的响应
    用于需要结构化输出的场景（如意图识别、评估打分）
    """
    content = chat(
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        logger.error(f"JSON解析失败: {content}")
        return {"error": "JSON解析失败", "raw": content}
