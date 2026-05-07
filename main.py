"""
苏格拉底 - 飞书学习机器人
主入口：启动飞书长连接，由 Coordinator 调度 Multi-Agent
内置自动重启机制：连接断开或异常退出后自动恢复
"""
import sys
import os
import time
import logging

# 将项目根目录加入 Python 路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 加载 .env 文件（本地开发用，云端通过环境变量配置）
_env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
if os.path.exists(_env_file):
    with open(_env_file) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ.setdefault(key.strip(), val.strip())

import config
from feishu.client import FeishuClient
from agents.coordinator import Coordinator

# 配置日志
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("苏格拉底")

# 每个用户一个 Coordinator 实例
_coordinators: dict[str, Coordinator] = {}


def get_coordinator(user_id: str) -> Coordinator:
    if user_id not in _coordinators:
        _coordinators[user_id] = Coordinator(user_id)
    return _coordinators[user_id]


def handle_message(user_id: str, text: str, message_id: str) -> str:
    """
    消息处理入口 - 由 Coordinator 统一调度
    """
    logger.info(f"处理消息: user={user_id}, text={text[:50]}")
    coordinator = get_coordinator(user_id)
    return coordinator.handle_message(text)


# 自动重启配置
MAX_RESTART_ATTEMPTS = 0  # 0 = 无限重试
RESTART_DELAY_BASE = 5    # 基础等待秒数
RESTART_DELAY_MAX = 60    # 最大等待秒数


def main():
    attempt = 0
    while True:
        attempt += 1
        start_time = time.time()
        try:
            logger.info("=" * 50)
            logger.info(f"苏格拉底学习Agent 启动 (第{attempt}次)")
            logger.info(f"学习领域: {config.LEARNING_DOMAIN}")
            logger.info(f"AI模型: {config.DEEPSEEK_MODEL}")
            logger.info(f"Agent架构: Coordinator → Socrates + Examiner + ProgressTracker")
            logger.info("=" * 50)

            # 创建飞书客户端并启动（阻塞）
            client = FeishuClient(message_handler=handle_message)
            client.start()

            # 如果 start() 正常返回（不应该），说明连接已断开
            logger.warning("飞书长连接已断开，准备自动重启...")

        except KeyboardInterrupt:
            logger.info("收到退出信号，服务停止")
            break
        except Exception as e:
            logger.error(f"服务异常退出: {e}", exc_info=True)

        # 如果连续运行超过5分钟，说明是偶发断开而非启动就崩，重置计数器
        run_duration = time.time() - start_time
        if run_duration > 300:
            logger.info(f"本次运行了 {run_duration:.0f} 秒，重置重启计数器")
            attempt = 0

        # 检查是否达到最大重试次数
        if MAX_RESTART_ATTEMPTS > 0 and attempt >= MAX_RESTART_ATTEMPTS:
            logger.error(f"已达到最大重启次数({MAX_RESTART_ATTEMPTS})，服务停止")
            break

        # 指数退避重启：5s → 10s → 20s → 40s → 60s(上限)
        delay = min(RESTART_DELAY_BASE * (2 ** (attempt - 1)), RESTART_DELAY_MAX)
        logger.info(f"等待 {delay} 秒后自动重启...")
        time.sleep(delay)


if __name__ == "__main__":
    main()
