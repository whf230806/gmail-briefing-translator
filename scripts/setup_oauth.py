#!/usr/bin/env python3
"""
OAuth 首次认证脚本

在本地运行此脚本以完成 Gmail API 的 OAuth 2.0 认证。
运行前请确保：
1. 已从 Google Cloud Console 下载 credentials.json 放到 data/ 目录
2. 已在 .env 中配置 GMAIL_USER_EMAIL

运行后将生成 data/token.pickle，将其复制到服务器的 data/ 目录即可。
"""

import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.config import GOOGLE_CREDENTIALS_PATH, GOOGLE_TOKEN_PATH
from src.gmail_client import get_gmail_service


def main():
    creds_path = Path(GOOGLE_CREDENTIALS_PATH)
    token_path = Path(GOOGLE_TOKEN_PATH)

    print("=" * 50)
    print("Gmail Briefing 翻译服务 - OAuth 认证")
    print("=" * 50)
    print()

    if not creds_path.exists():
        print(f"❌ 未找到 credentials.json 文件: {creds_path}")
        print()
        print("请按以下步骤操作：")
        print("1. 前往 https://console.cloud.google.com/")
        print("2. 创建或选择项目")
        print("3. 启用 Gmail API")
        print("4. 创建 OAuth 2.0 客户端 ID（桌面应用类型）")
        print("5. 下载 credentials.json 放到 data/ 目录")
        print()
        sys.exit(1)

    print(f"✓ 找到凭证文件: {creds_path}")
    print()
    print("即将打开浏览器进行 OAuth 认证...")
    print("请在浏览器中登录你的 Gmail 账号并授权。")
    print()

    try:
        service = get_gmail_service()
        # 获取用户邮箱以验证认证成功
        profile = service.users().getProfile(userId="me").execute()
        email = profile.get("emailAddress", "未知")
        print(f"✓ 认证成功！已授权账号: {email}")
        print(f"✓ Token 已保存到: {token_path}")
        print()
        print("下一步：将 data/token.pickle 文件复制到 Ubuntu 服务器的对应目录。")
    except Exception as e:
        print(f"❌ 认证失败: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
