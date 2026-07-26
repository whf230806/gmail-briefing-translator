# Gmail Briefing 邮件翻译服务

自动获取 Gmail 中标题含 "Briefing" 的邮件，使用 DeepSeek API 逐段翻译成中文（英文段落后插入蓝色中文翻译），保留原始格式和图片，然后将处理后的邮件发送回同一个邮箱。

## 功能

- 📧 自动搜索 Gmail 中标题含 "Briefing" 的邮件
- 🌐 使用 DeepSeek API 进行高质量英中翻译
- 📝 保留原始邮件格式（HTML），在每段英文后插入蓝色中文翻译
- 🖼️ 保留原始邮件中的所有图片（内嵌为 base64）
- ⏰ 定时运行：北京时间 5:00-6:30 和 17:00-18:30，每 10 分钟检查一次
- 💾 SQLite 追踪已处理邮件，避免重复处理
- 🔄 自动排除自身发送的翻译邮件，避免无限循环
- 📜 日志自动按大小轮转（5MB × 5 个备份），防止磁盘写满

## 项目结构

```
gmail-briefing-translator/
├── src/
│   ├── main.py              # 入口：调度循环
│   ├── gmail_client.py      # Gmail API 封装
│   ├── email_parser.py      # MIME 邮件解析
│   ├── translator.py        # DeepSeek API 翻译（JSON模式 + 逐段回退）
│   ├── html_processor.py    # HTML 段落提取和翻译插入
│   ├── state_manager.py     # SQLite 状态管理
│   └── config.py            # 配置加载
├── data/                    # 凭证和状态（不提交到 Git）
├── logs/                    # 运行日志（自动轮转）
├── scripts/
│   ├── setup_oauth.py       # OAuth 首次认证（本地运行）
│   └── setup_service.sh     # 一键部署脚本
├── deploy/
│   └── gmail-briefing.service  # systemd unit 文件
├── requirements.txt
├── .env.example
└── README.md
```

## 前置准备

### 1. 启用 Gmail API（获取 credentials.json）

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 点击顶部项目选择器 → **新建项目**，输入名称（如 `gmail-briefing`）
3. 左侧菜单 → **API 和服务** → **启用 API 和服务**
4. 搜索 **Gmail API**，点击启用
5. 左侧菜单 → **OAuth 同意屏幕**
   - User Type 选择 **External**
   - 填写应用名称、邮箱（其余可留空）
   - 添加敏感作用域时跳过（不需要额外添加）
   - 添加测试用户：填入你的 Gmail 邮箱
   - 完成注册
6. 左侧菜单 → **凭据** → **创建凭据** → **OAuth 客户端 ID**
   - 应用类型：**桌面应用**
   - 名称随意（如 `server-client`）
   - 点击创建
7. 下载 JSON 文件，重命名为 `credentials.json`

### 2. 获取 DeepSeek API Key

1. 前往 [DeepSeek 开放平台](https://platform.deepseek.com/)
2. 注册登录 → **API Keys** 页面
3. 点击 **创建 API Key**，复制密钥（格式 `sk-xxxxxxxx`）
4. 建议首次充值 10-20 元用于翻译费用

### 3. 准备 Ubuntu 云服务器

- **系统版本**：Ubuntu 22.04 LTS 或 24.04 LTS
- **最低配置**：1 核 CPU、512MB 内存、5GB 磁盘（实际使用 < 200MB）
- **网络**：需要出站访问 `gmail.googleapis.com` 和 `api.deepseek.com`

```bash
# SSH 登录服务器后，更新系统包
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-venv python3-pip git
```

## Ubuntu 服务器部署（详细步骤）

> 总耗时约 10 分钟。OAuth 认证在你的 **本地电脑**（Windows/Mac）上完成，服务器**不需要浏览器**。

整个部署分三步：本地获取 token → 上传到服务器 → 服务器配置启动。

---

### 第一步：本地完成 OAuth 认证

> 在 **你自己的电脑**（有浏览器的 Windows 或 Mac）上操作。

```bash
# 1. 克隆仓库到本地
git clone https://github.com/whf230806/gmail-briefing-translator.git
cd gmail-briefing-translator

# 2. 安装依赖
python3 -m venv venv
source venv/bin/activate          # Mac/Linux
# 或 venv\Scripts\activate       # Windows
pip install -r requirements.txt

# 3. 配置环境变量（仅本地运行 setup_oauth 不需要 .env，但为了完整）
cp .env.example .env
# 先不填，等上传到服务器后再编辑

# 4. 将下载的 credentials.json 放到 data/ 目录
cp /path/to/downloaded/credentials.json data/

# 5. 运行 OAuth 认证脚本
python scripts/setup_oauth.py
```

此时浏览器自动打开 Google 登录页面：
- 选择你的 Gmail 账号登录
- 如果提示 "Google 尚未验证此应用"，点击 **继续**（这是你自己创建的应用）
- 勾选所需权限后点击 **继续**
- 看到 "认证成功" 提示即完成

脚本会在 `data/` 目录生成 `token.pickle` 文件。

---

### 第二步：上传到服务器

```bash
# 将整个 data/ 目录上传到服务器（包含 credentials.json 和 token.pickle）
scp -r data/ ubuntu@你的服务器IP:/tmp/

# SSH 登录服务器
ssh ubuntu@你的服务器IP

# Clone 仓库到部署目录
sudo git clone https://github.com/whf230806/gmail-briefing-translator.git /opt/gmail-briefing-translator

# 移动凭证到仓库的 data/ 目录
sudo mv /tmp/data/* /opt/gmail-briefing-translator/data/
sudo chown -R ubuntu:ubuntu /opt/gmail-briefing-translator/data/

# 配置环境变量
cd /opt/gmail-briefing-translator
sudo cp .env.example .env
sudo nano .env
```

在打开的编辑器中填入关键配置：

```ini
GMAIL_USER_EMAIL=你的邮箱@gmail.com
DEEPSEEK_API_KEY=sk-你的密钥
# 以下选项保留默认即可
DEEPSEEK_MODEL=deepseek-v4-pro
DEEPSEEK_BATCH_INTERVAL=2.0
DEEPSEEK_SEGMENT_INTERVAL=1.5
LOG_LEVEL=INFO
```

按 `Ctrl+O` 回车保存，`Ctrl+X` 退出。

---

### 第三步：部署启动

```bash
# 一键部署（创建 venv、安装依赖、注册 systemd 服务）
cd /opt/gmail-briefing-translator
sudo chmod +x scripts/setup_service.sh
sudo ./scripts/setup_service.sh

# 启动服务
sudo systemctl start gmail-briefing

# 验证运行状态
sudo systemctl status gmail-briefing
```

看到 `active (running)` 即部署成功。

---

## 服务管理

```bash
# 查看状态
sudo systemctl status gmail-briefing

# 查看实时日志（应用日志）
sudo journalctl -u gmail-briefing -f

# 查看最近 50 行日志
sudo journalctl -u gmail-briefing -n 50

# 查看文件日志（轮转存档）
tail -f /opt/gmail-briefing-translator/logs/service.log

# 启动 / 停止 / 重启
sudo systemctl start gmail-briefing
sudo systemctl stop gmail-briefing
sudo systemctl restart gmail-briefing

# 开机自启
sudo systemctl enable gmail-briefing

# 禁用开机自启
sudo systemctl disable gmail-briefing
```

## 验证部署

### 1. 检查服务状态

```bash
sudo systemctl status gmail-briefing
```

输出应类似：
```
● gmail-briefing.service - Gmail Briefing Translator Service
   Active: active (running) since Sun 2026-07-26 17:05:00 CST
```

### 2. 检查日志

```bash
sudo journalctl -u gmail-briefing -n 20
```

启动日志应包含：
- `Gmail Briefing 翻译服务启动`
- `调度窗口 (北京时间): 05:00-06:30, 17:00-18:30`
- `历史已处理邮件数: 0`

### 3. 手动触发测试（在调度窗口内，或临时修改运行参数）

如果当前不在北京时间 5:00-6:30 或 17:00-18:30，服务会休眠等待。要立即测试：

```bash
# 停止服务
sudo systemctl stop gmail-briefing

# 手动前台运行（Ctrl+C 可中断）
cd /opt/gmail-briefing-translator
source venv/bin/activate
python -m src.main

# 观察输出，确认能正常连接 Gmail API 和搜索邮件
# 如果不在调度窗口，等待几分钟看是否自动进入窗口
```

## 故障排查

### Token 过期 / 认证失败

```bash
# 日志中看到 "Token 已过期，正在刷新..."
# 通常自动刷新成功。如果失败：

# 1. 检查 token.pickle 权限
ls -la /opt/gmail-briefing-translator/data/

# 2. 确保文件属主正确
sudo chown -R ubuntu:ubuntu /opt/gmail-briefing-translator/data/

# 3. 如果 token 损坏，在本地重新运行 setup_oauth.py，scp 上传新 token.pickle
# 然后重启服务
sudo systemctl restart gmail-briefing
```

### DeepSeek API 请求失败

```bash
# 常见原因：

# 1. API Key 错误 → 检查 .env 中 DEEPSEEK_API_KEY
grep DEEPSEEK_API_KEY /opt/gmail-briefing-translator/.env

# 2. 账户余额不足 → 登录 DeepSeek 平台检查充值

# 3. 模型名不符 → 检查 DEEPSEEK_MODEL（默认 deepseek-v4-pro）

# 4. 速率限制 (429) → 调大间隔
# 编辑 .env 修改：
#   DEEPSEEK_BATCH_INTERVAL=5.0
#   DEEPSEEK_SEGMENT_INTERVAL=3.0
#   sudo systemctl restart gmail-briefing

# 5. 网络不通 → 测试连通性
curl -s https://api.deepseek.com/v1/chat/completions \
  -H "Authorization: Bearer sk-你的key" \
  -d '{"model":"deepseek-chat","messages":[{"role":"user","content":"test"}]}'
```

### Gmail API 权限不足

```bash
# 日志中看到 403 / insufficient permissions

# 1. 确认 Google Cloud Console 中 Gmail API 已启用
# 2. 确认 OAuth 同意屏幕的测试用户包含你的邮箱
# 3. 确认凭证范围正确（src/config.py 中的 GMAIL_SCOPES）
# 4. 删除旧 token，重新运行 setup_oauth.py
```

### 服务无法启动

```bash
# 查看 systemd 日志获取详细错误
sudo journalctl -u gmail-briefing -n 50 --no-pager

# 检查 .env 文件是否配置
cat /opt/gmail-briefing-translator/.env

# 检查 venv 是否创建成功
ls -la /opt/gmail-briefing-translator/venv/bin/python

# 手动运行看具体错误
cd /opt/gmail-briefing-translator
sudo -u ubuntu venv/bin/python -m src.main
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `GMAIL_USER_EMAIL` | Gmail 邮箱地址 | **必填** |
| `DEEPSEEK_API_KEY` | DeepSeek API Key | **必填** |
| `DEEPSEEK_MODEL` | DeepSeek 模型名 | `deepseek-v4-pro` |
| `DEEPSEEK_BASE_URL` | DeepSeek API 地址 | `https://api.deepseek.com/v1` |
| `DEEPSEEK_BATCH_INTERVAL` | 批量翻译批次间隔（秒） | `2.0` |
| `DEEPSEEK_SEGMENT_INTERVAL` | 逐段翻译间隔（秒） | `1.5` |
| `GOOGLE_CREDENTIALS_PATH` | OAuth 凭证路径 | `data/credentials.json` |
| `GOOGLE_TOKEN_PATH` | OAuth Token 路径 | `data/token.pickle` |
| `STATE_DB_PATH` | 状态数据库路径 | `data/state.db` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

> **关于 API 调用间隔**：服务默认在翻译批次之间暂停 2 秒、逐段回退时每段暂停 1.5 秒，防止密集请求触发 DeepSeek 的速率限制（HTTP 429）。若日志中出现 429 错误，调大这两个值后重启服务。

## 调度说明

服务在以下时间段运行（北京时间，UTC+8）：

| 时间段 | 频率 | 说明 |
|--------|------|------|
| 早上 05:00 - 06:30 | 每 10 分钟 | Bloomberg 早间 Briefing 发送后 |
| 下午 17:00 - 18:30 | 每 10 分钟 | Bloomberg 晚间 Briefing 发送后 |

窗口外服务休眠等待，不消耗 API 配额。如需修改，编辑 `src/config.py` 中的 `SCHEDULE_WINDOWS`：

```python
SCHEDULE_WINDOWS = [
    ("05:00", "06:30"),
    ("17:00", "18:30"),
]
```

## 更新部署

代码更新时，在服务器执行：

```bash
cd /opt/gmail-briefing-translator
sudo systemctl stop gmail-briefing
git pull
source venv/bin/activate
pip install -r requirements.txt -q
sudo systemctl start gmail-briefing
```

## License

MIT
