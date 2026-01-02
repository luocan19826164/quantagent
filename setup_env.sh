#!/bin/bash

echo "=================================="
echo "配置量化Agent环境变量"
echo "=================================="
echo ""

# 检查.env文件是否存在
if [ -f .env ]; then
    echo "⚠️  .env文件已存在"
    read -p "是否要重新配置？(y/n): " choice
    if [ "$choice" != "y" ]; then
        echo "取消配置"
        exit 0
    fi
fi

# 创建.env文件
cat > .env << 'ENVFILE'
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here
# OPENAI_BASE_URL=https://api.openai.com/v1  # 可选

# DeepSeek配置
DEEPSEEK_API_KEY=sk-7a588fe651c94a50aff17274f8d8144b
# DEEPSEEK_BASE_URL=https://api.deepseek.com/v1  # 可选

# 模型配置
MODEL_NAME=gpt-4o-mini

# Flask配置
SECRET_KEY=quant-agent-secret-key-2024
ENVFILE

echo "✅ 已创建.env文件"
echo ""
echo "📝 已预配置DeepSeek API Key"
echo ""
echo "编辑命令（如果需要配置OpenAI API Key）:"
echo "  nano .env"
echo "  或"
echo "  open -e .env"
echo ""
echo "API Key获取地址:"
echo "  - OpenAI: https://platform.openai.com/api-keys"
echo "  - DeepSeek: https://platform.deepseek.com/api_keys"
echo ""
