# 🚀 快速开始 - DeepSeek集成版

## 配置环境变量

### 方法1：使用配置脚本
```bash
bash setup_env.sh
```

### 方法2：手动创建 .env
```bash
cat > .env << EOF
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here

# DeepSeek配置  
DEEPSEEK_API_KEY=sk-7a588fe651c94a50aff17274f8d8144b

# 模型配置
MODEL_NAME=gpt-4o-mini

# Flask配置
SECRET_KEY=quant-agent-secret-key-2024
EOF
```

## 启动应用

```bash
bash start.sh
```

访问：http://localhost:8080

## 使用模型切换功能

### 界面操作
1. 打开浏览器访问 http://localhost:8080
2. 在对话区右上角的模型选择下拉框
3. 选择 DeepSeek Chat 或 DeepSeek Coder
4. 确认切换
5. 继续对话，上下文保持不变！

### 测试建议
1. 先用GPT-4o Mini对话：收集策略信息
2. 切换到DeepSeek Chat：测试上下文保持
3. 继续提问：验证历史记录是否完整

## API调用示例

### 获取可用模型
```bash
curl http://localhost:8080/api/models
```

### 切换模型
```bash
curl -X POST http://localhost:8080/api/switch-model/<session_id> \
  -H "Content-Type: application/json" \
  -d '{"provider": "deepseek", "model": "deepseek-chat"}'
```

## 功能清单

✅ OpenAI模型（GPT-4o系列）  
✅ DeepSeek模型（Chat、Coder）  
✅ 动态切换不丢失上下文  
✅ 保持对话历史  
✅ 保持状态信息  

## 注意事项

1. 先配置 `.env` 文件
2. DeepSeek API Key已预配置
3. 如需使用OpenAI，还需要配置OPENAI_API_KEY
4. 切换模型时会确认提示

## 故障排除

### 问题：切换失败
- 检查 `.env` 文件中的API密钥是否正确
- 检查网络连接
- 查看后端日志

### 问题：找不到模型
- 确认 `app.py` 中的 `SUPPORTED_MODELS` 包含DeepSeek
- 刷新浏览器页面

### 问题：API密钥错误
- 验证DeepSeek API Key是否有效
- 检查密钥格式是否正确

## 下一步

尝试在不同模型间切换，体验：
- 不同模型的回答风格
- 上下文保持是否完整
- 状态信息的持久化

享受量化策略收集过程！🎉
