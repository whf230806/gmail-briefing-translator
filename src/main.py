"""
Gmail Briefing 邮件翻译服务 - 主入口

定时检查 Gmail 中标题含 "Briefing" 的邮件，
逐段翻译成中文（英文段落后插入中文），
保留格式和图片，将处理后的邮件发送给自己。

调度时间窗口（北京时间）：
- 早上 5:00 - 6:30，每 10 分钟一次
- 下午 17:00 - 18:30，每 10 分钟一次
"""

import logging
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from src.config import (
    SCHEDULE_WINDOWS,
    SCHEDULE_INTERVAL_MINUTES,
    TIMEZONE,
    LOG_LEVEL,
    LOG_DIR,
    validate as validate_config,
)
from src.gmail_client import (
    get_gmail_service,
    list_briefing_emails,
    get_email_mime,
    send_email,
)
from src.email_parser import (
    parse_raw_email,
    embed_images_in_html,
)
from src.html_processor import process_html, process_plain_text
from src.state_manager import StateManager
from src.translator import translate_text

# 配置日志
_log_dir = Path(LOG_DIR)
_log_dir.mkdir(parents=True, exist_ok=True)
_log_file = _log_dir / "service.log"

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(str(_log_file), encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)

logger = logging.getLogger("main")

# 北京时间时区
_tz = pytz.timezone(TIMEZONE)


def _is_in_schedule_window(now_bj: datetime) -> bool:
    """
    检查当前北京时间是否在调度窗口内。

    Args:
        now_bj: 当前北京时间

    Returns:
        True 表示在窗口内
    """
    current_time = now_bj.strftime("%H:%M")
    for start, end in SCHEDULE_WINDOWS:
        if start <= current_time <= end:
            return True
    return False


def _seconds_until_next_window(now_bj: datetime) -> float:
    """
    计算距离下一个调度窗口开始的秒数。

    如果当前已在窗口内，返回 0。

    Args:
        now_bj: 当前北京时间

    Returns:
        等待秒数
    """
    if _is_in_schedule_window(now_bj):
        return 0.0

    current_time = now_bj.strftime("%H:%M")

    # 检查所有窗口，找到最近的下一个窗口
    candidates = []
    for start, _ in SCHEDULE_WINDOWS:
        if current_time < start:
            # 今天还未到达的窗口
            target = now_bj.replace(
                hour=int(start.split(":")[0]),
                minute=int(start.split(":")[1]),
                second=0,
                microsecond=0,
            )
            candidates.append((target - now_bj).total_seconds())

    if candidates:
        return min(candidates)

    # 所有窗口都已过，等待到明天的第一个窗口
    first_start = SCHEDULE_WINDOWS[0][0]
    tomorrow = now_bj + timedelta(days=1)
    target = tomorrow.replace(
        hour=int(first_start.split(":")[0]),
        minute=int(first_start.split(":")[1]),
        second=0,
        microsecond=0,
    )
    return (target - now_bj).total_seconds()


def process_email(service, state: StateManager, msg: dict) -> bool:
    """
    处理单封邮件：解析 -> 翻译 -> 发送。

    Args:
        service: 已认证的 Gmail API 服务实例
        state: 状态管理器
        msg: Gmail 邮件信息（含 id 和 threadId）

    Returns:
        True 表示处理成功
    """
    gmail_id = msg.get("id", "")
    logger.info("=" * 60)
    logger.info("开始处理邮件: %s", gmail_id)

    # 1. 获取邮件 raw 内容
    raw_mime = get_email_mime(service, gmail_id)
    if not raw_mime:
        logger.error("无法获取邮件 %s 的内容", gmail_id)
        return False

    # 2. 解析邮件
    parsed = parse_raw_email(raw_mime)
    if not parsed:
        logger.error("解析邮件 %s 失败", gmail_id)
        return False

    logger.info("邮件主题: %s", parsed.subject)

    # 3. 翻译处理
    processed_html: str

    if parsed.has_html():
        # HTML 邮件：先嵌入图片，再处理段落翻译
        html_with_images = embed_images_in_html(parsed.html_body, parsed.images)
        processed_html = process_html(html_with_images)
    elif parsed.has_plain():
        # 纯文本邮件：按段落翻译，生成 HTML
        processed_html = process_plain_text(parsed.plain_body)
    else:
        logger.warning("邮件 %s 没有可翻译的内容", gmail_id)
        return False

    if not processed_html:
        logger.warning("邮件 %s 翻译后内容为空", gmail_id)
        return False

    # 4. 组装完整邮件 HTML（加标题和元信息）
    full_html = _build_full_html(parsed, processed_html)

    # 5. 发送邮件（主题加 [中文翻译] 标记，搜索时会排除避免无限循环）
    from src.config import GMAIL_USER_EMAIL, TRANSLATION_MARKER
    translated_subject = translate_text(parsed.subject) or ""
    new_subject = f"{TRANSLATION_MARKER} {parsed.subject}"
    if translated_subject and translated_subject != parsed.subject:
        new_subject += f" / {translated_subject}"

    sent_id = send_email(
        service=service,
        to=GMAIL_USER_EMAIL,
        subject=new_subject,
        html_body=full_html,
        in_reply_to=parsed.message_id,
    )

    if sent_id:
        state.mark_processed(gmail_id, parsed.subject)
        logger.info("邮件 %s 处理完成 ✓", gmail_id)
        return True
    else:
        logger.error("邮件 %s 发送失败", gmail_id)
        return False


def _build_full_html(parsed, processed_html: str) -> str:
    """构建完整的处理邮件 HTML。"""
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 720px; margin: 0 auto; padding: 20px; line-height: 1.6; color: #333;">
<div style="background: #f0f7ff; border: 1px solid #bfdbfe; border-radius: 8px; padding: 12px 16px; margin-bottom: 24px;">
  <p style="margin: 0; color: #1e40af; font-size: 0.9em;">
    📧 原始发件人: {_safe_html(parsed.from_addr)}<br>
    📅 原始日期: {_safe_html(parsed.date)}<br>
    🌐 蓝色段落为机器翻译（DeepSeek），仅供参考
  </p>
</div>
<div style="border-top: 1px solid #e5e7eb; padding-top: 20px;">
{processed_html}
</div>
</body>
</html>"""


def _safe_html(text: str) -> str:
    """安全转义 HTML 字符。"""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def run_once(state: StateManager) -> dict:
    """
    执行一次邮件检查和处理。

    Returns:
        处理统计: {"total": int, "processed": int, "failed": int}
    """
    stats = {"total": 0, "processed": 0, "failed": 0}

    try:
        service = get_gmail_service()
    except Exception as e:
        logger.error("Gmail API 认证失败: %s", e)
        return stats

    try:
        messages = list_briefing_emails(service)
    except Exception as e:
        logger.error("获取邮件列表失败: %s", e)
        return stats

    if not messages:
        logger.info("没有找到 Briefing 邮件")
        return stats

    # 过滤已处理的邮件
    unprocessed = state.filter_unprocessed(messages)
    stats["total"] = len(unprocessed)

    if not unprocessed:
        logger.info("没有新的 Briefing 邮件需要处理")
        return stats

    for msg in unprocessed:
        try:
            success = process_email(service, state, msg)
            if success:
                stats["processed"] += 1
            else:
                stats["failed"] += 1
        except Exception as e:
            logger.exception("处理邮件 %s 时发生异常: %s", msg.get("id", "?"), e)
            stats["failed"] += 1

    logger.info(
        "本轮处理完成: %d 封待处理, %d 成功, %d 失败",
        stats["total"], stats["processed"], stats["failed"],
    )
    return stats


def main():
    """主调度循环。"""
    logger.info("=" * 60)
    logger.info("Gmail Briefing 翻译服务启动")

    # 验证配置
    missing = validate_config()
    if missing:
        logger.error("缺少必需配置: %s", ", ".join(missing))
        logger.error("请在 .env 文件中配置上述环境变量后重启服务")
        sys.exit(1)

    logger.info("调度窗口 (北京时间): %s", ", ".join(
        f"{s}-{e}" for s, e in SCHEDULE_WINDOWS
    ))
    logger.info("检查间隔: %d 分钟", SCHEDULE_INTERVAL_MINUTES)

    state = StateManager()
    total_processed = state.get_processed_count()
    logger.info("历史已处理邮件数: %d", total_processed)

    while True:
        try:
            now_bj = datetime.now(_tz)
            in_window = _is_in_schedule_window(now_bj)

            if in_window:
                logger.info("--- 检查邮件 (%s 北京时间) ---", now_bj.strftime("%H:%M"))
                stats = run_once(state)

                # 处理完后等待间隔
                sleep_seconds = SCHEDULE_INTERVAL_MINUTES * 60
                logger.info("等待 %d 分钟后进行下一次检查...", SCHEDULE_INTERVAL_MINUTES)
            else:
                # 不在窗口内，计算等待时间
                sleep_seconds = _seconds_until_next_window(now_bj)
                if sleep_seconds > 0:
                    next_time = now_bj + timedelta(seconds=sleep_seconds)
                    logger.info("不在调度窗口内，休眠至 %s (约 %.1f 分钟)",
                                next_time.strftime("%H:%M"), sleep_seconds / 60)

            time.sleep(sleep_seconds)

        except KeyboardInterrupt:
            logger.info("收到停止信号，服务正在退出...")
            break
        except Exception as e:
            logger.exception("主循环异常: %s", e)
            # 异常后等待 60 秒再重试
            time.sleep(60)

    logger.info("服务已停止")


if __name__ == "__main__":
    main()
