"""
苏格拉底学习Agent - 配置文件
所有敏感信息从环境变量读取，不硬编码
"""
import os

# ========== 飞书应用配置 ==========
FEISHU_APP_ID = os.environ.get("FEISHU_APP_ID", "")
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")

# 飞书知识库配置
FEISHU_WIKI_SPACE_ID = os.environ.get("FEISHU_WIKI_SPACE_ID", "7628530521119149241")

# ========== DeepSeek 配置 ==========
DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
DEEPSEEK_BASE_URL = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
DEEPSEEK_MAX_TOKENS = int(os.environ.get("DEEPSEEK_MAX_TOKENS", "2000"))
DEEPSEEK_TEMPERATURE = float(os.environ.get("DEEPSEEK_TEMPERATURE", "0.7"))

# ========== 学习配置 ==========
LEARNING_DOMAIN = "世界万物原理"  # 不限于物理，包括数学、物理、化学、经济等

# ========== 数据存储 ==========
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PROGRESS_FILE = os.path.join(DATA_DIR, "progress.json")
CONVERSATION_DIR = os.path.join(DATA_DIR, "conversations")
USER_PROFILE_FILE = os.path.join(DATA_DIR, "user_profile.json")
CHROMA_DB_DIR = os.path.join(DATA_DIR, "chroma_db")
TEMP_IMAGE_DIR = os.path.join(DATA_DIR, "temp_images")

os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONVERSATION_DIR, exist_ok=True)
os.makedirs(CHROMA_DB_DIR, exist_ok=True)
os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)

# ========== ChromaDB 向量数据库 ==========
CHROMA_COLLECTION_NAME = "socrates_memory"

# ========== 日志 ==========
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
