# Execution Agent 改进方案

## 问题分析

当前 `execution_agent` 存在的问题：
1. **被动数据注入**：直接获取K线数据并传给LLM，LLM无法主动决定需要什么数据
2. **一步到位决策**：LLM直接返回最终决策，没有中间计算步骤
3. **无法追踪过程**：无法看到LLM的推理过程和中间计算结果
4. **缺乏工具调用能力**：LLM无法主动调用工具获取数据或计算指标

## 改进方案：基于 ReAct 模式的逐步执行框架

### 核心设计思路

采用 **ReAct (Reasoning + Acting)** 模式，让LLM能够：
1. **思考 (Think)**：分析当前状态，决定下一步行动
2. **行动 (Act)**：调用工具或进行计算
3. **观察 (Observe)**：获取工具返回结果或计算结果
4. **反馈 (Feedback)**：记录中间结果，继续下一步或做出最终决策

### Action 格式设计

统一的 action 格式，支持工具调用、计算和决策：

```json
{
  "type": "tool_call" | "calculation" | "decision" | "observation",
  "step": 1,  // 步骤编号
  "reasoning": "为什么执行这个操作",  // 推理过程
  "action": {
    // 如果是 tool_call
    "tool_name": "get_kline_data",
    "params": {
      "exchange": "Binance",
      "symbol": "BTCUSDT",
      "timeframe": "1h",
      "limit": 100
    }
  },
  "result": null,  // 工具返回结果（执行后填充）
  "intermediate_result": null,  // 中间计算结果（如果是calculation）
  "next_step": "继续分析" | "做出决策"  // 下一步指示
}
```

### 执行流程

```
1. 初始化执行上下文
   ├─ 加载规则配置
   ├─ 获取当前持仓状态
   └─ 初始化执行历史记录

2. ReAct 循环（最多 N 轮，如 10 轮）
   ├─ Step 1: LLM 分析当前状态，决定需要什么数据
   │   └─ 返回 action: {type: "tool_call", tool_name: "get_kline_data", ...}
   │
   ├─ Step 2: 执行工具调用，获取K线数据
   │   └─ 记录结果到 action.result
   │
   ├─ Step 3: LLM 分析数据，决定需要计算什么指标
   │   └─ 返回 action: {type: "calculation", reasoning: "计算MA30", ...}
   │
   ├─ Step 4: 执行计算（或调用指标工具）
   │   └─ 记录中间结果到 action.intermediate_result
   │
   ├─ Step 5: LLM 继续分析，可能需要更多数据或计算
   │   └─ 返回 action: {type: "tool_call" | "calculation", ...}
   │
   └─ Step N: LLM 做出最终决策
       └─ 返回 action: {type: "decision", action: "buy" | "sell" | "hold", ...}

3. 执行最终决策（如果是 buy/sell）
   └─ 调用 place_order 工具
```

### LLM Prompt 设计

**使用 ChatMessageHistory 管理执行历史**（推荐方式）

```python
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage

# 初始化 memory
memory = ConversationBufferMemory(
    memory_key="execution_history",
    return_messages=True
)

# 系统提示词（只设置一次）
system_prompt = """
你是一个专业的量化交易执行Agent。你的任务是逐步分析策略规则，调用工具获取数据，进行计算，最终做出交易决策。

【当前上下文】
- 规则ID: {rule_id}
- 交易对: {symbol}
- 当前持仓状态: {runtime_status}
- 策略规则: {user_requirements}

【可用工具】
{available_tools}

【你的任务】
基于以上信息和执行历史，决定下一步操作。你可以：
1. 调用工具获取数据（如 get_kline_data）
2. 进行计算并记录中间结果（如计算MA、RSI等指标）
3. 做出最终决策（buy/sell/hold）

请返回JSON格式的action：
{{
    "type": "tool_call" | "calculation" | "decision",
    "step": {current_step},
    "reasoning": "你的推理过程",
    "action": {{
        // 如果是 tool_call
        "tool_name": "工具名称",
        "params": {{"param1": "value1"}}
        
        // 如果是 calculation
        "calculation_type": "指标类型",
        "formula": "计算公式",
        "inputs": {{"data": "..."}}
        
        // 如果是 decision
        "action": "buy" | "sell" | "hold",
        "reason": "决策原因",
        "confidence": 0.0-1.0
    }},
    "intermediate_result": null,  // 如果是calculation，这里填写计算结果
    "next_step": "下一步指示"
}}
"""

# 创建 prompt 模板
prompt = ChatPromptTemplate.from_messages([
    ("system", system_prompt),
    MessagesPlaceholder(variable_name="execution_history"),  # 自动注入历史消息
    ("human", "请分析当前状态，决定下一步操作。")
])

# ReAct 循环中使用
def react_step(step_num, context):
    # 获取历史消息
    history = memory.chat_memory.messages
    
    # 调用 LLM（历史自动包含在 messages 中）
    messages = prompt.format_messages(
        rule_id=context['rule_id'],
        symbol=context['symbol'],
        runtime_status=context['runtime_status'],
        user_requirements=context['user_requirements'],
        available_tools=context['available_tools'],
        current_step=step_num,
        execution_history=history
    )
    
    response = llm.invoke(messages)
    
    # 解析 action
    action = parse_action(response.content)
    
    # 执行 action（工具调用或计算）
    result = execute_action(action)
    
    # 保存到历史
    memory.chat_memory.add_user_message(
        f"Step {step_num}: {action['reasoning']}"
    )
    memory.chat_memory.add_ai_message(
        f"执行结果: {json.dumps(result, ensure_ascii=False)}"
    )
    
    return action, result
```

**优势：**
- ✅ 更符合对话模式，LLM 天然理解 message history
- ✅ Token 使用更高效（模型可以压缩历史）
- ✅ 代码更清晰，符合 LangChain 最佳实践
- ✅ 支持 Function Calling（如果使用工具调用）
- ✅ 自动管理上下文窗口

### 执行历史记录

每次执行都会记录完整的执行历史，格式如下：

```python
execution_history = [
    {
        "step": 1,
        "type": "tool_call",
        "reasoning": "需要获取BTCUSDT的1小时K线数据来分析价格趋势",
        "tool_name": "get_kline_data",
        "params": {"exchange": "Binance", "symbol": "BTCUSDT", "timeframe": "1h", "limit": 100},
        "result": [{"time": 1234567890, "open": 50000, "high": 51000, "low": 49000, "close": 50500, "volume": 1000}],
        "timestamp": "2024-01-01T10:00:00"
    },
    {
        "step": 2,
        "type": "calculation",
        "reasoning": "根据策略规则，需要计算30日移动平均线",
        "calculation_type": "MA",
        "formula": "MA30 = sum(close[-30:]) / 30",
        "inputs": {"period": 30, "data": "kline_data"},
        "intermediate_result": {"ma30": 50200, "current_price": 50500, "price_above_ma": True},
        "timestamp": "2024-01-01T10:00:01"
    },
    {
        "step": 3,
        "type": "calculation",
        "reasoning": "检查RSI指标，确认是否超买超卖",
        "calculation_type": "RSI",
        "formula": "RSI(14) = ...",
        "inputs": {"period": 14, "data": "kline_data"},
        "intermediate_result": {"rsi": 65, "is_oversold": False, "is_overbought": False},
        "timestamp": "2024-01-01T10:00:02"
    },
    {
        "step": 4,
        "type": "decision",
        "reasoning": "价格突破MA30且RSI在正常区间，满足建仓条件",
        "action": "buy",
        "reason": "价格突破30日均线，趋势向上，RSI未超买",
        "confidence": 0.75,
        "timestamp": "2024-01-01T10:00:03"
    }
]
```

### 技术指标计算

由于当前指标工具都是 `NotImplementedError`，我们需要：
1. **实现指标计算函数**：在 `execution_agent` 中实现实际的指标计算逻辑
2. **或者让LLM自行计算**：提供K线数据，让LLM在 `calculation` action 中自行计算并返回结果

推荐方案：**混合模式**
- 简单指标（MA、EMA）：让LLM自行计算并返回结果
- 复杂指标（MACD、BOLL）：提供计算函数，LLM调用后获取结果

### 数据库扩展

为了追踪执行过程，建议在数据库中新增表：

```sql
CREATE TABLE IF NOT EXISTS execution_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id INTEGER NOT NULL,
    symbol TEXT NOT NULL,
    execution_id TEXT NOT NULL,  -- 每次执行的唯一ID
    step INTEGER NOT NULL,
    action_type TEXT NOT NULL,  -- tool_call, calculation, decision
    action_data TEXT NOT NULL,  -- JSON格式的完整action
    result_data TEXT,  -- JSON格式的结果
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (rule_id) REFERENCES saved_rules (id)
);
```

### 实现要点

1. **工具绑定**：将 `tools_catalog` 中的工具绑定到LLM，使用 LangChain 的 `bind_tools` 或自定义工具调用解析
2. **循环控制**：
   - 最大轮数限制（如10轮）
   - 超时控制
   - 提前终止条件（LLM返回 decision）
3. **错误处理**：
   - 工具调用失败时的重试机制
   - LLM返回格式错误时的处理
   - 异常情况的回退策略
4. **执行追踪**：
   - 实时记录每一步的执行结果
   - 支持查询历史执行记录
   - 提供执行过程的可视化

### 优势

1. ✅ **主动数据获取**：LLM决定需要什么数据，何时获取
2. ✅ **逐步计算**：可以看到每一步的计算过程和中间结果
3. ✅ **完整追踪**：记录完整的执行历史，便于调试和分析
4. ✅ **灵活扩展**：可以轻松添加新的工具或计算步骤
5. ✅ **可解释性**：每一步都有 reasoning，决策过程透明

### 潜在挑战

1. **LLM调用成本**：多轮交互会增加API调用次数
2. **执行时间**：逐步执行会比一步到位慢
3. **LLM稳定性**：需要处理LLM返回格式不一致的情况
4. **指标计算**：需要决定是让LLM计算还是提供函数

## 下一步

请确认：
1. 这个方案是否符合你的预期？
2. 是否需要调整 action 格式？
3. 指标计算采用哪种方式（LLM自行计算 vs 提供函数）？
4. 是否需要实现执行日志的数据库存储？

确认后我将开始实现。

