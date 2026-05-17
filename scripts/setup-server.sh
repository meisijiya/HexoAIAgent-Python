#!/bin/bash
# ===============================================================
# Hexo Agent 服务器初始化脚本 (Ubuntu 24.04)
# ===============================================================
# 功能：
# 1. 安装 Docker + Docker Compose
# 2. 开放防火墙端口 8001
# 3. 克隆项目代码
# 4. 提示配置环境变量
# ===============================================================
set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} Hexo Agent 服务器初始化脚本${NC}"
echo -e "${GREEN} 目标系统: Ubuntu 24.04${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""

# ---- 检查 root 权限 ----
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}请使用 sudo 运行此脚本: sudo bash setup-server.sh${NC}"
   exit 1
fi

# ============================================================
# Step 1: 安装 Docker
# ============================================================
echo -e "${YELLOW}[1/5] 安装 Docker...${NC}"

if command -v docker &> /dev/null; then
    echo -e "${GREEN}  ✓ Docker 已安装: $(docker --version)${NC}"
else
    # 卸载旧版本（如有）
    apt-get remove -y docker docker-engine docker.io containerd runc 2>/dev/null || true

    # 安装依赖
    apt-get update
    apt-get install -y ca-certificates curl

    # 添加 Docker 官方 GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc

    # 添加 Docker 仓库
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    echo -e "${GREEN}  ✓ Docker 安装完成: $(docker --version)${NC}"
fi

# ============================================================
# Step 2: 安装 Docker Compose（独立版本，备用）
# ============================================================
echo -e "${YELLOW}[2/5] 检查 Docker Compose...${NC}"

if docker compose version &> /dev/null; then
    echo -e "${GREEN}  ✓ Docker Compose 插件可用: $(docker compose version)${NC}"
else
    echo -e "${RED}  ✗ Docker Compose 插件不可用，请检查 Docker 安装${NC}"
    exit 1
fi

# ============================================================
# Step 3: 开放防火墙端口
# ============================================================
echo -e "${YELLOW}[3/5] 配置防火墙...${NC}"

# 检查 ufw 是否可用
if command -v ufw &> /dev/null; then
    # 开放 8001 端口（Agent 服务对外端口）
    ufw allow 8001/tcp comment "Hexo Agent Service"
    # 确保 SSH 端口是开放的（防止锁自己）
    ufw allow 22/tcp 2>/dev/null || true
    # 如果防火墙未启用，提示用户
    if ufw status | grep -q "Status: inactive"; then
        echo -e "${YELLOW}  ⚠ ufw 防火墙当前未启用，端口规则已添加${NC}"
        echo -e "${YELLOW}  建议运行 'sudo ufw enable' 启用防火墙${NC}"
    else
        echo -e "${GREEN}  ✓ 防火墙端口 8001 已开放${NC}"
    fi
else
    echo -e "${YELLOW}  ⚠ ufw 未安装，请手动配置防火墙开放 8001 端口${NC}"
    echo -e "${YELLOW}  iptables 命令: iptables -A INPUT -p tcp --dport 8001 -j ACCEPT${NC}"
fi

# 如果使用云服务商的安全组，提示用户
echo -e "${YELLOW}  💡 提醒: 如果你的服务器在云服务商（阿里云/腾讯云等），${NC}"
echo -e "${YELLOW}     请同时在控制台的「安全组」中放行 TCP 8001 端口${NC}"

# ============================================================
# Step 4: 创建项目目录
# ============================================================
echo -e "${YELLOW}[4/5] 创建项目目录...${NC}"

PROJECT_DIR="/opt/hexo-agent"
if [ ! -d "$PROJECT_DIR" ]; then
    mkdir -p "$PROJECT_DIR"
    echo -e "${GREEN}  ✓ 项目目录已创建: $PROJECT_DIR${NC}"
else
    echo -e "${YELLOW}  ⚠ 目录已存在: $PROJECT_DIR${NC}"
fi

# ============================================================
# Step 5: 提示后续步骤
# ============================================================
echo ""
echo -e "${GREEN}============================================${NC}"
echo -e "${GREEN} 服务器环境初始化完成！${NC}"
echo -e "${GREEN}============================================${NC}"
echo ""
echo -e "${YELLOW}后续步骤:${NC}"
echo ""
echo -e "  ${GREEN}1.${NC} 上传项目代码到服务器:"
echo -e "     scp -r ./* root@<服务器IP>:$PROJECT_DIR/"
echo ""
echo -e "  ${GREEN}2.${NC} 配置环境变量:"
echo -e "     cd $PROJECT_DIR"
echo -e "     cp .env.production.template agent-service/.env"
echo -e "     vim agent-service/.env"
echo -e "     # 填入: SERVER_IP, GITHUB_CLIENT_ID, GITHUB_CLIENT_SECRET,"
echo -e "     #        GITHUB_PAGES_DOMAIN, GIT_REPO_URL, POSTGRES_PASSWORD 等"
echo ""
echo -e "  ${GREEN}3.${NC} 配置 GitHub SSH Key（用于 git pull 备用仓库）:"
echo -e "     ssh-keygen -t ed25519 -C \"hexo-agent@server\""
echo -e "     cat ~/.ssh/id_ed25519.pub"
echo -e "     # 将公钥添加到备用 GitHub 仓库的 Deploy Keys"
echo ""
echo -e "  ${GREEN}4.${NC} 申请新的 GitHub OAuth App:"
echo -e "     GitHub → Settings → Developer settings → OAuth Apps → New OAuth App"
echo -e "     Homepage URL:      https://<你的GitHubPages域名>"
echo -e "     Callback URL:      http://<服务器IP>:8001/static/oauth-callback.html"
echo ""
echo -e "  ${GREEN}5.${NC} 启动服务:"
echo -e "     cd $PROJECT_DIR"
echo -e "     docker compose -f docker-compose.prod.yml up -d"
echo ""
echo -e "  ${GREEN}6.${NC} 验证:"
echo -e "     curl http://localhost:8001/health"
echo -e "     curl http://<服务器IP>:8001/health  # 从外部访问"
echo ""
