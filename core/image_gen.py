"""
图片生成模块 - 支持 Mermaid 流程图、LaTeX 公式、网络搜图
所有函数返回 PNG 格式的 bytes，失败返回 None
"""
import base64
import logging
import re
from urllib.parse import quote

import requests

logger = logging.getLogger(__name__)

_TIMEOUT = 15  # HTTP 请求超时秒数


def render_mermaid(code: str) -> bytes | None:
    """
    将 Mermaid 语法渲染为 PNG 图片。
    使用免费公共 API: https://mermaid.ink/img/{base64}
    """
    try:
        code = code.strip()
        if not code:
            return None
        # mermaid.ink 要求 base64 编码的 Mermaid 代码
        encoded = base64.urlsafe_b64encode(code.encode("utf-8")).decode("utf-8")
        url = f"https://mermaid.ink/img/{encoded}"
        resp = requests.get(url, timeout=_TIMEOUT)
        if resp.status_code == 200 and resp.content:
            logger.info(f"Mermaid 渲染成功, 大小: {len(resp.content)} bytes")
            return resp.content
        else:
            logger.warning(f"Mermaid 渲染失败: HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"Mermaid 渲染异常: {e}")
        return None


def render_latex(formula: str) -> bytes | None:
    """
    将 LaTeX 公式渲染为 PNG 图片。
    使用免费公共 API: https://latex.codecogs.com/png.latex
    """
    try:
        formula = formula.strip()
        if not formula:
            return None
        # codecogs API: URL 编码公式
        encoded_formula = quote(formula)
        url = f"https://latex.codecogs.com/png.latex?\\dpi{{200}}{encoded_formula}"
        resp = requests.get(url, timeout=_TIMEOUT)
        if resp.status_code == 200 and resp.content:
            logger.info(f"LaTeX 渲染成功, 大小: {len(resp.content)} bytes")
            return resp.content
        else:
            logger.warning(f"LaTeX 渲染失败: HTTP {resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"LaTeX 渲染异常: {e}")
        return None


def search_image(query: str) -> bytes | None:
    """
    根据关键词搜索图片并返回第一张图片的 bytes。
    使用 Bing 图片搜索页面抓取（无需 API key）。
    注意：稳定性有限，失败时静默返回 None。
    """
    try:
        query = query.strip()
        if not query:
            return None
        # 通过 Bing 图片搜索获取图片 URL
        search_url = f"https://www.bing.com/images/search?q={quote(query)}&first=1"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        }
        resp = requests.get(search_url, headers=headers, timeout=_TIMEOUT)
        if resp.status_code != 200:
            logger.warning(f"图片搜索失败: HTTP {resp.status_code}")
            return None

        # 从搜索结果中提取图片 URL (murl 参数)
        pattern = r'murl&quot;:&quot;(https?://[^&]+?)&quot;'
        matches = re.findall(pattern, resp.text)
        if not matches:
            logger.warning("图片搜索: 未找到图片 URL")
            return None

        # 下载第一张图片
        img_url = matches[0]
        img_resp = requests.get(img_url, headers=headers, timeout=_TIMEOUT)
        if img_resp.status_code == 200 and img_resp.content:
            logger.info(f"搜图成功: {query}, 大小: {len(img_resp.content)} bytes")
            return img_resp.content
        else:
            logger.warning(f"图片下载失败: HTTP {img_resp.status_code}")
            return None
    except Exception as e:
        logger.warning(f"搜图异常: {e}")
        return None
