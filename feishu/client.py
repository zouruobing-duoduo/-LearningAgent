"""
飞书客户端
使用长连接（WebSocket）模式接收消息，无需公网服务器
"""
import json
import os
import time
import threading
import logging
from typing import Callable, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    CreateMessageRequest,
    CreateMessageRequestBody,
    ReplyMessageRequest,
    ReplyMessageRequestBody,
    DeleteMessageRequest,
    UpdateMessageRequest,
    UpdateMessageRequestBody,
    CreateImageRequest,
    CreateImageRequestBody,
)

import config

logger = logging.getLogger(__name__)

# 消息去重缓存文件
_DEDUP_FILE = os.path.join(config.DATA_DIR, "processed_messages.json")


class FeishuClient:
    """飞书客户端，封装消息收发和长连接"""

    def __init__(self, message_handler: Callable[[str, str, str], str]):
        """
        Args:
            message_handler: 消息处理回调函数
                接收参数: (user_id, message_text, message_id)
                返回: 回复文本
        """
        self._message_handler = message_handler
        self._processed_message_ids: set[str] = self._load_dedup_cache()  # 从文件恢复
        self._max_cache_size = 200  # 最多缓存200条消息ID

        # 并发控制：防止同一用户的多条消息并行处理导致旧回复后发
        self._user_locks: dict[str, threading.Lock] = {}  # 每用户一把锁
        self._user_msg_seq: dict[str, int] = {}  # 每用户最新消息序号
        self._global_lock = threading.Lock()  # 保护上面两个字典的访问

        # 创建 API 客户端（用于主动调用 API）
        self._api_client = (
            lark.Client.builder()
            .app_id(config.FEISHU_APP_ID)
            .app_secret(config.FEISHU_APP_SECRET)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # 创建事件处理器
        self._event_handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message_received)
            .build()
        )

        # 创建 WebSocket 长连接客户端
        self._ws_client = lark.ws.Client(
            config.FEISHU_APP_ID,
            config.FEISHU_APP_SECRET,
            event_handler=self._event_handler,
            log_level=lark.LogLevel.DEBUG,
        )

    def _on_message_received(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """接收到消息的回调处理"""
        logger.info(f"收到事件回调, data type: {type(data)}")
        try:
            event = data.event
            if event is None:
                logger.warning("event 为空")
                return
            message = event.message
            if message is None:
                logger.warning("message 为空")
                return
            logger.info(f"消息类型: {message.message_type}, content: {message.content}")

            # 只处理文本消息和富文本消息
            if message.message_type == "text":
                content = json.loads(message.content)
                text = content.get("text", "").strip()
            elif message.message_type == "post":
                # 富文本：提取所有文字内容
                content = json.loads(message.content)
                text_parts = []
                for line in content.get("content", []):
                    line_text = "".join(
                        item.get("text", "") for item in line if item.get("tag") == "text"
                    )
                    if line_text.strip():
                        text_parts.append(line_text.strip())
                text = "\n".join(text_parts)
            else:
                logger.info(f"忽略不支持的消息类型: type={message.message_type}")
                return

            if not text:
                return

            # 获取用户信息
            sender = event.sender
            user_id = sender.sender_id.open_id
            message_id = message.message_id
            chat_type = message.chat_type  # "p2p" 或 "group"

            # 消息去重：飞书长连接可能重复推送同一事件（包括重启后重新推送）
            if message_id in self._processed_message_ids:
                logger.info(f"跳过重复消息: {message_id}")
                return
            self._processed_message_ids.add(message_id)
            # 防止缓存无限增长
            if len(self._processed_message_ids) > self._max_cache_size:
                # 只保留最近的一半
                to_keep = list(self._processed_message_ids)[self._max_cache_size // 2:]
                self._processed_message_ids = set(to_keep)
            self._save_dedup_cache()

            # 群聊中需要@机器人才响应，去掉@前缀
            if chat_type == "group":
                # 去掉可能的 @机器人 前缀
                if text.startswith("@"):
                    # 格式可能是 @_user_1 xxx
                    parts = text.split(" ", 1)
                    text = parts[1] if len(parts) > 1 else ""
                    if not text:
                        return

            logger.info(f"收到消息: user={user_id}, text={text[:50]}")

            # 并发控制：获取用户锁 + 递增序号
            with self._global_lock:
                if user_id not in self._user_locks:
                    self._user_locks[user_id] = threading.Lock()
                self._user_msg_seq[user_id] = self._user_msg_seq.get(user_id, 0) + 1
                my_seq = self._user_msg_seq[user_id]
                user_lock = self._user_locks[user_id]

            # 获取用户锁，确保同一用户的消息串行处理
            with user_lock:
                # 再次检查：如果等待锁期间有更新的消息到达，放弃处理本条
                if self._user_msg_seq[user_id] != my_seq:
                    logger.info(f"放弃过期消息(等锁期间有新消息): {message_id}, seq={my_seq}")
                    return

                # 立即发送"思考中"状态提示
                thinking_msg_id = self._reply_message(message_id, "💭 思考中...")

                # 调用消息处理器
                reply_text = self._message_handler(user_id, text, message_id)

                # 处理完毕后检查：如果处理期间有更新的消息到达，放弃发送回复
                if self._user_msg_seq[user_id] != my_seq:
                    logger.info(f"放弃过期回复(处理期间有新消息): {message_id}, seq={my_seq}")
                    if thinking_msg_id:
                        self._delete_message(thinking_msg_id)
                    return

                # 用编辑消息替换"思考中"为实际内容（避免"撤回了一条消息"提示）
                if reply_text and thinking_msg_id:
                    # 检查回复是否包含图片标记
                    from core.reply_parser import parse_reply_with_images
                    has_images = bool(parse_reply_with_images(reply_text))
                    
                    if has_images:
                        # 有图片则必须删除思考消息，用富文本重新回复
                        self._delete_message(thinking_msg_id)
                        self._send_reply(message_id, reply_text)
                    else:
                        # 纯文本：直接编辑消息内容
                        updated = self._update_message(thinking_msg_id, reply_text)
                        if not updated:
                            # 编辑失败则删除思考中消息，重新回复
                            self._delete_message(thinking_msg_id)
                            self._send_reply(message_id, reply_text)
                elif reply_text:
                    self._send_reply(message_id, reply_text)
                elif thinking_msg_id:
                    self._delete_message(thinking_msg_id)

        except Exception as e:
            logger.error(f"处理消息失败: {e}", exc_info=True)

    def _reply_message(self, message_id: str, text: str) -> str | None:
        """回复消息，返回回复消息的 message_id"""
        try:
            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.message.reply(request)
            if not response.success():
                logger.error(
                    f"回复消息失败: code={response.code}, msg={response.msg}"
                )
                return None
            return response.data.message_id if response.data else None
        except Exception as e:
            logger.error(f"回复消息异常: {e}", exc_info=True)
            return None

    def _update_message(self, message_id: str, text: str) -> bool:
        """编辑已发送的消息内容（替代撤回+重发，避免'撤回了一条消息'提示）"""
        try:
            request = (
                UpdateMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    UpdateMessageRequestBody.builder()
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.message.update(request)
            if response.success():
                logger.info(f"编辑消息成功: {message_id}")
                return True
            else:
                logger.warning(f"编辑消息失败: code={response.code}, msg={response.msg}")
                return False
        except Exception as e:
            logger.warning(f"编辑消息异常: {e}")
            return False

    def _delete_message(self, message_id: str):
        """撤回/删除消息"""
        try:
            request = DeleteMessageRequest.builder().message_id(message_id).build()
            response = self._api_client.im.v1.message.delete(request)
            if not response.success():
                logger.debug(f"删除消息失败: code={response.code}, msg={response.msg}")
        except Exception as e:
            logger.debug(f"删除消息异常: {e}")

    def _upload_image(self, image_bytes: bytes) -> str | None:
        """上传图片到飞书，返回 image_key"""
        try:
            import io
            request = (
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(io.BytesIO(image_bytes))
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.image.create(request)
            if response.success() and response.data:
                image_key = response.data.image_key
                logger.info(f"图片上传成功: {image_key}")
                return image_key
            else:
                logger.warning(f"图片上传失败: code={response.code}, msg={response.msg}")
                return None
        except Exception as e:
            logger.warning(f"图片上传异常: {e}")
            return None

    def _reply_rich_message(self, message_id: str, content_parts: list) -> str | None:
        """
        使用富文本(post)格式回复消息，支持文本+图片混排。
        content_parts: [{"type": "text", "text": "..."}, {"type": "image", "image_key": "..."}]
        """
        try:
            # 构造飞书 post 富文本格式
            # post 格式: {"zh_cn": {"title": "", "content": [[{tag, ...}, ...], ...]}}
            lines = []
            current_line = []

            for part in content_parts:
                if part["type"] == "text":
                    # 文本可能包含换行，按换行分段
                    text_lines = part["text"].split("\n")
                    for i, tl in enumerate(text_lines):
                        if tl.strip():
                            current_line.append({"tag": "text", "text": tl})
                        if i < len(text_lines) - 1:
                            # 换行：结束当前行，开始新行
                            if current_line:
                                lines.append(current_line)
                                current_line = []
                            else:
                                lines.append([{"tag": "text", "text": ""}])
                elif part["type"] == "image":
                    # 图片单独成行
                    if current_line:
                        lines.append(current_line)
                        current_line = []
                    lines.append([{"tag": "img", "image_key": part["image_key"]}])

            # 处理最后一行
            if current_line:
                lines.append(current_line)

            if not lines:
                return None

            post_content = json.dumps({
                "zh_cn": {
                    "title": "",
                    "content": lines,
                }
            })

            request = (
                ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    ReplyMessageRequestBody.builder()
                    .msg_type("post")
                    .content(post_content)
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.message.reply(request)
            if not response.success():
                logger.error(f"富文本回复失败: code={response.code}, msg={response.msg}")
                return None
            return response.data.message_id if response.data else None
        except Exception as e:
            logger.error(f"富文本回复异常: {e}", exc_info=True)
            return None

    def _send_reply(self, message_id: str, reply_text: str):
        """
        智能回复：检测回复中是否包含图片标记，有则图文混排发送，否则纯文本。
        """
        try:
            from core.reply_parser import parse_reply_with_images
            parts = parse_reply_with_images(reply_text)

            if parts:
                # 有图片标记：上传图片并用富文本发送
                rich_parts = []
                for part in parts:
                    if part["type"] == "text":
                        rich_parts.append(part)
                    elif part["type"] == "image_bytes":
                        image_key = self._upload_image(part["data"])
                        if image_key:
                            rich_parts.append({"type": "image", "image_key": image_key})
                if rich_parts:
                    self._reply_rich_message(message_id, rich_parts)
                else:
                    # 所有图片上传失败，降级为纯文本
                    self._reply_message(message_id, reply_text)
            else:
                # 无图片标记，走原有纯文本逻辑
                self._reply_message(message_id, reply_text)
        except Exception as e:
            logger.warning(f"图文回复处理异常，降级为纯文本: {e}")
            self._reply_message(message_id, reply_text)

    def send_message(self, user_open_id: str, text: str):
        """主动发送消息给用户"""
        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(user_open_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                )
                .build()
            )
            response = self._api_client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    f"发送消息失败: code={response.code}, msg={response.msg}"
                )
        except Exception as e:
            logger.error(f"发送消息异常: {e}", exc_info=True)

    @property
    def api_client(self) -> lark.Client:
        """获取 API 客户端，供知识库等模块使用"""
        return self._api_client

    def _load_dedup_cache(self) -> set[str]:
        """从文件加载消息去重缓存"""
        try:
            if os.path.exists(_DEDUP_FILE):
                with open(_DEDUP_FILE, "r", encoding="utf-8") as f:
                    ids = json.load(f)
                logger.info(f"恢复消息去重缓存: {len(ids)} 条")
                return set(ids)
        except Exception as e:
            logger.error(f"加载消息去重缓存失败: {e}")
        return set()

    def _save_dedup_cache(self):
        """保存消息去重缓存到文件"""
        try:
            with open(_DEDUP_FILE, "w", encoding="utf-8") as f:
                json.dump(list(self._processed_message_ids), f)
        except Exception as e:
            logger.error(f"保存消息去重缓存失败: {e}")

    def start(self):
        """启动长连接，阻塞运行"""
        logger.info("苏格拉底飞书机器人启动中...")
        logger.info("使用长连接模式（WebSocket），无需公网服务器")
        self._ws_client.start()
