"""
状态管理模块

使用 SQLite 追踪已处理的邮件，避免重复翻译和发送。
"""

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from src.config import STATE_DB_PATH

logger = logging.getLogger(__name__)

# 建表 SQL
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS processed_emails (
    gmail_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""


class StateManager:
    """邮件处理状态管理器。"""

    def __init__(self, db_path: str = None):
        self.db_path = str(db_path or STATE_DB_PATH)
        self._ensure_db()

    def _ensure_db(self):
        """确保数据库和表已创建。"""
        db_file = Path(self.db_path)
        db_file.parent.mkdir(parents=True, exist_ok=True)

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(CREATE_TABLE_SQL)
            conn.commit()

    def is_processed(self, gmail_id: str) -> bool:
        """
        检查某封邮件是否已经处理过。

        Args:
            gmail_id: Gmail 邮件 ID

        Returns:
            True 表示已处理
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM processed_emails WHERE gmail_id = ?",
                (gmail_id,),
            )
            return cursor.fetchone() is not None

    def mark_processed(self, gmail_id: str, subject: str):
        """
        标记邮件为已处理。

        Args:
            gmail_id: Gmail 邮件 ID
            subject: 邮件主题
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO processed_emails (gmail_id, subject) VALUES (?, ?)",
                (gmail_id, subject),
            )
            conn.commit()
        logger.info("标记已处理: %s - %s", gmail_id[:20], subject[:60])

    def get_processed_count(self) -> int:
        """获取已处理邮件总数。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(*) FROM processed_emails")
            return cursor.fetchone()[0]

    def get_last_processed_time(self) -> Optional[datetime]:
        """获取最近一次处理的时间。"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT processed_at FROM processed_emails ORDER BY processed_at DESC LIMIT 1"
            )
            row = cursor.fetchone()
            if row:
                return datetime.fromisoformat(row[0])
            return None

    def filter_unprocessed(self, messages: list[dict]) -> list[dict]:
        """
        从邮件列表中过滤出尚未处理的邮件。

        Args:
            messages: Gmail API 返回的邮件列表

        Returns:
            未处理的邮件列表
        """
        unprocessed = []
        for msg in messages:
            gmail_id = msg.get("id", "")
            if not self.is_processed(gmail_id):
                unprocessed.append(msg)
            else:
                logger.debug("跳过已处理: %s", gmail_id[:20])

        logger.info(
            "过滤结果: %d 封邮件, %d 已处理, %d 待处理",
            len(messages), len(messages) - len(unprocessed), len(unprocessed),
        )
        return unprocessed
