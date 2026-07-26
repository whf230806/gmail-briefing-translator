#!/bin/bash
#
# 一键部署脚本
#
# 在 Ubuntu 云服务器上运行此脚本，自动完成：
# 1. 创建 Python 虚拟环境
# 2. 安装依赖
# 3. 配置 systemd 服务
# 4. 启动服务
#
# 使用方法：
#   chmod +x scripts/setup_service.sh
#   sudo ./scripts/setup_service.sh
#

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "============================================"
echo " Gmail Briefing 翻译服务 - 部署脚本"
echo "============================================"
echo ""

# 检测是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# 项目目录
APP_DIR="/opt/gmail-briefing-translator"
APP_USER="ubuntu"

# 检查项目目录
if [ ! -d "$APP_DIR" ]; then
    echo -e "${RED}项目目录 $APP_DIR 不存在${NC}"
    echo "请先将代码 clone 到该目录："
    echo "  git clone <repo-url> $APP_DIR"
    exit 1
fi

echo -e "${GREEN}[1/5] 安装系统依赖${NC}"
apt-get update -qq
apt-get install -y -qq python3 python3-venv python3-pip

echo -e "${GREEN}[2/5] 创建 Python 虚拟环境${NC}"
cd "$APP_DIR"
python3 -m venv venv
chown -R "$APP_USER:$APP_USER" venv/

echo -e "${GREEN}[3/5] 安装 Python 依赖${NC}"
"$APP_DIR/venv/bin/pip" install --upgrade pip -q
"$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" -q

echo -e "${GREEN}[4/5] 配置 systemd 服务${NC}"
cp "$APP_DIR/deploy/gmail-briefing.service" /etc/systemd/system/
systemctl daemon-reload
systemctl enable gmail-briefing

echo -e "${GREEN}[5/5] 检查配置${NC}"
if [ ! -f "$APP_DIR/.env" ]; then
    echo -e "${YELLOW}⚠ 未找到 .env 文件。请从 .env.example 复制并配置：${NC}"
    echo "  cp $APP_DIR/.env.example $APP_DIR/.env"
    echo "  nano $APP_DIR/.env"
    echo ""
    echo -e "${YELLOW}⚠ 同时请确保 data/token.pickle 已上传到服务器！${NC}"
    echo ""
fi

echo ""
echo "============================================"
echo -e "${GREEN} 部署完成！${NC}"
echo "============================================"
echo ""
echo "后续步骤："
echo "1. 确保 .env 和 data/token.pickle 已配置"
echo "2. 启动服务："
echo "   sudo systemctl start gmail-briefing"
echo ""
echo "3. 查看状态："
echo "   sudo systemctl status gmail-briefing"
echo ""
echo "4. 查看日志："
echo "   sudo journalctl -u gmail-briefing -f"
echo ""
echo "5. 重启服务（修改配置后）："
echo "   sudo systemctl restart gmail-briefing"
echo ""
