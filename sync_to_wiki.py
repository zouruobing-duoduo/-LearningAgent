"""
将开发经验文档同步到飞书知识库
使用飞书 Wiki + Docx API
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import json
import logging
import lark_oapi as lark
from lark_oapi.api.wiki.v2 import *
from lark_oapi.api.docx.v1 import *
import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

client = (
    lark.Client.builder()
    .app_id(config.FEISHU_APP_ID)
    .app_secret(config.FEISHU_APP_SECRET)
    .log_level(lark.LogLevel.INFO)
    .build()
)


def list_wiki_spaces():
    """列出所有知识空间"""
    request = ListSpaceRequest.builder().build()
    response = client.wiki.v2.space.list(request)
    if not response.success():
        logger.error(f"获取知识空间失败: code={response.code}, msg={response.msg}")
        return []
    items = response.data.items or []
    spaces = []
    for s in items:
        spaces.append({"space_id": s.space_id, "name": s.name})
        logger.info(f"  知识空间: {s.name} (id={s.space_id})")
    return spaces


def find_existing_node(space_id: str, title: str):
    """查找知识空间中是否已存在同名文档，返回 obj_token"""
    request = ListSpaceNodeRequest.builder().space_id(space_id).build()
    response = client.wiki.v2.space_node.list(request)
    if not response.success():
        return None
    for node in (response.data.items or []):
        if node.title == title:
            logger.info(f"找到已有文档: {title} (obj_token={node.obj_token})")
            return node.obj_token
    return None


def create_wiki_node(space_id: str, title: str):
    """在知识空间中创建一个文档节点"""
    node = Node.builder() \
        .obj_type("docx") \
        .node_type("origin") \
        .title(title) \
        .build()

    request = CreateSpaceNodeRequest.builder() \
        .space_id(space_id) \
        .request_body(node) \
        .build()

    response = client.wiki.v2.space_node.create(request)
    if not response.success():
        logger.error(f"创建知识库节点失败: code={response.code}, msg={response.msg}")
        return None

    node_data = response.data.node
    obj_token = node_data.obj_token
    logger.info(f"创建文档成功: title={title}, obj_token={obj_token}")
    return obj_token


def add_text_block(document_id: str, block_id: str, text: str, style: int = 0):
    """向文档添加文本块
    style: 0=正文, 1=H1, 2=H2, 3=H3, 4=H4
    """
    text_element = TextElement.builder() \
        .text_run(TextRun.builder().content(text).build()) \
        .build()

    block_type = 2  # text
    if style >= 1:
        block_type = style + 2  # 3=H1, 4=H2, 5=H3, 6=H4

    text_style = None
    if style == 0:
        block_type = 2  # paragraph

    block = Block.builder() \
        .block_type(block_type) \
        .text(Text.builder().elements([text_element]).build()) \
        .build()

    request = CreateDocumentBlockChildrenRequest.builder() \
        .document_id(document_id) \
        .block_id(block_id) \
        .request_body(
            CreateDocumentBlockChildrenRequestBody.builder()
            .children([block])
            .build()
        ) \
        .build()

    response = client.docx.v1.document_block_children.create(request)
    if not response.success():
        logger.error(f"添加文本块失败: code={response.code}, msg={response.msg}")
        return False
    return True


def add_blocks_batch(document_id: str, block_id: str, blocks: list):
    """批量添加多个块"""
    request = CreateDocumentBlockChildrenRequest.builder() \
        .document_id(document_id) \
        .block_id(block_id) \
        .request_body(
            CreateDocumentBlockChildrenRequestBody.builder()
            .children(blocks)
            .build()
        ) \
        .build()

    response = client.docx.v1.document_block_children.create(request)
    if not response.success():
        logger.error(f"批量添加块失败: code={response.code}, msg={response.msg}")
        return False
    return True


def make_text_elements(text: str, bold: bool = False):
    """构建文本元素列表"""
    style = None
    if bold:
        style = TextElementStyle.builder().bold(True).build()
    elem = TextElement.builder() \
        .text_run(TextRun.builder().content(text).text_element_style(style).build()) \
        .build()
    return [elem]


def make_heading_block(text: str, level: int = 1):
    """构建标题块 level: 1-9"""
    elements = make_text_elements(text)
    text_obj = Text.builder().elements(elements).build()
    b = Block.builder().block_type(level + 2)  # heading1=3, heading2=4, heading3=5
    # 使用对应的 heading 方法
    if level == 1:
        b = b.heading1(text_obj)
    elif level == 2:
        b = b.heading2(text_obj)
    elif level == 3:
        b = b.heading3(text_obj)
    elif level == 4:
        b = b.heading4(text_obj)
    return b.build()


def make_paragraph_block(text: str):
    """构建普通段落"""
    elements = make_text_elements(text)
    text_obj = Text.builder().elements(elements).build()
    return Block.builder().block_type(2).text(text_obj).build()


def make_bullet_block(text: str):
    """构建无序列表项"""
    elements = make_text_elements(text)
    text_obj = Text.builder().elements(elements).build()
    return Block.builder().block_type(12).bullet(text_obj).build()


def make_ordered_block(text: str):
    """构建有序列表项"""
    elements = make_text_elements(text)
    text_obj = Text.builder().elements(elements).build()
    return Block.builder().block_type(13).ordered(text_obj).build()


def parse_md_and_write(document_id: str, block_id: str, md_content: str):
    """解析 markdown 内容并写入飞书文档"""
    lines = md_content.strip().split("\n")
    blocks = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        if stripped == "---":
            continue  # 跳过分割线，飞书文档用标题自然分隔
        elif stripped.startswith("# "):
            blocks.append(make_heading_block(stripped[2:], level=1))
        elif stripped.startswith("## "):
            blocks.append(make_heading_block(stripped[3:], level=2))
        elif stripped.startswith("### "):
            blocks.append(make_heading_block(stripped[4:], level=3))
        elif stripped.startswith("> "):
            blocks.append(make_paragraph_block(stripped[2:]))
        elif stripped.startswith("- "):
            clean = stripped[2:].replace("**", "")
            blocks.append(make_bullet_block(clean))
        elif len(stripped) > 1 and stripped[0].isdigit() and ". " in stripped[:4]:
            content = stripped.split(". ", 1)[1] if ". " in stripped else stripped
            blocks.append(make_ordered_block(content.replace("**", "")))
        else:
            clean = stripped.replace("**", "")
            blocks.append(make_paragraph_block(clean))

        # 飞书 API 每次最多50个块，分批发送
        if len(blocks) >= 45:
            if not add_blocks_batch(document_id, block_id, blocks):
                return False
            blocks = []

    if blocks:
        return add_blocks_batch(document_id, block_id, blocks)
    return True


def main():
    # 1. 获取知识空间
    logger.info("正在获取飞书知识空间列表...")
    spaces = list_wiki_spaces()
    if not spaces:
        logger.error("未找到任何知识空间，请先在飞书中创建一个知识库")
        logger.info("提示：需要在飞书开放平台为应用开通 wiki 相关权限")
        return

    # 使用第一个知识空间
    space = spaces[0]
    space_id = space["space_id"]
    logger.info(f"使用知识空间: {space['name']} ({space_id})")

    # 2. 查找已有文档或创建新文档
    title = "苏格拉底学习Agent - 开发经验沉淀"
    obj_token = find_existing_node(space_id, title)
    if obj_token:
        logger.info(f"文档已存在，将覆盖内容: {obj_token}")
    else:
        logger.info(f"正在创建文档: {title}")
        obj_token = create_wiki_node(space_id, title)
        if not obj_token:
            return

    # 3. 读取本地经验文档
    md_path = os.path.join(os.path.dirname(__file__), "docs", "experience.md")
    with open(md_path, "r", encoding="utf-8") as f:
        md_content = f.read()

    # 4. 写入文档内容
    logger.info("正在写入文档内容...")
    success = parse_md_and_write(obj_token, obj_token, md_content)

    if success:
        logger.info(f"文档已成功同步到飞书知识库!")
        logger.info(f"知识空间: {space['name']}")
        logger.info(f"文档标题: {title}")
    else:
        logger.error("文档内容写入失败")


if __name__ == "__main__":
    main()
