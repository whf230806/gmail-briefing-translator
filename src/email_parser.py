"""
邮件解析模块

解析 Gmail API 返回的 raw MIME 内容，提取 HTML 和纯文本，
处理 multipart/related 内嵌图片。
"""

import base64
import email
import logging
from email.message import Message
from typing import Optional

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class ParsedEmail:
    """解析后的邮件数据类。"""

    def __init__(
        self,
        message_id: str,
        subject: str,
        from_addr: str,
        date: str,
        html_body: str,
        plain_body: str,
        images: dict[str, bytes],  # cid -> bytes
    ):
        self.message_id = message_id
        self.subject = subject
        self.from_addr = from_addr
        self.date = date
        self.html_body = html_body
        self.plain_body = plain_body
        self.images = images

    def has_html(self) -> bool:
        return bool(self.html_body and self.html_body.strip())

    def has_plain(self) -> bool:
        return bool(self.plain_body and self.plain_body.strip())


def parse_raw_email(raw_mime: str) -> Optional[ParsedEmail]:
    """
    解析 raw MIME 邮件内容。

    Args:
        raw_mime: Gmail API 返回的 base64 URL-safe 编码 raw 内容

    Returns:
        ParsedEmail 对象，解析失败返回 None
    """
    try:
        # 解码 base64（URL-safe -> 标准 base64）
        raw_bytes = base64.urlsafe_b64decode(raw_mime)
        msg = email.message_from_bytes(raw_bytes)

        message_id = msg.get("Message-ID", "")
        subject = _decode_header(msg.get("Subject", "无主题"))
        from_addr = _decode_header(msg.get("From", ""))
        date = msg.get("Date", "")

        html_body = ""
        plain_body = ""
        images: dict[str, bytes] = {}

        # 遍历 MIME 各部分（用列表引用传递可变状态）
        html_body_ref = [""]
        plain_body_ref = [""]
        _walk_parts(msg, images, html_body_ref, plain_body_ref)

        html_body = html_body_ref[0]
        plain_body = plain_body_ref[0]

        if not html_body and not plain_body:
            logger.warning("邮件 %s 未找到 text/html 或 text/plain 部分", message_id)
            return None

        logger.info(
            "解析邮件成功: subject=%s, html_len=%d, plain_len=%d, images=%d",
            subject,
            len(html_body),
            len(plain_body),
            len(images),
        )

        return ParsedEmail(
            message_id=message_id,
            subject=subject,
            from_addr=from_addr,
            date=date,
            html_body=html_body,
            plain_body=plain_body,
            images=images,
        )

    except Exception as e:
        logger.error("解析邮件失败: %s", e)
        return None


def _walk_parts(
    part: Message,
    images: dict[str, bytes],
    html_body_ref: list[str],
    plain_body_ref: list[str],
):
    """
    递归遍历 MIME 树，提取 HTML、纯文本和图片。

    使用列表引用 (list) 来实现闭包内可变状态。
    """
    content_type = part.get_content_type()

    if part.is_multipart():
        for sub_part in part.get_payload():
            if isinstance(sub_part, Message):
                _walk_parts(sub_part, images, html_body_ref, plain_body_ref)
    else:
        payload = part.get_payload(decode=True)
        if payload is None:
            return

        # 提取 HTML 正文
        if content_type == "text/html" and not html_body_ref[0]:
            html_body_ref[0] = _decode_payload(part, payload)

        # 提取纯文本正文
        elif content_type == "text/plain" and not plain_body_ref[0]:
            plain_body_ref[0] = _decode_payload(part, payload)

        # 提取内嵌图片（通过 Content-ID 引用）
        elif content_type.startswith("image/"):
            content_id = part.get("Content-ID", "").strip("<>")
            if content_id:
                logger.debug("提取内嵌图片: cid=%s, type=%s, size=%d",
                             content_id, content_type, len(payload))
                images[content_id] = payload
            else:
                # 有些图片通过 Content-Location 引用
                location = part.get("Content-Location", "")
                if location:
                    images[location] = payload


def _decode_payload(part: Message, payload: bytes) -> str:
    """
    用 MIME 部分声明的字符集解码 payload。
    对 Python 不认识的字符集回退到 utf-8（replace），避免 LookupError 崩溃。
    """
    charset = part.get_content_charset() or "utf-8"
    try:
        return payload.decode(charset, errors="replace")
    except (LookupError, ValueError):
        # 字符集不被 Python 支持，回退到 utf-8
        logger.debug("字符集 %s 不支持，回退 utf-8", charset)
        return payload.decode("utf-8", errors="replace")


def _decode_header(header_value: str) -> str:
    """解码 MIME 编码的邮件头（如 =?UTF-8?B?...?=）。"""
    decoded_parts = email.header.decode_header(header_value)
    result = []
    for part, charset in decoded_parts:
        if isinstance(part, bytes):
            charset = charset or "utf-8"
            result.append(part.decode(charset, errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def embed_images_in_html(html_body: str, images: dict[str, bytes]) -> str:
    """
    将内嵌图片 (cid:) 替换为 base64 data URI。

    这样可以确保邮件中的图片不依赖原始邮件存储，
    在转发/发送时能正常显示。

    Args:
        html_body: 原始 HTML
        images: cid -> bytes 的图片字典

    Returns:
        替换后的 HTML（图片内嵌为 base64 data URI）
    """
    if not html_body or not images:
        return html_body

    soup = BeautifulSoup(html_body, "html.parser")

    for img_tag in soup.find_all("img"):
        src = img_tag.get("src", "")
        # 处理 cid:引用
        if src.startswith("cid:"):
            cid = src[4:]
            if cid in images:
                img_data = images[cid]
                content_type = _infer_image_type(img_data)
                data_uri = f"data:{content_type};base64,{base64.b64encode(img_data).decode('ascii')}"
                img_tag["src"] = data_uri
                logger.debug("嵌入图片: cid=%s -> data URI", cid)
        # 处理相对 Content-Location 引用
        elif src in images:
            img_data = images[src]
            content_type = _infer_image_type(img_data)
            data_uri = f"data:{content_type};base64,{base64.b64encode(img_data).decode('ascii')}"
            img_tag["src"] = data_uri
            logger.debug("嵌入图片: location=%s -> data URI", src)

    return str(soup)


def _infer_image_type(data: bytes) -> str:
    """通过文件头魔数推断图片 MIME 类型。"""
    if data[:4] == b"\x89PNG":
        return "image/png"
    if data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if data[:6] == b"GIF87a" or data[:6] == b"GIF89a":
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:4] == b"<svg":
        return "image/svg+xml"
    return "image/png"  # 默认
