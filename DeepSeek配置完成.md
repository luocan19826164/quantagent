# DeepSeek配置完成 ✅

已集成DeepSeek模型，现在可以使用了！

## 配置详情

### DeepSeek API Key
```
DEEPSEEK_API_KEY=sk-7a588fe651c94a50aff17274f8d8144b
```

### 支持的模型

#### OpenAI
- GPT-4o Mini (默认推荐)
- GPT-4o
- GPT-4 Turbo

#### DeepSeek
- DeepSeek Chat
- DeepSeek Coder

## 使用方法

### 1. 创建环境变量文件

运行配置脚本：
```bash
bash setup_env.sh
```

或手动创建 `.env` 文件：
```bash
# OpenAI配置
OPENAI_API_KEY=your_openai_api_key_here

# DeepSeek配置
DEEPSEEK_API_KEY=sk-7a588fe651c94a50aff17274f8d8144b

# 模型配置
MODEL_NAME=gpt-4o-mini

# Flask配置
SECRET_KEY=quant-agent-secret-key-2024
```

### 2. 启动应用
```bash
python backend/app.py
# 或
bash start.sh
```

### 3. 切换模型

在界面上选择模型下拉框：
- GPT-4o Mini
- GPT-4o
- GPT-4 Turbo
- **DeepSeek Chat**
- **DeepSeek Coder**

点击切换后，对话历史和上下文保持不变！

## 功能特点

✅ 支持动态切换模型  
✅ 保持对话历史和上下文  
✅ 支持OpenAI和DeepSeek  
✅ 无需重启应用  

## 测试建议

1. 先用默认的GPT-4o Mini进行对话
2. 收集一些信息后切换到DeepSeek Chat
3. 继续对话，验证上下文保持完整
4. 观察不同模型的表现

## 注意事项

⚠️ API Key已硬编码在配置脚本中  
⚠️ 不要将包含API Key的文件提交到Git  
⚠️ DeepSeek免费额度有限，注意使用量  

## 后续优化

- [ ] 添加模型费用显示
- [ ] 添加模型切换历史记录
- [ ] 支持自定义温度参数
- [ ] 添加模型性能对比
