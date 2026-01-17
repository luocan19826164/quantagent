# 量化规则收集 Agent

这是一个基于 LangChain 的智能量化规则收集系统，通过多轮对话引导用户完善量化交易策略。

## 功能特性

- 🤖 智能对话引导：通过多轮交互帮助用户完善量化策略
- 🔧 工具验证：自动检测现有工具和指标能否满足用户需求
- 📊 规则收集：收集交易市场、币种、建仓规则、止盈止损等完整信息
- 💾 结构化输出：生成可用于后续执行的规则数据结构
- 🌐 Web界面：友好的浏览器交互界面

## 架构设计

```
quantagent/
├── backend/
│   ├── agent/
│   │   ├── quant_agent.py      # Agent核心逻辑
│   │   ├── tools.py             # 工具定义
│   │   ├── indicators.py        # 技术指标
│   │   └── state_manager.py    # 状态管理
│   └── app.py                   # Flask后端
├── frontend/
│   ├── templates/
│   │   └── index.html           # 前端页面
│   └── static/
│       ├── style.css            # 样式
│       └── script.js            # 前端逻辑
├── requirements.txt
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

运行配置脚本：

```bash
./setup_env.sh
```

或手动编辑 `.env` 文件，配置你的 LLM Provider（三选一）：

```bash
# 方式1: OpenRouter（推荐中国用户访问 Claude）
OPENROUTER_API_KEY=sk-or-v1-xxxxx
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODEL=anthropic/claude-sonnet-4

# 方式2: DeepSeek
DEEPSEEK_API_KEY=sk-xxxxx
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-reasoner

# 方式3: OpenAI
OPENAI_API_KEY=sk-proj-xxxxx
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o
```

详细配置说明见 `.env配置说明.md`

### 3. 运行应用

```bash
python backend/app.py
```

### 4. 访问界面

打开浏览器访问：`http://localhost:5000`

## 使用示例

### 用户输入示例：
```
我想做一个趋势跟踪策略，当价格突破30日均线时买入
```

### Agent会引导用户完善：
- 交易市场（现货/合约）
- 交易币种列表
- K线周期（1分钟/5分钟/1小时/日线等）
- 止盈止损规则
- 最大仓位比例
- 其他风险控制参数

### 最终输出的数据结构：
```json
{
  "user_requirements": {
    "market": "现货",
    "symbols": ["BTCUSDT", "ETHUSDT"],
    "timeframe": "1h",
    "entry_rules": "价格突破30日均线",
    "take_profit": "5%",
    "stop_loss": "2%",
    "max_position_ratio": 0.3
  },
  "execution_logic": {
    "steps": [...],
    "tools_used": [...],
    "indicators_used": [...]
  }
}
```

## 已实现的工具和指标

### 技术指标（Indicators）
- MA (移动平均线)
- EMA (指数移动平均线)
- RSI (相对强弱指标)
- MACD (指数平滑异同移动平均线)
- Bollinger Bands (布林带)
- KDJ (随机指标)
- ATR (平均真实波幅)
- Volume (成交量)

### 工具（Tools）
- 查询可用指标
- 验证规则可行性
- 查询支持的交易对
- 查询支持的时间周期
- 保存最终规则

## 技术栈

- **后端**: Flask + LangChain
- **AI**: OpenAI GPT-4 / DeepSeek / Claude (via OpenRouter)
- **前端**: HTML + CSS + JavaScript
- **状态管理**: 内存会话存储 + SQLite

## 注意事项

- 此Agent仅用于收集和验证量化规则，不执行实际交易
- 所有工具和指标均为Mock数据，用于演示和调试
- 实际生产环境需要对接真实的交易所API和数据源

