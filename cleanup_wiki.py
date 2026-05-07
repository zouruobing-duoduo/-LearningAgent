"""删除飞书知识库中的空文档"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import config, lark_oapi as lark
from lark_oapi.api.wiki.v2 import *

client = lark.Client.builder().app_id(config.FEISHU_APP_ID).app_secret(config.FEISHU_APP_SECRET).build()

# 要删除的两个空文档 node_token
empty_tokens = [
    "IyujwrKXViBTDJkNE7Cciixanih",  # 第1次失败的空文档
    "IsIBwk7pni2YX0kzSbXcUF4Tnef",  # 第2次失败的空文档
]

for token in empty_tokens:
    req = DeleteSpaceNodeRequest.builder().space_id("7628530521119149241").node_token(token).build()
    resp = client.wiki.v2.space_node.delete(req)
    if resp.success():
        print(f"已删除: {token}")
    else:
        print(f"删除失败: {token}, code={resp.code}, msg={resp.msg}")

