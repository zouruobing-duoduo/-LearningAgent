"""测试：用机器人主动发消息"""
import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import *

APP_ID = "cli_a954b51ad2b8dcd3"
APP_SECRET = "cNIwgCy4ZQFAnqP2mD3CjfsjNyq8lpsX"

client = (
    lark.Client.builder()
    .app_id(APP_ID)
    .app_secret(APP_SECRET)
    .log_level(lark.LogLevel.DEBUG)
    .build()
)

# 先列出机器人最近的会话，找到用户 open_id
print("=== 获取机器人会话列表 ===")
import requests

# 获取 tenant_access_token
token_resp = requests.post(
    "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
    json={"app_id": APP_ID, "app_secret": APP_SECRET},
)
token_data = token_resp.json()
print(f"token resp: {token_data}")
token = token_data.get("tenant_access_token", "")

if token:
    headers = {"Authorization": f"Bearer {token}"}

    # 1. 获取机器人信息
    print("\n=== 机器人信息 ===")
    bot_resp = requests.get(
        "https://open.feishu.cn/open-apis/bot/v3/info",
        headers=headers,
    )
    print(json.dumps(bot_resp.json(), ensure_ascii=False, indent=2))

    # 2. 直接发消息到 chat_id
    chat_id = "oc_a093d8ee60a35534ed19374037931340"
    print(f"\n=== 发送消息到 chat: {chat_id} ===")
    send_resp = requests.post(
        "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id",
        headers={**headers, "Content-Type": "application/json; charset=utf-8"},
        json={
            "receive_id": chat_id,
            "msg_type": "text",
            "content": json.dumps({"text": "你好！我是苏格拉底机器人，这是一条测试消息 🎉"}),
        },
    )
    print(json.dumps(send_resp.json(), ensure_ascii=False, indent=2))
