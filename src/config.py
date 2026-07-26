"""
配置加载模块

从 .env 文件和系统环境变量加载所有配置项。
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件（项目根目录）
_project_root = Path(__file__).parent.parent
_dotenv_path = _project_root / ".env"
load_dotenv(_dotenv_path, override=False)

# Gmail 配置
GMAIL_USER_EMAIL = os.getenv("GMAIL_USER_EMAIL", "")

# DeepSeek API 配置
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v4-pro")
DEEPSEEK_BASE_URL = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")

# Google OAuth 配置
GOOGLE_CREDENTIALS_PATH = os.getenv(
    "GOOGLE_CREDENTIALS_PATH",
    str(_project_root / "data" / "credentials.json")
)
GOOGLE_TOKEN_PATH = os.getenv(
    "GOOGLE_TOKEN_PATH",
    str(_project_root / "data" / "token.pickle")
)

# 状态数据库
STATE_DB_PATH = os.getenv(
    "STATE_DB_PATH",
    str(_project_root / "data" / "state.db")
)

# Gmail API 权限范围
GMAIL_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",   # 读取邮件
    "https://www.googleapis.com/auth/gmail.send",        # 发送邮件
]

# 日志配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = _project_root / "logs"

# 调度配置（北京时间）
SCHEDULE_WINDOWS = [
    ("05:00", "06:30"),   # 早上 5:00-6:30
    ("17:00", "18:30"),   # 下午 17:00-18:30
]
SCHEDULE_INTERVAL_MINUTES = 10  # 每 10 分钟一次
TIMEZONE = "Asia/Shanghai"

# 邮件搜索条件（仅最近7天，排除自己发送的翻译邮件避免无限循环）
TRANSLATION_MARKER = "[中文翻译]"
BRIEFING_SEARCH_QUERY = 'subject:"Briefing" newer_than:7d -subject:"[中文翻译]"'

# DeepSeek API 调用间隔（秒）—— 在每次 API 请求之间暂停，避免触发速率限制
# 批量翻译批次之间的间隔
DEEPSEEK_BATCH_INTERVAL = float(os.getenv("DEEPSEEK_BATCH_INTERVAL", "2.0"))
# 逐段翻译时每段之间的间隔（回退方案调用更密集，间隔适当加大）
DEEPSEEK_SEGMENT_INTERVAL = float(os.getenv("DEEPSEEK_SEGMENT_INTERVAL", "1.5"))


def validate() -> list[str]:
    """验证必需配置是否存在，返回缺失项列表。"""
    missing = []
    if not GMAIL_USER_EMAIL:
        missing.append("GMAIL_USER_EMAIL")
    if not DEEPSEEK_API_KEY:
        missing.append("DEEPSEEK_API_KEY")
    return missing
