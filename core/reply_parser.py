"""
回复解析器 - 从 LLM 回复中提取图片标记并渲染
支持三种标记：[MERMAID]...[/MERMAID], [LATEX]...[/LATEX], [IMG_SEARCH:...]
"""
import re
import logging
from typing import Optional

from core.image_gen import render_mermaid, render_latex, search_image

logger = logging.getLogger(__name__)

# 匹配三种图片标记的正则
_MERMAID_PATTERN = re.compile(
    r'\[MERMAID\]\s*(.*?)\s*\[/MERMAID\]', re.DOTALL
)
_LATEX_PATTERN = re.compile(
    r'\[LATEX\](.*?)\[/LATEX\]', re.DOTALL
)
_IMG_SEARCH_PATTERN = re.compile(
    r'\[IMG_SEARCH:([^\]]+)\]'
)

# 合并所有图片标记的模式（用于分割文本）
_ALL_PATTERNS = re.compile(
    r'(\[MERMAID\].*?\[/MERMAID\]|\[LATEX\].*?\[/LATEX\]|\[IMG_SEARCH:[^\]]+\])',
    re.DOTALL,
)


def parse_reply_with_images(reply_text: str) -> Optional[list[dict]]:
    """
    解析 LLM 回复，提取图片标记并渲染为图片 bytes。

    返回有序的 content_parts 列表：
    - {"type": "text", "text": "..."} 文本段
    - {"type": "image_bytes", "data": b"...", "alt": "描述"} 图片段

    如果回复中没有任何图片标记，返回 None（走原有纯文本逻辑）。
    """
    if not reply_text:
        return None

    # 检查是否包含任何图片标记
    if not _ALL_PATTERNS.search(reply_text):
        return None

    parts = []
    # 按图片标记分割文本
    segments = _ALL_PATTERNS.split(reply_text)

    for segment in segments:
        if not segment:
            continue

        # 尝试匹配 Mermaid
        m = _MERMAID_PATTERN.match(segment)
        if m:
            code = m.group(1).strip()
            img_data = render_mermaid(code)
            if img_data:
                parts.append({
                    "type": "image_bytes",
                    "data": img_data,
                    "alt": "概念图",
                })
            else:
                # 渲染失败，降级为代码文本
                parts.append({"type": "text", "text": f"\n```\n{code}\n```\n"})
            continue

        # 尝试匹配 LaTeX
        m = _LATEX_PATTERN.match(segment)
        if m:
            formula = m.group(1).strip()
            img_data = render_latex(formula)
            if img_data:
                parts.append({
                    "type": "image_bytes",
                    "data": img_data,
                    "alt": "公式",
                })
            else:
                # 渲染失败，降级为文本公式
                parts.append({"type": "text", "text": f" {formula} "})
            continue

        # 尝试匹配搜图
        m = _IMG_SEARCH_PATTERN.match(segment)
        if m:
            query = m.group(1).strip()
            img_data = search_image(query)
            if img_data:
                parts.append({
                    "type": "image_bytes",
                    "data": img_data,
                    "alt": query,
                })
            # 搜图失败就静默跳过，不留痕迹
            continue

        # 普通文本段
        text = segment.strip()
        if text:
            parts.append({"type": "text", "text": text})

    # 如果解析后没有任何图片，返回 None
    has_image = any(p["type"] == "image_bytes" for p in parts)
    if not has_image:
        return None

    return parts
