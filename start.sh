#!/bin/bash

# 量化规则收集Agent启动脚本

echo "=================================="
echo "量化规则收集 Agent"
echo "=================================="
echo ""

# 检查.env文件
if [ ! -f .env ]; then
    echo "⚠️  未找到.env文件，正在创建..."
    cp .env.example .env
    echo "✅ 已创建.env文件"
    echo ""
    echo "❗️ 重要: 请编辑.env文件，填入你的OpenAI API Key"
    echo "   编辑命令: nano .env"
    echo ""
    read -p "按Enter继续..."
fi

# 检查依赖
echo "检查依赖中..."
if ! pip show langchain > /dev/null 2>&1; then
    echo "📦 正在安装缺失依赖..."
    pip install -r requirements.txt
fi

echo ""
echo "🚀 启动程序: http://localhost:8081"
echo "按 Ctrl+C 停止"
echo ""

# 启动应用（开启 debug 模式）
export FLASK_DEBUG=1
python backend/app.py

