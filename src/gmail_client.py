"""
Gmail API 客户端

提供 Gmail API 认证、获取邮件列表、获取邮件完整内容、以及发送邮件的功能。
"""

import base64
import logging
import pickle
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from src.config import (
    GOOGLE_CREDENTIALS_PATH,
    GOOGLE_TOKEN_PATH,
    GMAIL_SCOPES,
    GMAIL_USER_EMAIL,
    BRIEFING_SEARCH_QUERY,
)

logger = logging.getLogger(__name__)


def get_gmail_service():
    """
    获取已认证的 Gmail API 服务。

    首次运行时打开浏览器进行 OAuth 认证，后续使用缓存的 token。
    """
    creds = None

    # 从缓存加载 token
    token_path = Path(GOOGLE_TOKEN_PATH)
    if token_path.exists():
        with open(token_path, "rb") as token_file:
            creds = pickle.load(token_file)

    # 如果没有有效凭证，进行 OAuth 认证
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Token 已过期，正在刷新...")
            creds.refresh(Request())
        else:
            creds_path = Path(GOOGLE_CREDENTIALS_PATH)
            if not creds_path.exists():
                raise FileNotFoundError(
                    f"Google OAuth 凭证文件未找到: {creds_path}\n"
                    "请从 Google Cloud Console 下载 credentials.json 并放到 data/ 目录下。"
                )
            logger.info("开始 OAuth 认证流程...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(creds_path), GMAIL_SCOPES
            )
            creds = flow.run_local_server(port=8080)

        # 保存 token 到缓存
        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "wb") as token_file:
            pickle.dump(creds, token_file)
        logger.info(f"Token 已保存到 {token_path}")

    return build("gmail", "v1", credentials=creds)


def list_briefing_emails(service, max_results: int = 50) -> list[dict]:
    """
    搜索标题中含 "Briefing" 的邮件。

    Args:
        service: Gmail API 服务实例
        max_results: 最多返回的邮件数量

    Returns:
        邮件列表，每封邮件包含 id 和 threadId
    """
    try:
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                q=BRIEFING_SEARCH_QUERY,
                maxResults=max_results,
            )
            .execute()
        )
        messages = results.get("messages", [])
        logger.info(f"找到 {len(messages)} 封 Briefing 邮件")
        return messages
    except HttpError as e:
        logger.error(f"搜索邮件失败: {e}")
        raise


def get_email_mime(service, message_id: str) -> Optional[str]:
    """
    获取邮件的完整 raw MIME 内容。

    Args:
        service: Gmail API 服务实例
        message_id: 邮件 ID

    Returns:
        base64 编码的邮件 raw 内容（URL-safe），不含换行符
    """
    try:
        message = (
            service.users()
            .messages()
            .get(
                userId="me",
                id=message_id,
                format="raw",
            )
            .execute()
        )
        return message.get("raw")
    except HttpError as e:
        logger.error(f"获取邮件 {message_id} 失败: {e}")
        return None


def send_email(
    service,
    to: str,
    subject: str,
    html_body: str,
    in_reply_to: Optional[str] = None,
) -> Optional[str]:
    """
    发送 HTML 格式邮件。

    Args:
        service: Gmail API 服务实例
        to: 收件人邮箱
        subject: 邮件主题
        html_body: HTML 格式邮件正文
        in_reply_to: 原始邮件 Message-ID（用于关联回复）

    Returns:
        发送成功返回邮件 ID，失败返回 None
    """
    try:
        message = MIMEText(html_body, "html", "utf-8")
        message["To"] = to
        message["From"] = GMAIL_USER_EMAIL
        message["Subject"] = subject

        # 保留原始邮件的关联信息
        if in_reply_to:
            message["In-Reply-To"] = in_reply_to
            message["References"] = in_reply_to

        # 编码为 base64 URL-safe
        raw_bytes = message.as_bytes()
        raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("utf-8")

        sent = (
            service.users()
            .messages()
            .send(
                userId="me",
                body={"raw": raw_b64},
            )
            .execute()
        )

        logger.info(f"邮件已发送: {subject} -> {to}, id={sent.get('id')}")
        return sent.get("id")
    except HttpError as e:
        logger.error(f"发送邮件失败: {e}")
        return None
