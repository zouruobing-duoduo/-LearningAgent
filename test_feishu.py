"""最小化飞书长连接测试 - 排除代码问题"""
import logging
import lark_oapi as lark
from lark_oapi.api.im.v1 import *

# 开启所有日志
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s %(name)s %(levelname)s: %(message)s")

APP_ID = "cli_a954b51ad2b8dcd3"
APP_SECRET = "cNIwgCy4ZQFAnqP2mD3CjfsjNyq8lpsX"


def on_message(data: lark.im.v1.P2ImMessageReceiveV1):
    print("\n" + "=" * 50)
    print("!!! 收到消息事件 !!!")
    print(f"event: {data.event}")
    if data.event and data.event.message:
        msg = data.event.message
        print(f"type: {msg.message_type}, content: {msg.content}")
    print("=" * 50 + "\n")


def on_any_event(data):
    """通配符：捕获任何事件"""
    print("\n" + "!" * 50)
    print(f"!!! 收到未知事件: type={type(data)}, data={data}")
    print("!" * 50 + "\n")


event_handler = (
    lark.EventDispatcherHandler.builder("", "")
    .register_p2_im_message_receive_v1(on_message)
    .build()
)

cli = lark.ws.Client(
    APP_ID,
    APP_SECRET,
    event_handler=event_handler,
    log_level=lark.LogLevel.DEBUG,
)

print("\n" + "=" * 50)
print("启动最小化测试...")
print("请在飞书私聊给苏格拉底发消息")
print("=" * 50 + "\n")
cli.start()
