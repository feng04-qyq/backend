#!/bin/bash

# 部署脚本 - wxf888.top
# 使用方法: chmod +x deploy_to_wxf888.top.sh && ./deploy_to_wxf888.top.sh

set -e  # 遇到错误立即退出

echo "🚀 开始部署到 wxf888.top..."

# 配置变量
BACKEND_DIR="/var/www/wxf888.top/backend"
FRONTEND_DIR="/var/www/wxf888.top/frontend"

# 检查目录是否存在
if [ ! -d "$BACKEND_DIR" ]; then
    echo "❌ 后端目录不存在: $BACKEND_DIR"
    exit 1
fi

if [ ! -d "$FRONTEND_DIR" ]; then
    echo "❌ 前端目录不存在: $FRONTEND_DIR"
    exit 1
fi

# 更新后端
echo "📦 更新后端..."
cd "$BACKEND_DIR"
source venv/bin/activate

# 如果有 Git，拉取最新代码
if [ -d ".git" ]; then
    git pull || echo "⚠️ Git pull 失败，继续使用当前代码"
fi

# 安装依赖
pip install -r requirements_production.txt

# 重启后端
echo "🔄 重启后端服务..."
pm2 restart backend || pm2 start ecosystem.config.js || pm2 start uvicorn --name "backend" -- --host 0.0.0.0 --port 8000 api_server_unified:app

# 更新前端
echo "📦 更新前端..."
cd "$FRONTEND_DIR"

# 如果有 Git，拉取最新代码
if [ -d ".git" ]; then
    git pull || echo "⚠️ Git pull 失败，继续使用当前代码"
fi

# 安装依赖
npm install

# 构建生产版本
npm run build

# 重启前端
echo "🔄 重启前端服务..."
pm2 restart frontend || pm2 start npm --name "frontend" -- start

# 显示状态
echo ""
echo "✅ 部署完成！"
echo ""
echo "📊 服务状态："
pm2 status
echo ""
echo "📝 查看日志："
echo "  pm2 logs backend   # 后端日志"
echo "  pm2 logs frontend  # 前端日志"
echo ""
echo "🌐 访问地址："
echo "  https://wxf888.top"

