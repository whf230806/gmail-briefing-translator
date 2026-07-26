"""
HTML 处理模块

解析 HTML 邮件正文，提取段落级文本，在每段英文后插入中文翻译，
保留所有图片和格式。
"""

import logging
import re
from typing import Optional

from bs4 import BeautifulSoup, NavigableString, Tag

from src.translator import translate_batch

logger = logging.getLogger(__name__)

# 视为段落级元素的 HTML 标签
BLOCK_TAGS = {"p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li", "td", "th"}

# 不需要翻译的标签
SKIP_TAGS = {
    "img", "br", "hr", "style", "script", "code", "pre", "table",
    "ul", "ol", "a", "span", "strong", "em", "b", "i", "u",
}

# 最小文本长度（字符数太少的不翻译）
MIN_TEXT_LENGTH = 3

# 翻译段落的样式（蓝色字体，稍小字号以区分）
TRANSLATION_STYLE = (
    "color: #2563eb; "
    "font-size: 0.95em; "
    "margin-top: 4px; "
    "margin-bottom: 12px; "
    "padding-left: 8px; "
    "border-left: 2px solid #93c5fd;"
)


def process_html(html_body: str) -> str:
    """
    处理 HTML 邮件正文：在每段英文后插入中文翻译。

    Args:
        html_body: 原始 HTML

    Returns:
        处理后的 HTML（中英对照，图片保留）
    """
    if not html_body or not html_body.strip():
        return html_body

    soup = BeautifulSoup(html_body, "html.parser")

    # 找到所有需要翻译的文本元素
    text_elements = _find_translatable_elements(soup)

    if not text_elements:
        logger.info("HTML 中未找到需要翻译的文本段落")
        # 即使没有可翻译段落，也只返回 body 内容，避免外层重复包裹
        return _extract_body_inner(soup)

    logger.info("找到 %d 个文本段落需要翻译", len(text_elements))

    # 提取纯文本
    plain_texts = [_extract_plain_text(el) for el in text_elements]

    # 批量翻译
    translations = translate_batch(plain_texts)

    # 在每个原文元素后插入翻译
    for element, original_text, translation in zip(text_elements, plain_texts, translations):
        if translation and translation.strip():
            _insert_translation(element, translation)

    # 只返回 body 内部内容，避免 <html>/<body> 在外层包裹时重复嵌套
    return _extract_body_inner(soup)


def _extract_body_inner(soup: BeautifulSoup) -> str:
    """
    提取 body 标签的内部 HTML（不含 <body> 本身）。
    如果没有 body 标签，返回整个 soup 的字符串形式。
    """
    if soup.body:
        # 拼接 body 的所有子节点
        return "".join(str(child) for child in soup.body.children)
    return str(soup)


def process_plain_text(plain_body: str) -> str:
    """
    处理纯文本邮件：按段落分割，每段后插入翻译，
    返回 HTML 格式的中英对照文本。

    Args:
        plain_body: 纯文本邮件正文

    Returns:
        HTML 格式的中英对照文本
    """
    if not plain_body or not plain_body.strip():
        return ""

    # 按空行分割段落
    paragraphs = _split_plain_paragraphs(plain_body)

    # 按连续换行分割段落（双换行 -> 新段落）
    non_empty = [(i, p) for i, p in enumerate(paragraphs) if p.strip()]

    if not non_empty:
        return plain_body

    indices = [i for i, _ in non_empty]
    texts = [p for _, p in non_empty]

    translations = translate_batch(texts)

    # 构建映射
    translation_map = {}
    for pos, idx in enumerate(indices):
        if pos < len(translations) and translations[pos]:
            translation_map[idx] = translations[pos]

    # 构建 HTML
    html_parts = []
    for i, para in enumerate(paragraphs):
        if para.strip():
            # 原文段落
            html_parts.append(
                f'<p style="margin-bottom: 4px;">'
                f'{_escape_html(para)}</p>'
            )
            # 中文翻译
            if i in translation_map:
                html_parts.append(
                    f'<p style="{TRANSLATION_STYLE}">'
                    f'{_escape_html(translation_map[i])}</p>'
                )
        else:
            # 空行保留间距
            html_parts.append('<p style="margin: 12px 0;">&nbsp;</p>')

    return "\n".join(html_parts)


def _find_translatable_elements(soup: BeautifulSoup) -> list[Tag]:
    """
    在 HTML DOM 树中查找需要翻译的块级文本元素。

    遍历 body 内的直接子元素，找到包含有意义文本内容的块级元素。
    跳过图片、链接容器、代码块等。
    """
    elements = []

    # 优先在 body 中查找
    root = soup.body if soup.body else soup

    for child in root.descendants:
        if not isinstance(child, Tag):
            continue

        tag_name = child.name.lower() if child.name else ""

        # 跳过不需要翻译的标签
        if tag_name in SKIP_TAGS:
            continue

        # 只处理块级元素
        if tag_name not in BLOCK_TAGS:
            continue

        # 跳过长文本的父容器（如整个 article 被 div 包裹）
        # 如果当前元素内部还有块级子元素，则跳过，让子元素被单独处理
        child_block_tags = [
            c for c in child.descendants
            if isinstance(c, Tag) and c.name and c.name.lower() in BLOCK_TAGS
        ]
        if len(child_block_tags) > 0:
            # 该元素内部有块级子标签，跳过它，让子标签被单独发现
            continue

        text = _extract_plain_text(child)
        if text and len(text.strip()) >= MIN_TEXT_LENGTH:
            elements.append(child)

    return elements


def _extract_plain_text(element: Tag) -> str:
    """
    从 HTML 元素中提取纯文本（保留有意义的空白）。

    移除内联标签（<a>, <strong> 等）但保留其文本。
    """
    if not element:
        return ""
    text = element.get_text(separator=" ", strip=True)
    # 规范化空白
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _insert_translation(element: Tag, translation: str):
    """
    在原始 HTML 元素之后插入翻译段落。

    Args:
        element: 原始 BeautifulSoup Tag 元素
        translation: 中文翻译文本
    """
    trans_tag = BeautifulSoup(
        f'<p style="{TRANSLATION_STYLE}">{translation}</p>',
        "html.parser",
    )
    element.insert_after(trans_tag)


def _split_plain_paragraphs(text: str) -> list[str]:
    """按空行将纯文本拆分为段落。"""
    # 先标准化换行
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # 按双换行拆分
    parts = re.split(r"\n\s*\n", text)
    # 单换行替换为空格（保持同一段落连贯性）
    return [re.sub(r"\n", " ", p).strip() for p in parts]


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，同时保留换行为 <br>。"""
    text = text.replace("&", "&amp;")
    text = text.replace("<", "&lt;")
    text = text.replace(">", "&gt;")
    text = text.replace('"', "&quot;")
    return text
