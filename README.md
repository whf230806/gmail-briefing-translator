# Gmail Briefing 邮件翻译服务

自动获取 Gmail 中标题含 "Briefing" 的邮件，使用 DeepSeek API 逐段翻译成中文（英文段落后插入蓝色中文翻译），保留原始格式和图片，然后将处理后的邮件发送回同一个邮箱。

## 功能

- 📧 自动搜索 Gmail 中标题含 "Briefing" 的邮件
- 🌐 使用 DeepSeek API 进行高质量英中翻译
- 📝 保留原始邮件格式（HTML），在每段英文后插入蓝色中文翻译
- 🖼️ 保留原始邮件中的所有图片（内嵌为 base64）
- ⏰ 定时运行：北京时间 5:00-6:30 和 17:00-18:30，每 10 分钟检查一次
- 💾 SQLite 追踪已处理邮件，避免重复处理

## 项目结构

```
gmail-briefing-translator/
├── src/
│   ├── main.py              # 入口：调度循环
│   ├── gmail_client.py      # Gmail API 封装
│   ├── email_parser.py      # MIME 邮件解析
│   ├── translator.py        # DeepSeek API 翻译
│   ├── html_processor.py    # HTML 段落提取和翻译插入
│   ├── state_manager.py     # SQLite 状态管理
│   └── config.py            # 配置加载
├── data/                    # 凭证和状态（不提交）
├── logs/                    # 运行日志
├── scripts/
│   ├── setup_oauth.py       # OAuth 首次认证
│   └── setup_service.sh     # 一键部署脚本
├── deploy/
│   └── gmail-briefing.service  # systemd unit 文件
├── requirements.txt
├── .env.example
└── README.md
```

## 快速开始

### 前置准备

#### 1. 启用 Gmail API

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 创建或选择项目
3. 启用 **Gmail API**
4. 进入 "凭据" → "创建凭据" → "OAuth 客户端 ID"
5. 选择 "桌面应用" 类型
6. 下载 `credentials.json`

#### 2. 获取 DeepSeek API Key

前往 [DeepSeek 开放平台](https://platform.deepseek.com/) 注册并获取 API Key。

### 本地开发

```bash
# 1. 克隆仓库
git clone <repo-url>
cd gmail-briefing-translator

# 2. 安装依赖
python3 -m venv venv
source venv/bin/activate     # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入 GMAIL_USER_EMAIL 和 DEEPSEEK_API_KEY

# 4. 放置 credentials.json 到 data/ 目录

# 5. 完成 OAuth 认证
python scripts/setup_oauth.py
# 浏览器会自动打开，登录并授权

# 6. 运行
python -m src.main
```

### Ubuntu 服务器部署

```bash
# 1. Clone 到服务器
git clone <repo-url> /opt/gmail-briefing-translator
cd /opt/gmail-briefing-translator

# 2. 配置环境变量
cp .env.example .env
nano .env  # 填入实际配置

# 3. 上传 OAuth token（在本地运行 setup_oauth.py 后获得）
# 将 data/token.pickle 上传到服务器的 data/ 目录

# 4. 上传 credentials.json 到 data/ 目录

# 5. 一键部署
sudo chmod +x scripts/setup_service.sh
sudo ./scripts/setup_service.sh

# 6. 启动服务
sudo systemctl start gmail-briefing

# 7. 查看日志
sudo journalctl -u gmail-briefing -f
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GMAIL_USER_EMAIL` | Gmail 邮箱地址 | 必填 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | 必填 |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-v4-pro` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_BATCH_INTERVAL` | 批量翻译时批次之间的间隔（秒），避免触发 API 速率限制 | `2.0` |
| `DEEPSEEK_SEGMENT_INTERVAL` | 逐段翻译回退时每段之间的间隔（秒） | `1.5` |
| `GOOGLE_CREDENTIALS_PATH` | OAuth 凭证路径 | `data/credentials.json` |
| `GOOGLE_TOKEN_PATH` | OAuth Token 路径 | `data/token.pickle` |
| `STATE_DB_PATH` | 状态数据库路径 | `data/state.db` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

> **关于 API 调用间隔**：服务默认在翻译批次之间暂停 2 秒、逐段回退时每段暂停 1.5 秒，防止密集请求触发 DeepSeek 的速率限制（HTTP 429）。若日志中出现 429 错误，可在 `.env` 中调大这两个间隔值。

## 服务管理

```bash
# 启动
sudo systemctl start gmail-briefing

# 停止
sudo systemctl stop gmail-briefing

# 重启
sudo systemctl restart gmail-briefing

# 查看状态
sudo systemctl status gmail-briefing

# 查看实时日志
sudo journalctl -u gmail-briefing -f

# 禁用开机自启
sudo systemctl disable gmail-briefing
```

## 调度说明

服务在以下时间段运行（北京时间，UTC+8）：

| 时间段 | 频率 |
|--------|------|
| 早上 05:00 - 06:30 | 每 10 分钟 |
| 下午 17:00 - 18:30 | 每 10 分钟 |

这些时间段对应 Bloomberg Briefing 邮件通常的发送时间。在窗口外，服务休眠等待。如需修改，编辑 `src/config.py` 中的 `SCHEDULE_WINDOWS`。

## License

MIT
