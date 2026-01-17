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
# ===========================================
# LLM 配置（三选一，按优先级自动选择）
# 优先级: OPENROUTER > DEEPSEEK > OPENAI
# ===========================================

# 方式1: OpenRouter（推荐中国用户访问 Claude）
# OPENROUTER_API_KEY=sk-or-v1-xxxxx
# OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
# OPENROUTER_MODEL=anthropic/claude-sonnet-4

# 方式2: DeepSeek
# DEEPSEEK_API_KEY=sk-xxxxx
# DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
# DEEPSEEK_MODEL=deepseek-reasoner

# 方式3: OpenAI
OPENAI_API_KEY=your_openai_api_key_here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini

# ===========================================
# Flask 配置
# ===========================================
SECRET_KEY=quant-agent-secret-key-2024
ENVFILE

echo "✅ 已创建.env文件"
echo ""
echo "📝 请编辑 .env 文件，配置你的 LLM Provider"
echo ""
echo "编辑命令:"
echo "  nano .env"
echo "  或"
echo "  open -e .env"
echo ""
echo "API Key获取地址:"
echo "  - OpenRouter: https://openrouter.ai/keys (推荐，可访问 Claude)"
echo "  - DeepSeek: https://platform.deepseek.com/api_keys"
echo "  - OpenAI: https://platform.openai.com/api-keys"
echo ""
echo "配置示例（使用 OpenRouter 访问 Claude）:"
echo "  OPENROUTER_API_KEY=sk-or-v1-xxxxx"
echo "  OPENROUTER_BASE_URL=https://openrouter.ai/api/v1"
echo "  OPENROUTER_MODEL=anthropic/claude-sonnet-4"
echo ""
