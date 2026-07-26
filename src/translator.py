"""
翻译模块

调用 DeepSeek API，将英文文本翻译为中文。
支持批量翻译：通过 JSON 模式一次性翻译多个段落，保持段落对应关系；
若批量失败则自动回退到逐段翻译，保证结果可靠。
"""

import json
import logging
import math
import time
from typing import Optional

import requests

from src.config import (
    DEEPSEEK_API_KEY,
    DEEPSEEK_MODEL,
    DEEPSEEK_BASE_URL,
    DEEPSEEK_BATCH_INTERVAL,
    DEEPSEEK_SEGMENT_INTERVAL,
)

logger = logging.getLogger(__name__)

# 翻译系统提示词
SYSTEM_PROMPT = (
    "你是一个专业的英中翻译。请将用户提供的英文段落翻译成中文。要求：\n"
    "1. 保持专业术语的准确性，尤其是金融、科技领域术语；\n"
    "2. 翻译要流畅自然，符合中文表达习惯；\n"
    "3. 只输出翻译结果，不要添加任何解释或注释；\n"
    "4. 每个输入段落对应一个输出段落，数量必须一致。"
)

# 单批最多翻译的段落数（避免输出 token 超限导致 JSON 截断）
BATCH_SIZE = 15

# 单段最大字符数（超出则跳过翻译，避免单段过长撑爆上下文）
MAX_SEGMENT_CHARS = 4000


def translate_text(text: str) -> Optional[str]:
    """
    翻译单段文本。

    Args:
        text: 待翻译的英文文本

    Returns:
        中文翻译，失败返回 None
    """
    if not text or not text.strip():
        return ""

    result = translate_batch([text])
    if result:
        return result[0]
    return None


def translate_batch(
    texts: list[str],
    temperature: float = 0.3,
) -> list[str]:
    """
    批量翻译多个文本段落，保持输入顺序与对应关系。

    策略：
    1. 过滤空段和过长段；
    2. 按 BATCH_SIZE 分批，每批通过 JSON 模式请求 DeepSeek；
    3. 若某批 JSON 解析失败或段落数不匹配，回退到逐段翻译；
    4. 把结果按原位置回填。

    Args:
        texts: 待翻译的文本段落列表
        temperature: 翻译温度（低值 -> 更确定性）

    Returns:
        与输入等长的翻译结果列表（翻译失败的对应位置为空字符串）
    """
    if not texts:
        return []

    # 初始化结果：原位置 -> 翻译文本，默认空字符串
    result = [""] * len(texts)

    # 收集需要翻译的 (原位置索引, 文本)
    pending = []
    for i, t in enumerate(texts):
        if not t or not t.strip():
            continue
        if len(t) > MAX_SEGMENT_CHARS:
            logger.warning("段落 %d 过长（%d 字），截断后翻译", i, len(t))
            t = t[:MAX_SEGMENT_CHARS]
        pending.append((i, t))

    if not pending:
        return result

    # 分批处理
    total_batches = math.ceil(len(pending) / BATCH_SIZE)
    for batch_no, batch_start in enumerate(range(0, len(pending), BATCH_SIZE)):
        batch = pending[batch_start:batch_start + BATCH_SIZE]
        indices = [idx for idx, _ in batch]
        segs = [t for _, t in batch]

        logger.info("翻译批次 %d/%d（%d 段）", batch_no + 1, total_batches, len(segs))
        translations = _translate_batch_json(segs, temperature)

        # 校验结果数量
        if translations is None or len(translations) != len(segs):
            logger.warning(
                "批次 %d-%d JSON 翻译失败或数量不匹配（期望 %d），回退逐段翻译",
                batch_start, batch_start + len(batch) - 1, len(segs),
            )
            translations = _translate_segments_individually(segs, temperature)

        # 回填
        for pos, idx in enumerate(indices):
            if pos < len(translations):
                result[idx] = translations[pos].strip()

        # 批次之间暂停，避免触发 API 速率限制（最后一批之后无需等待）
        if batch_no < total_batches - 1 and DEEPSEEK_BATCH_INTERVAL > 0:
            logger.debug("批次间暂停 %.1f 秒", DEEPSEEK_BATCH_INTERVAL)
            time.sleep(DEEPSEEK_BATCH_INTERVAL)

    return result


def _translate_batch_json(
    segments: list[str],
    temperature: float,
) -> Optional[list[str]]:
    """
    通过 JSON 模式批量翻译。

    请求 DeepSeek 返回 {"translations": ["译文1", "译文2", ...]}，
    译文顺序与输入严格一致。

    Args:
        segments: 待翻译段落列表
        temperature: 采样温度

    Returns:
        翻译结果列表，解析失败返回 None
    """
    if not segments:
        return []

    # 构造 JSON 输入提示
    items_json = json.dumps(
        [{"id": i, "text": seg} for i, seg in enumerate(segments)],
        ensure_ascii=False,
    )
    user_message = (
        "请将下面 JSON 数组中每个元素的 text 字段翻译成中文，"
        "返回一个 JSON 对象，格式为 {\"translations\": [\"译文1\", \"译文2\", ...]}，"
        "数组顺序和长度必须与输入完全一致。只输出 JSON，不要输出任何其他内容。\n\n"
        f"{items_json}"
    )

    content = _call_deepseek(
        user_message,
        temperature=temperature,
        max_tokens=4096,
        json_mode=True,
    )
    if content is None:
        return None

    # 兼容模型可能用 ```json ... ``` 包裹的情况
    content = _strip_code_fence(content)

    try:
        data = json.loads(content)
        translations = data.get("translations", [])
        if isinstance(translations, list):
            return [str(t) for t in translations]
        logger.error("translations 字段不是列表: %s", type(translations).__name__)
        return None
    except json.JSONDecodeError as e:
        logger.error("JSON 解析失败: %s, 原始内容前200字: %s", e, content[:200])
        return None


def _translate_segments_individually(
    segments: list[str],
    temperature: float,
) -> list[str]:
    """
    逐段翻译（批量失败时的回退方案）。

    Args:
        segments: 待翻译段落列表
        temperature: 采样温度

    Returns:
        翻译结果列表，失败的段落为空字符串
    """
    results = []
    for i, seg in enumerate(segments):
        content = _call_deepseek(
            f"请将以下英文翻译成中文，只输出译文：\n\n{seg}",
            temperature=temperature,
            max_tokens=2048,
            json_mode=False,
        )
        if content is None:
            logger.warning("第 %d 段单独翻译失败，留空", i)
            results.append("")
        else:
            results.append(content)

        # 每段之间暂停，避免逐段密集调用触发速率限制（最后一段之后无需等待）
        if i < len(segments) - 1 and DEEPSEEK_SEGMENT_INTERVAL > 0:
            logger.debug("逐段翻译间暂停 %.1f 秒", DEEPSEEK_SEGMENT_INTERVAL)
            time.sleep(DEEPSEEK_SEGMENT_INTERVAL)

    return results


def _strip_code_fence(text: str) -> str:
    """去掉模型输出可能包裹的 ```json ... ``` 代码围栏。"""
    text = text.strip()
    if text.startswith("```"):
        # 去掉首行 ```json 或 ```
        first_newline = text.find("\n")
        if first_newline != -1:
            text = text[first_newline + 1:]
        # 去掉结尾 ```
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return text.strip()


def _call_deepseek(
    user_message: str,
    temperature: float = 0.3,
    max_tokens: int = 4096,
    json_mode: bool = False,
) -> Optional[str]:
    """
    调用 DeepSeek Chat Completion API。

    Args:
        user_message: 用户消息
        temperature: 采样温度
        max_tokens: 最大输出 token 数
        json_mode: 是否启用 JSON 输出模式

    Returns:
        API 返回的文本内容，失败返回 None
    """
    url = f"{DEEPSEEK_BASE_URL}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
    }

    payload = {
        "model": DEEPSEEK_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    resp = None
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()

        content = data["choices"][0]["message"]["content"].strip()
        logger.debug("翻译成功，输入 %d 字 -> 输出 %d 字",
                     len(user_message), len(content))
        return content

    except requests.exceptions.Timeout:
        logger.error("DeepSeek API 请求超时")
        return None
    except requests.exceptions.RequestException as e:
        body = resp.text[:500] if resp is not None else "N/A"
        logger.error("DeepSeek API 请求失败: %s, body=%s", e, body)
        return None
    except (KeyError, IndexError, TypeError) as e:
        body = resp.text[:500] if resp is not None else "N/A"
        logger.error("DeepSeek API 返回格式异常: %s, body=%s", e, body)
        return None
