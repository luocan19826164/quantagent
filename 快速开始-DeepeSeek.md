# 🚀 快速开始 - 多模型支持版

## 配置环境变量

### 方法1：使用配置脚本
```bash
bash setup_env.sh
```

### 方法2：手动创建 .env

选择你想用的 LLM Provider（三选一）：

```bash
cat > .env << EOF
# ===========================================
# LLM 配置（三选一，按优先级自动选择）
# 优先级: OPENROUTER > DEEPSEEK > OPENAI
# ===========================================

# 方式1: OpenRouter（推荐中国用户访问 Claude）
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=anthropic/claude-sonnet-4

# 方式2: DeepSeek
# DEEPSEEK_API_KEY=sk-xxxxx
# DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
# DEEPSEEK_MODEL=deepseek-reasoner

# 方式3: OpenAI
# OPENAI_API_KEY=sk-proj-xxxxx
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4o

# Flask配置
SECRET_KEY=quant-agent-secret-key-2024
EOF
```

## 启动应用

```bash
bash start.sh
```

访问：http://localhost:8081

## 支持的 LLM Provider

| Provider | 获取 API Key | 推荐模型 |
|----------|-------------|---------|
| OpenRouter | https://openrouter.ai/keys | `anthropic/claude-sonnet-4` |
| DeepSeek | https://platform.deepseek.com/api_keys | `deepseek-reasoner` |
| OpenAI | https://platform.openai.com/api-keys | `gpt-4o` |

## 环境变量命名约定

```
{PROVIDER}_API_KEY   - API 密钥（必填）
{PROVIDER}_BASE_URL  - API 地址（必填）
{PROVIDER}_MODEL     - 模型名称（必填）
```

## 验证配置

启动后查看日志，确认使用的 Provider：

```
Using OPENROUTER - Model: anthropic/claude-sonnet-4, Base URL: https://openrouter.ai/api/v1
```

## 故障排除

### 问题：提示缺少配置
确保每个 Provider 的三个环境变量都配置完整：
- `{PROVIDER}_API_KEY`
- `{PROVIDER}_BASE_URL`
- `{PROVIDER}_MODEL`

### 问题：API 调用失败
- 检查 API Key 是否有效
- 检查网络连接
- 查看后端日志 `app.log`

### 问题：模型名称错误
不同 Provider 的模型名称格式不同：
- OpenRouter: `anthropic/claude-sonnet-4`
- DeepSeek: `deepseek-reasoner`
- OpenAI: `gpt-4o`

## 下一步

配置好环境变量后，访问 http://localhost:8081 开始使用！

详细配置说明见 `.env配置说明.md`
