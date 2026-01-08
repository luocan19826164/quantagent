import logging
import json
import asyncio
import os
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from .state_manager import QuantRuleState
from tool.tools_catalog import get_kline_data, place_order, ALL_TOOLS
from tool.capability_manifest import get_capability_manifest_text

class QuantExecutionAgent:
    """量化规则执行Agent"""
    
    def __init__(self, db_module):
        self.db = db_module
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.running_jobs = {}  # rule_id -> job_id
        
        # 初始化LLM用于决策分析
        self.llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL"),
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        # 工具映射字典（工具名称 -> 工具函数）
        self.tool_map = {
            "get_kline_data": get_kline_data,
            "place_order": place_order,
        }
        
        # 获取工具能力清单文本
        self.available_tools_text = get_capability_manifest_text()

    def start_rule_execution(self, rule_id: int):
        """开始执行规则"""
        if rule_id in self.running_jobs:
            return True
            
        rule = self._get_rule_from_db(rule_id)
        if not rule:
            return False
            
        timeframe = rule['content']['user_requirements'].get('timeframe', '1d')
        cron_params = self._timeframe_to_cron(timeframe)
        
        job = self.scheduler.add_job(
            self.execute_step,
            'cron',
            args=[rule_id],
            id=f"rule_{rule_id}",
            **cron_params
        )
        self.running_jobs[rule_id] = job.id
        
        # 更新数据库状态
        self._update_rule_status(rule_id, 'running')
        logging.info(f"Started execution for rule {rule_id} with timeframe {timeframe}")
        return True

    def stop_rule_execution(self, rule_id: int):
        """停止执行规则"""
        if rule_id in self.running_jobs:
            self.scheduler.remove_job(self.running_jobs[rule_id])
            del self.running_jobs[rule_id]
            
        self._update_rule_status(rule_id, 'stopped')
        logging.info(f"Stopped execution for rule {rule_id}")
        return True

    def execute_step(self, rule_id: int):
        """单次执行逻辑 - 使用 ReAct 模式"""
        logging.info(f"Executing step for rule {rule_id} (ReAct mode)")
        rule = self._get_rule_from_db(rule_id)
        if not rule:
            return
            
        requirements = rule['content']['user_requirements']
        # 使用新的 runtime_status 结构
        runtime_status = rule['content'].get('runtime_status', {
            "is_holding": False,
            "entry_price": None,
            "quantity": 0.0,
            "position_side": None,
            "last_update": None
        })
        
        exchange = requirements.get('exchange', 'Binance')
        product = requirements.get('product', 'spot')  # 默认为现货
        symbols = requirements.get('symbols', [])
        timeframe = requirements.get('timeframe', '1d')
        total_capital = rule.get('total_capital', 0)
        max_position_ratio = requirements.get('max_position_ratio', 0.1)
        
        for symbol in symbols:
            try:
                # 准备执行上下文
                context = {
                    "rule_id": rule_id,
                    "symbol": symbol,
                    "exchange": exchange,
                    "timeframe": timeframe,
                    "total_capital": total_capital,
                    "max_position_ratio": max_position_ratio,
                    "runtime_status": runtime_status,
                    "user_requirements": requirements
                }
                
                # 使用 ReAct 模式执行
                result = self._react_execute(rule_id, symbol, context, max_steps=10)
                
                if not result.get("success"):
                    logging.warning(f"ReAct execution failed for rule {rule_id}, symbol {symbol}")
                    continue
                
                decision_action = result.get("action", "hold")
                
                # 执行最终决策 - 买入逻辑
                if decision_action == 'buy' and self._can_execute_buy(product, runtime_status):
                    # 需要先获取当前价格
                    kline_data = get_kline_data.invoke({
                        "exchange": exchange,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "limit": 1
                    })
                    
                    if not kline_data:
                        logging.warning(f"No kline data for {symbol}, cannot execute buy")
                        continue
                    
                    current_price = kline_data[-1]['close']
                    amount = total_capital * max_position_ratio
                    quantity = amount / current_price
                    
                    logging.info(f"ReAct Decision: BUY {symbol} at {current_price} with quantity {quantity} (product: {product})")
                    
                    order_res = place_order.invoke({
                        "exchange": exchange,
                        "symbol": symbol,
                        "side": "buy",
                        "order_type": "market",
                        "quantity": quantity
                    })
                    
                    if "order_id" in order_res:
                        # 记录订单
                        self._record_order(rule_id, symbol, "buy", quantity, current_price, order_res['order_id'])
                        # 更新运行态：使用新的状态更新函数
                        self._update_runtime_status_after_buy(product, runtime_status, current_price, quantity)
                        self._update_rule_runtime_status(rule_id, runtime_status)
                        
                # 执行最终决策 - 卖出逻辑
                elif decision_action == 'sell' and self._can_execute_sell(product, runtime_status):
                    # 需要先获取当前价格
                    kline_data = get_kline_data.invoke({
                        "exchange": exchange,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "limit": 1
                    })
                    
                    if not kline_data:
                        logging.warning(f"No kline data for {symbol}, cannot execute sell")
                        continue
                    
                    current_price = kline_data[-1]['close']
                    
                    # 获取持仓数量 - **必须使用 quantity（base 资产数量）**
                    quantity_to_sell = runtime_status.get('quantity', 0.0)
                    
                    # 如果是合约且是开空仓，需要计算数量
                    if product in ["contract", "futures"] and not runtime_status.get('is_holding'):
                        # 开空仓：计算 base 资产数量
                        amount = total_capital * max_position_ratio
                        quantity_to_sell = amount / current_price
                    
                    if quantity_to_sell <= 0:
                        logging.warning(f"No quantity to sell for {symbol}, current quantity: {quantity_to_sell}")
                        continue
                    
                    logging.info(f"ReAct Decision: SELL {symbol} at {current_price} with quantity {quantity_to_sell} (product: {product})")
                    
                    # 卖出逻辑：使用实际持仓数量
                    order_res = place_order.invoke({
                        "exchange": exchange,
                        "symbol": symbol,
                        "side": "sell",
                        "order_type": "market",
                        "quantity": quantity_to_sell
                    })
                    
                    if "order_id" in order_res:
                        # 记录订单
                        self._record_order(rule_id, symbol, "sell", quantity_to_sell, current_price, order_res.get('order_id', 'SELL'))
                        # 更新运行态：使用新的状态更新函数
                        self._update_runtime_status_after_sell(product, runtime_status, current_price, quantity_to_sell)
                        self._update_rule_runtime_status(rule_id, runtime_status)
                
                # 记录执行历史（可选：保存到数据库）
                logging.info(f"Execution completed for rule {rule_id}, symbol {symbol}: {decision_action}")
                    
            except Exception as e:
                logging.error(f"Error in execute_step for rule {rule_id}, symbol {symbol}: {e}", exc_info=True)

    def _get_rule_from_db(self, rule_id: int):
        """从数据库读取规则"""
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('SELECT * FROM saved_rules WHERE id = ?', (rule_id,))
        row = c.fetchone()
        conn.close()
        if row:
            return {
                "id": row['id'],
                "content": json.loads(row['rule_content']),
                "total_capital": row['total_capital'],
                "status": row['status']
            }
        return None

    def _update_rule_status(self, rule_id: int, status: str):
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('UPDATE saved_rules SET status = ? WHERE id = ?', (status, rule_id))
        conn.commit()
        conn.close()

    def _update_rule_runtime_status(self, rule_id: int, runtime_status: Dict):
        """更新规则的运行态数据"""
        rule = self._get_rule_from_db(rule_id)
        if not rule:
            return
            
        content = rule['content']
        content['runtime_status'] = runtime_status
        
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('UPDATE saved_rules SET rule_content = ? WHERE id = ?', 
                  (json.dumps(content, ensure_ascii=False), rule_id))
        conn.commit()
        conn.close()

    def _record_order(self, rule_id: int, symbol: str, side: str, amount: float, price: float, order_id: str):
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO orders (rule_id, symbol, side, amount, price, status, order_id)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (rule_id, symbol, side, amount, price, 'filled', order_id))
        conn.commit()
        conn.close()

    def _timeframe_to_cron(self, timeframe: str) -> Dict:
        """将K线周期映射为APScheduler的cron参数"""
        if timeframe == '1m': return {'minute': '*/1'}
        if timeframe == '5m': return {'minute': '*/5'}
        if timeframe == '15m': return {'minute': '*/15'}
        if timeframe == '30m': return {'minute': '*/30'}
        if timeframe == '1h': return {'hour': '*/1'}
        if timeframe == '4h': return {'hour': '*/4'}
        if timeframe == '1d': return {'hour': '0'} # 每天0点
        return {'hour': '0'}
    
    def _execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """执行工具调用"""
        try:
            if tool_name not in self.tool_map:
                return {"error": f"Unknown tool: {tool_name}", "status": "FAILED"}
            
            tool_func = self.tool_map[tool_name]
            result = tool_func.invoke(params)
            return {"status": "SUCCESS", "result": result}
        except Exception as e:
            logging.error(f"Tool execution error: {e}")
            return {"error": str(e), "status": "FAILED"}
    
    def _can_execute_buy(self, product: str, runtime_status: Dict) -> bool:
        """
        判断是否可以执行买入操作
        
        Args:
            product: 产品类型 "spot" 或 "contract"
            runtime_status: 当前持仓状态
            
        Returns:
            bool: 是否可以买入
        """
        is_holding = runtime_status.get('is_holding', False)
        position_side = runtime_status.get('position_side')
        
        if product == "spot":
            # 现货：不能重复买入（必须先卖出才能再买入）
            return not is_holding
        elif product in ["contract", "futures"]:
            # 合约：可以开多仓，或平空仓
            if not is_holding:
                # 没有持仓 → 可以开多仓
                return True
            elif position_side == 'short':
                # 已有空仓 → 可以买入平空仓
                return True
            elif position_side == 'long':
                # 已有多仓 → 不能重复开多（但可以继续持有）
                return False
            else:
                return True  # 未知状态，允许尝试
        else:
            return False
    
    def _can_execute_sell(self, product: str, runtime_status: Dict) -> bool:
        """
        判断是否可以执行卖出操作
        
        Args:
            product: 产品类型 "spot" 或 "contract"
            runtime_status: 当前持仓状态
            
        Returns:
            bool: 是否可以卖出
        """
        is_holding = runtime_status.get('is_holding', False)
        position_side = runtime_status.get('position_side')
        
        if product == "spot":
            # 现货：必须先持有才能卖出
            return is_holding
        elif product in ["contract", "futures"]:
            # 合约：可以开空仓，或平多仓
            if not is_holding:
                # 没有持仓 → 可以开空仓
                return True
            elif position_side == 'long':
                # 已有多仓 → 可以卖出平多仓
                return True
            elif position_side == 'short':
                # 已有空仓 → 不能重复开空（但可以继续持有）
                return False
            else:
                return True  # 未知状态，允许尝试
        else:
            return False
    
    def _update_runtime_status_after_buy(self, product: str, runtime_status: Dict, price: float, quantity: float):
        """
        买入后更新持仓状态
        
        Args:
            product: 产品类型 "spot" 或 "contract"
            runtime_status: 当前持仓状态
            price: 成交价格
            quantity: 买入数量（base 资产）- **这是平仓时必须使用的数量**
        """
        if product == "spot":
            # 现货：开仓
            runtime_status['is_holding'] = True
            runtime_status['entry_price'] = price
            runtime_status['quantity'] = quantity  # base 资产数量（固定值，用于平仓）
            runtime_status['position_side'] = None  # 现货不需要方向
        elif product in ["contract", "futures"]:
            if runtime_status.get('position_side') == 'short':
                # 平空仓
                runtime_status['is_holding'] = False
                runtime_status['position_side'] = None
                runtime_status['entry_price'] = None
                runtime_status['quantity'] = 0.0  # 清空 base 资产数量
            else:
                # 开多仓
                runtime_status['is_holding'] = True
                runtime_status['position_side'] = 'long'
                runtime_status['entry_price'] = price
                runtime_status['quantity'] = quantity  # base 资产数量（固定值，用于平仓）
        
        runtime_status['last_update'] = datetime.now().isoformat()
    
    def _update_runtime_status_after_sell(self, product: str, runtime_status: Dict, price: float, quantity: float = None):
        """
        卖出后更新持仓状态
        
        Args:
            product: 产品类型 "spot" 或 "contract"
            runtime_status: 当前持仓状态
            price: 成交价格
            quantity: 卖出数量（base 资产），如果为 None 则全部平仓
        """
        if product == "spot":
            # 现货：平仓
            runtime_status['is_holding'] = False
            runtime_status['entry_price'] = None
            runtime_status['quantity'] = 0.0  # 清空 base 资产数量
            runtime_status['position_side'] = None
        elif product in ["contract", "futures"]:
            if runtime_status.get('position_side') == 'long':
                # 平多仓：使用实际的 quantity（base 资产数量）
                runtime_status['is_holding'] = False
                runtime_status['position_side'] = None
                runtime_status['entry_price'] = None
                runtime_status['quantity'] = 0.0  # 清空 base 资产数量
            else:
                # 开空仓：使用传入的 quantity（base 资产数量）
                current_quantity = runtime_status.get('quantity', 0.0)
                sell_quantity = quantity if quantity is not None else current_quantity
                runtime_status['is_holding'] = True
                runtime_status['position_side'] = 'short'
                runtime_status['entry_price'] = price
                runtime_status['quantity'] = sell_quantity  # base 资产数量（固定值，用于平仓）
        
        runtime_status['last_update'] = datetime.now().isoformat()
    
    def _create_prompt_template(self, context: Dict[str, Any]) -> ChatPromptTemplate:
        """创建 ReAct 执行的 prompt 模板"""
        rule_id = context.get('rule_id', 'N/A')
        symbol = context.get('symbol', 'N/A')
        runtime_status = context.get('runtime_status', {})
        user_requirements = context.get('user_requirements', {})
        
        # 使用模板占位符，而不是 f-string，这样 current_step 可以在 format_messages 时替换
        system_prompt = f"""你是一个专业的量化交易执行Agent。你的任务是逐步分析策略规则，调用工具获取数据，进行计算，最终做出交易决策。

【当前上下文】
- 规则ID: {rule_id}
- 交易对: {symbol}
- 当前持仓状态: {json.dumps(runtime_status, ensure_ascii=False)}
- 策略规则: {json.dumps(user_requirements, ensure_ascii=False, indent=2)}

【可用工具】
{self.available_tools_text}

【你的任务】
请基于当前上下文和执行历史，决定下一步操作。你可以：
1. 调用工具获取数据（如 get_kline_data）
2. 进行计算并记录中间结果（如计算MA、RSI等指标）
3. 做出最终决策（buy/sell/hold）

【返回格式要求】
请返回JSON格式的action：
{{
    "type": "tool_call" | "calculation" | "decision",
    "step": {{current_step}},
    "reasoning": "你的推理过程",
    "action": {{
        // 如果是 tool_call
        "tool_name": "工具名称",
        "params": {{"param1": "value1"}}
        
        // 如果是 calculation
        "calculation_type": "指标类型",
        "formula": "计算公式",
        "inputs": {{"data": "..."}},
        "intermediate_result": {{"result_key": "result_value"}}
        
        // 如果是 decision
        "action": "buy" | "sell" | "hold",
        "reason": "决策原因",
        "confidence": 0.0-1.0
    }},
    "next_step": "下一步指示"
}}"""
        
        return ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="execution_history"),
            ("human", "请分析当前状态，决定下一步操作。")
        ])
    
    def _react_execute(self, rule_id: int, symbol: str, context: Dict[str, Any], max_steps: int = 10) -> Dict[str, Any]:
        """
        ReAct 模式执行：逐步调用工具、计算、决策
        
        Args:
            rule_id: 规则ID
            symbol: 交易对
            context: 执行上下文（包含规则、持仓状态等）
            max_steps: 最大执行步数
            
        Returns:
            最终决策结果
        """
        # 为每次执行创建新的 memory（避免历史干扰）
        memory = ConversationBufferMemory(
            memory_key="execution_history",
            return_messages=True
        )
        # 创建 prompt 模板（包含完整的上下文信息）
        prompt_template = self._create_prompt_template(context)
        
        execution_history = []  # 记录完整执行历史
        current_step = 1
        
        while current_step <= max_steps:
            try:
                # 获取历史消息
                history = memory.chat_memory.messages
                
                # 调用 LLM
                messages = prompt_template.format_messages(
                    current_step=current_step,
                    execution_history=history
                )
                
                response = self.llm.invoke(messages)
                content = response.content
                
                # 解析 JSON（处理可能的 markdown 包裹）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                action_data = json.loads(content)
                action_type = action_data.get("type")
                reasoning = action_data.get("reasoning", "")
                action_detail = action_data.get("action", {})
                
                # 记录到执行历史
                step_record = {
                    "step": current_step,
                    "type": action_type,
                    "reasoning": reasoning,
                    "action": action_detail,
                    "timestamp": datetime.now().isoformat()
                }
                
                # 执行 action
                if action_type == "tool_call":
                    tool_name = action_detail.get("tool_name")
                    params = action_detail.get("params", {})
                    
                    # LLM 的决策（包含工具调用）应该使用 AIMessage
                    ai_message = AIMessage(
                        content=f"Step {current_step}: {reasoning}",
                        tool_calls=[{
                            "name": tool_name,
                            "args": params,
                            "id": f"call_{current_step}_{tool_name}"
                        }]
                    )
                    memory.chat_memory.add_message(ai_message)
                    
                    # 执行工具
                    tool_result = self._execute_tool(tool_name, params)
                    step_record["result"] = tool_result
                    
                    # 工具执行结果应该使用 ToolMessage
                    tool_message = ToolMessage(
                        content=json.dumps(tool_result, ensure_ascii=False),
                        tool_call_id=f"call_{current_step}_{tool_name}"
                    )
                    memory.chat_memory.add_message(tool_message)
                    
                elif action_type == "calculation":
                    # 计算类型，LLM 已经在 intermediate_result 中提供了结果
                    intermediate_result = action_detail.get("intermediate_result", {})
                    step_record["intermediate_result"] = intermediate_result
                    
                    # LLM 的计算结果应该使用 AIMessage
                    calculation_type = action_detail.get('calculation_type', 'unknown')
                    ai_message = AIMessage(
                        content=f"Step {current_step}: {reasoning}\n计算类型: {calculation_type}\n计算结果: {json.dumps(intermediate_result, ensure_ascii=False)}"
                    )
                    memory.chat_memory.add_message(ai_message)
                    
                elif action_type == "decision":
                    # 最终决策
                    decision_action = action_detail.get("action", "hold")
                    decision_reason = action_detail.get("reason", "")
                    confidence = action_detail.get("confidence", 0.0)
                    
                    step_record["decision"] = {
                        "action": decision_action,
                        "reason": decision_reason,
                        "confidence": confidence
                    }
                    
                    execution_history.append(step_record)
                    
                    logging.info(f"ReAct execution completed for rule {rule_id}, symbol {symbol}: {decision_action}")
                    return {
                        "success": True,
                        "action": decision_action,
                        "reason": decision_reason,
                        "confidence": confidence,
                        "execution_history": execution_history
                    }
                else:
                    logging.warning(f"Unknown action type: {action_type}")
                
                execution_history.append(step_record)
                current_step += 1
                
            except json.JSONDecodeError as e:
                logging.error(f"JSON parse error at step {current_step}: {e}")
                logging.error(f"LLM response: {content[:500]}")
                current_step += 1
                continue
            except Exception as e:
                logging.error(f"Error in ReAct step {current_step}: {e}")
                current_step += 1
                continue
        
        # 达到最大步数，返回 hold
        logging.warning(f"ReAct execution reached max steps ({max_steps}) for rule {rule_id}, symbol {symbol}")
        return {
            "success": False,
            "action": "hold",
            "reason": "达到最大执行步数，未做出决策",
            "execution_history": execution_history
        }
