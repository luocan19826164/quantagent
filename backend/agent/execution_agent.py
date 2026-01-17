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
from langchain_core.messages import SystemMessage
from .state_manager import QuantRuleState
from .prompt_loader import get_execution_prompt_loader
from tool.tools_catalog import get_kline_data, place_order, ALL_TOOLS

class QuantExecutionAgent:
    """量化规则执行Agent"""
    
    def __init__(self, db_module):
        self.db = db_module
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.running_jobs = {}  # rule_id -> job_id
        
        # 自动检测模型配置 - 优先使用 OpenAI/ChatGPT
        api_key = os.getenv("OPENAI_API_KEY")
        base_url = os.getenv("OPENAI_BASE_URL")
        
        # 优先使用 DeepSeek（deepseek-reasoner 推理能力更强）
        if os.getenv("DEEPSEEK_API_KEY"):
            api_key = os.getenv("DEEPSEEK_API_KEY")
            base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
            model_name = "deepseek-reasoner"  # 推理模型，数学能力更强
            logging.info("Using DeepSeek Reasoner model configuration")
        elif api_key:
            # 使用 OpenAI 时，强制使用 OpenAI 兼容的模型
            model_name = "gpt-4o"
            logging.info("Using OpenAI/ChatGPT model configuration")
        else:
            model_name = os.getenv("MODEL_NAME", "gpt-4o")
            logging.warning("No API key found immediately, will rely on env vars during invoke if possible")
            
        logging.info(f"Initializing Execution Agent with Model: {model_name}, Base URL: {base_url}")
        
        # 初始化LLM用于决策分析
        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0,
            api_key=api_key,
            base_url=base_url
        )
        
        # 工具映射字典（工具名称 -> 工具函数）
        # 注意：只暴露 get_kline_data 给 LLM，place_order 由代码层控制
        self.tool_map = {
            "get_kline_data": get_kline_data,
        }
        
        # 加载执行Agent的提示词配置
        self.prompt_loader = get_execution_prompt_loader()
        
        # Mock 模式标志（True: 模拟环境，不执行真实交易；False: 真实环境）
        # TODO: 未来可从环境变量或初始化参数获取
        self.mock_mode = True
        logging.info(f"Execution Agent running in {'MOCK' if self.mock_mode else 'REAL'} mode")

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
        import os, threading
        logging.info(f"Executing step for rule {rule_id} (ReAct mode) [PID: {os.getpid()}, Thread: {threading.current_thread().name}]")
        rule = self._get_rule_from_db(rule_id)
        if not rule:
            return
            
        requirements = rule['content']['user_requirements']
        # runtime_status 现在是按 symbol 存储的字典: {"BTCUSDT": {...}, "ETHUSDT": {...}}
        all_runtime_status = rule['content'].get('runtime_status', {})
        
        # 构建交易上下文（基础部分，symbol_status 会在循环中设置）
        trade_ctx = {
            "rule_id": rule_id,
            "exchange": requirements.get('exchange', 'Binance'),
            "product": requirements.get('product', 'spot'),
            "symbols": requirements.get('symbols', []),
            "timeframe": requirements.get('timeframe', '1d'),
            "total_capital": rule.get('total_capital', 0),
            "max_position_ratio": requirements.get('max_position_ratio', 0.1),
            "user_requirements": requirements,
            "all_runtime_status": all_runtime_status  # 保存完整的 runtime_status 用于更新
        }
        
        for symbol in trade_ctx["symbols"]:
            try:
                trade_ctx["symbol"] = symbol
                
                # 获取该 symbol 的 runtime_status（如果不存在则初始化）
                symbol_status = self._get_symbol_status(all_runtime_status, symbol)
                trade_ctx["runtime_status"] = symbol_status
                
                # 如果有持仓，先更新浮动盈亏
                if symbol_status.get('is_holding') and symbol_status.get('db_order_id'):
                    self._update_floating_pnl(trade_ctx)
                
                # 使用 ReAct 模式获取决策
                result = self._react_execute(rule_id, symbol, trade_ctx, max_steps=20)
                if not result.get("success"):
                    logging.warning(f"ReAct execution failed for rule {rule_id}, symbol {symbol}")
                    continue
                
                action = result.get("action", "hold")
                if action == "hold":
                    logging.info(f"Decision: HOLD for {symbol}")
                    continue
                
                # 根据产品类型分发执行
                if trade_ctx["product"] == "spot":
                    self._execute_spot_trade(action, trade_ctx)
                else:
                    self._execute_contract_trade(action, trade_ctx)
                
                logging.info(f"Execution completed for rule {rule_id}, symbol {symbol}: {action}")
                    
            except Exception as e:
                logging.error(f"Error in execute_step for rule {rule_id}, symbol {symbol}: {e}", exc_info=True)
    
    def _get_symbol_status(self, all_runtime_status: Dict, symbol: str) -> Dict:
        """获取指定 symbol 的 runtime_status，如果不存在则初始化"""
        if symbol not in all_runtime_status:
            all_runtime_status[symbol] = {
                "is_holding": False,
                "entry_price": None,
                "quantity": 0.0,
                "position_side": None,
                "db_order_id": None,
                "last_update": None
            }
        return all_runtime_status[symbol]
    
    # ==================== 现货交易 ====================
    
    def _execute_spot_trade(self, action: str, ctx: Dict):
        """执行现货交易"""
        if action == "buy":
            self._spot_buy(ctx)
        elif action == "sell":
            self._spot_sell(ctx)
    
    def _spot_buy(self, ctx: Dict):
        """现货买入（开仓）"""
        runtime_status = ctx["runtime_status"]
        if runtime_status.get('is_holding'):
            logging.warning(f"Already holding {ctx['symbol']}, skip buy")
            return
        
        current_price = self._get_current_price(ctx)
        if not current_price:
            return
        
        quantity = (ctx["total_capital"] * ctx["max_position_ratio"]) / current_price
        order_res = self._place_order(ctx, "buy", quantity)
        
        if order_res and "order_id" in order_res:
            db_order_id = self._create_order(
                ctx["rule_id"], ctx["symbol"], "buy", 
                quantity, current_price, order_res['order_id']
            )
            logging.info(f"[SPOT] Opened long: {ctx['symbol']} @ {current_price}, qty={quantity}, db_order_id={db_order_id}")
            
            runtime_status['is_holding'] = True
            runtime_status['entry_price'] = current_price
            runtime_status['quantity'] = quantity
            runtime_status['db_order_id'] = db_order_id
            runtime_status['last_update'] = datetime.now().isoformat()
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    def _spot_sell(self, ctx: Dict):
        """现货卖出（平仓）"""
        runtime_status = ctx["runtime_status"]
        if not runtime_status.get('is_holding'):
            logging.warning(f"Not holding {ctx['symbol']}, skip sell")
            return
        
        current_price = self._get_current_price(ctx)
        if not current_price:
            return
        
        quantity = runtime_status.get('quantity', 0)
        if quantity <= 0:
            logging.warning(f"No quantity to sell for {ctx['symbol']}")
            return
        
        order_res = self._place_order(ctx, "sell", quantity)
        
        if order_res and "order_id" in order_res:
            # 计算盈亏
            entry_price = runtime_status.get('entry_price', 0)
            pnl_percent = ((current_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            # 关闭订单
            db_order_id = runtime_status.get('db_order_id')
            if db_order_id:
                self._close_order(db_order_id, pnl_percent, current_price)
            logging.info(f"[SPOT] Closed long: {ctx['symbol']} @ {current_price}, PnL={pnl_percent:.2f}%")
            
            # 重置状态
            runtime_status['is_holding'] = False
            runtime_status['entry_price'] = None
            runtime_status['quantity'] = 0.0
            runtime_status['db_order_id'] = None
            runtime_status['last_update'] = datetime.now().isoformat()
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    # ==================== 合约交易 ====================
    
    def _execute_contract_trade(self, action: str, ctx: Dict):
        """执行合约交易"""
        if action == "buy":
            self._contract_buy(ctx)
        elif action == "sell":
            self._contract_sell(ctx)
    
    def _contract_buy(self, ctx: Dict):
        """合约买入：开多仓 或 平空仓"""
        runtime_status = ctx["runtime_status"]
        position_side = runtime_status.get('position_side')
        
        current_price = self._get_current_price(ctx)
        if not current_price:
            return
        
        if position_side == 'short':
            # 平空仓
            self._close_short_position(ctx, current_price)
        elif not runtime_status.get('is_holding'):
            # 开多仓
            self._open_long_position(ctx, current_price)
        else:
            logging.warning(f"Already holding long for {ctx['symbol']}, skip buy")
    
    def _contract_sell(self, ctx: Dict):
        """合约卖出：开空仓 或 平多仓"""
        runtime_status = ctx["runtime_status"]
        position_side = runtime_status.get('position_side')
        
        current_price = self._get_current_price(ctx)
        if not current_price:
            return
        
        if position_side == 'long':
            # 平多仓
            self._close_long_position(ctx, current_price)
        elif not runtime_status.get('is_holding'):
            # 开空仓
            self._open_short_position(ctx, current_price)
        else:
            logging.warning(f"Already holding short for {ctx['symbol']}, skip sell")
    
    def _open_long_position(self, ctx: Dict, price: float):
        """开多仓"""
        runtime_status = ctx["runtime_status"]
        quantity = (ctx["total_capital"] * ctx["max_position_ratio"]) / price
        
        order_res = self._place_order(ctx, "buy", quantity)
        if order_res and "order_id" in order_res:
            db_order_id = self._create_order(
                ctx["rule_id"], ctx["symbol"], "buy",
                quantity, price, order_res['order_id']
            )
            logging.info(f"[CONTRACT] Opened long: {ctx['symbol']} @ {price}, qty={quantity}")
            
            runtime_status['is_holding'] = True
            runtime_status['position_side'] = 'long'
            runtime_status['entry_price'] = price
            runtime_status['quantity'] = quantity
            runtime_status['db_order_id'] = db_order_id
            runtime_status['last_update'] = datetime.now().isoformat()
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    def _close_long_position(self, ctx: Dict, price: float):
        """平多仓"""
        runtime_status = ctx["runtime_status"]
        quantity = runtime_status.get('quantity', 0)
        if quantity <= 0:
            logging.warning(f"No quantity to close for {ctx['symbol']}")
            return
        
        order_res = self._place_order(ctx, "sell", quantity)
        if order_res and "order_id" in order_res:
            entry_price = runtime_status.get('entry_price', 0)
            pnl_percent = ((price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            
            db_order_id = runtime_status.get('db_order_id')
            if db_order_id:
                self._close_order(db_order_id, pnl_percent, price)
            logging.info(f"[CONTRACT] Closed long: {ctx['symbol']} @ {price}, PnL={pnl_percent:.2f}%")
            
            self._reset_runtime_status(runtime_status)
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    def _open_short_position(self, ctx: Dict, price: float):
        """开空仓"""
        runtime_status = ctx["runtime_status"]
        quantity = (ctx["total_capital"] * ctx["max_position_ratio"]) / price
        
        order_res = self._place_order(ctx, "sell", quantity)
        if order_res and "order_id" in order_res:
            db_order_id = self._create_order(
                ctx["rule_id"], ctx["symbol"], "sell",
                quantity, price, order_res['order_id']
            )
            logging.info(f"[CONTRACT] Opened short: {ctx['symbol']} @ {price}, qty={quantity}")
            
            runtime_status['is_holding'] = True
            runtime_status['position_side'] = 'short'
            runtime_status['entry_price'] = price
            runtime_status['quantity'] = quantity
            runtime_status['db_order_id'] = db_order_id
            runtime_status['last_update'] = datetime.now().isoformat()
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    def _close_short_position(self, ctx: Dict, price: float):
        """平空仓"""
        runtime_status = ctx["runtime_status"]
        quantity = runtime_status.get('quantity', 0)
        if quantity <= 0:
            logging.warning(f"No quantity to close for {ctx['symbol']}")
            return
        
        order_res = self._place_order(ctx, "buy", quantity)
        if order_res and "order_id" in order_res:
            entry_price = runtime_status.get('entry_price', 0)
            # 空仓盈亏：开仓价 - 平仓价
            pnl_percent = ((entry_price - price) / entry_price * 100) if entry_price > 0 else 0
            
            db_order_id = runtime_status.get('db_order_id')
            if db_order_id:
                self._close_order(db_order_id, pnl_percent, price)
            logging.info(f"[CONTRACT] Closed short: {ctx['symbol']} @ {price}, PnL={pnl_percent:.2f}%")
            
            self._reset_runtime_status(runtime_status)
            self._update_rule_runtime_status(ctx["rule_id"], ctx["all_runtime_status"])
    
    # ==================== 工具方法 ====================
    
    def _get_current_price(self, ctx: Dict) -> Optional[float]:
        """获取当前价格"""
        kline_data = get_kline_data.invoke({
            "exchange": ctx["exchange"],
            "symbol": ctx["symbol"],
            "timeframe": ctx["timeframe"],
            "limit": 1,
            "mock": self.mock_mode
        })
        if not kline_data:
            logging.warning(f"No kline data for {ctx['symbol']}")
            return None
        return kline_data[-1]['close']
    
    def _place_order(self, ctx: Dict, side: str, quantity: float) -> Optional[Dict]:
        """下单"""
        logging.info(f"Placing {side} order: {ctx['symbol']}, qty={quantity}, mock={self.mock_mode}")
        return place_order.invoke({
            "exchange": ctx["exchange"],
            "symbol": ctx["symbol"],
            "side": side,
            "order_type": "market",
            "quantity": quantity,
            "mock": self.mock_mode
        })
    
    def _update_floating_pnl(self, ctx: Dict):
        """
        更新持仓的浮动盈亏
        
        盈亏计算规则：
        - 现货/合约多头：(当前价 - 开仓价) / 开仓价 * 100
        - 合约空头：(开仓价 - 当前价) / 开仓价 * 100
        """
        runtime_status = ctx["runtime_status"]
        db_order_id = runtime_status.get('db_order_id')
        if not db_order_id:
            return
        
        current_price = self._get_current_price(ctx)
        if not current_price:
            return
        
        entry_price = runtime_status.get('entry_price', 0)
        if entry_price <= 0:
            return
        
        position_side = runtime_status.get('position_side')
        
        # 根据持仓方向计算盈亏
        # 注：现货没有 position_side（为 None），视为多头
        if position_side == 'short':
            # 合约空头：价格下跌盈利
            pnl_percent = ((entry_price - current_price) / entry_price) * 100
        else:
            # 现货 或 合约多头：价格上涨盈利
            pnl_percent = ((current_price - entry_price) / entry_price) * 100
        
        # 更新订单的浮动盈亏
        self._update_order_pnl(db_order_id, pnl_percent)
        logging.info(f"Updated floating PnL for {ctx['symbol']}: {pnl_percent:.2f}% (entry={entry_price}, current={current_price}, side={position_side or 'long'})")
    
    def _reset_runtime_status(self, runtime_status: Dict):
        """重置持仓状态"""
        runtime_status['is_holding'] = False
        runtime_status['position_side'] = None
        runtime_status['entry_price'] = None
        runtime_status['quantity'] = 0.0
        runtime_status['db_order_id'] = None
        runtime_status['last_update'] = datetime.now().isoformat()

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

    def _create_order(self, rule_id: int, symbol: str, side: str, amount: float, price: float, order_id: str) -> int:
        """
        开仓时创建订单记录
        
        Returns:
            int: 新创建的订单 ID（数据库自增 ID）
        """
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('''
            INSERT INTO orders (rule_id, symbol, side, amount, price, status, order_id, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (rule_id, symbol, side, amount, price, 'open', order_id, 0.0))
        conn.commit()
        db_order_id = c.lastrowid
        conn.close()
        return db_order_id
    
    def _update_order_pnl(self, db_order_id: int, pnl: float):
        """
        更新订单的浮动盈亏（持仓期间定期调用）
        
        Args:
            db_order_id: 数据库订单 ID
            pnl: 当前浮动盈亏百分比
        """
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE orders SET pnl = ? WHERE id = ?
        ''', (pnl, db_order_id))
        conn.commit()
        conn.close()
    
    def _close_order(self, db_order_id: int, pnl: float, close_price: float = None):
        """
        平仓时关闭订单，固定最终盈亏
        
        Args:
            db_order_id: 数据库订单 ID
            pnl: 最终盈亏百分比
            close_price: 平仓价格（可选，用于记录）
        """
        conn = self.db.get_db_connection()
        c = conn.cursor()
        c.execute('''
            UPDATE orders SET pnl = ?, status = 'closed' WHERE id = ?
        ''', (pnl, db_order_id))
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
        """执行工具调用（自动注入 mock 参数）"""
        try:
            if tool_name not in self.tool_map:
                return {"error": f"Unknown tool: {tool_name}", "status": "FAILED"}
            
            # 自动注入 mock 参数（LLM 不需要知道如何使用）
            params_with_mock = {**params, "mock": self.mock_mode}
            
            tool_func = self.tool_map[tool_name]
            result = tool_func.invoke(params_with_mock)
            return {"status": "SUCCESS", "result": result}
        except Exception as e:
            logging.error(f"Tool execution error: {e}")
            return {"error": str(e), "status": "FAILED"}
    
    
    def _create_prompt_template(self, context: Dict[str, Any]) -> ChatPromptTemplate:
        """创建 ReAct 执行的 prompt 模板（使用配置文件）"""
        runtime_status = context.get('runtime_status', {})
        user_requirements = context.get('user_requirements', {})
        
        # 构建 prompt loader 需要的上下文
        prompt_context = {
            'symbol': context.get('symbol', 'N/A'),
            'exchange': user_requirements.get('exchange', 'Binance'),
            'timeframe': user_requirements.get('timeframe', '5m'),
            'product': context.get('product', 'spot'),
            'is_holding': runtime_status.get('is_holding', False),
            'position_side': runtime_status.get('position_side'),
            'entry_price': runtime_status.get('entry_price'),
            'quantity': runtime_status.get('quantity', 0.0),
            'entry_rules': user_requirements.get('entry_rules', ''),
            'take_profit': user_requirements.get('take_profit', ''),
            'stop_loss': user_requirements.get('stop_loss', ''),
            'execute_plan': user_requirements.get('execute_plan', ''),
            'current_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        
        # 使用 prompt_loader 构建系统提示词
        system_prompt = self.prompt_loader.build_system_prompt(prompt_context, self.tool_map)
        human_message = self.prompt_loader.get_human_message()
        
        return ChatPromptTemplate.from_messages([
            SystemMessage(content=system_prompt),
            MessagesPlaceholder(variable_name="execution_history"),
            ("human", human_message)
        ])
    
    def _react_execute(self, rule_id: int, symbol: str, context: Dict[str, Any], max_steps: int = 20) -> Dict[str, Any]:
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
                logging.info(f"[ReAct Step {current_step}/{max_steps}] Rule {rule_id}, Symbol {symbol} - Invoking LLM...")
                messages = prompt_template.format_messages(
                    current_step=current_step,
                    execution_history=history
                )
                
                response = self.llm.invoke(messages)
                content = response.content
                
                # 记录原始 LLM 响应（截断以避免日志过长）
                logging.debug(f"[ReAct Step {current_step}] LLM raw response: {content[:500]}...")
                
                # 解析 JSON（处理可能的 markdown 包裹）
                if "```json" in content:
                    content = content.split("```json")[1].split("```")[0].strip()
                elif "```" in content:
                    content = content.split("```")[1].split("```")[0].strip()
                
                action_data = json.loads(content)
                action_type = action_data.get("type")
                reasoning = action_data.get("reasoning", "")
                action_detail = action_data.get("action", {})
                
                # 记录解析后的 action
                logging.info(f"[ReAct Step {current_step}] Type: {action_type}, Reasoning: {reasoning[:100]}...")
                
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
                    
                    logging.info(f"[ReAct Step {current_step}] Calling tool: {tool_name} with params: {json.dumps(params, ensure_ascii=False)[:200]}")
                    
                    # LLM 决定调用工具 → 存为 assistant
                    memory.chat_memory.add_ai_message(
                        f"Step {current_step}: {reasoning}\n调用工具: {tool_name}({json.dumps(params, ensure_ascii=False)})"
                    )
                    
                    # 执行工具
                    tool_result = self._execute_tool(tool_name, params)
                    step_record["result"] = tool_result
                    
                    # 记录工具执行结果
                    result_status = tool_result.get("status", "UNKNOWN")
                    logging.info(f"[ReAct Step {current_step}] Tool result: {tool_result}")
                    
                    # 工具执行结果 → 存为 user（外部反馈）
                    memory.chat_memory.add_user_message(
                        f"工具执行结果: {json.dumps(tool_result, ensure_ascii=False)}"
                    )
                    
                elif action_type == "calculation":
                    # 计算类型，LLM 已经在 intermediate_result 中提供了结果
                    intermediate_result = action_detail.get("intermediate_result", {})
                    step_record["intermediate_result"] = intermediate_result
                    
                    # 记录计算详情用于调试
                    calculation_type = action_detail.get('calculation_type', 'unknown')
                    logging.info(f"[ReAct Step {current_step}] Calculation type: {calculation_type}, Result: {json.dumps(intermediate_result, ensure_ascii=False)}")
                    
                    # 如果 intermediate_result 为空，说明 LLM 没有给出计算结果
                    if not intermediate_result:
                        logging.warning(f"[ReAct Step {current_step}] Empty intermediate_result! LLM may be stuck.")
                    
                    # LLM 进行计算并给出结果 → 存为 assistant
                    memory.chat_memory.add_ai_message(
                        f"Step {current_step}: {reasoning}\n计算类型: {calculation_type}\n计算结果: {json.dumps(intermediate_result, ensure_ascii=False)}"
                    )
                    
                    # 确认收到计算结果 → 存为 user（反馈）
                    memory.chat_memory.add_user_message(
                        f"收到 {calculation_type} 计算结果: {json.dumps(intermediate_result, ensure_ascii=False)}。请继续下一步操作。"
                    )
                    
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
                logging.error(f"LLM raw response: {response.content[:500] if response else 'No response'}")
                # 添加到 memory 以便下一步可以纠正
                memory.chat_memory.add_ai_message(
                    f"Step {current_step} failed: JSON parse error - {e}"
                )
                current_step += 1
                continue
            except KeyError as e:
                logging.error(f"KeyError in ReAct step {current_step}: {e}", exc_info=True)
                logging.error(f"Action data: {action_data if 'action_data' in locals() else 'Not parsed'}")
                current_step += 1
                continue
            except Exception as e:
                logging.error(f"Error in ReAct step {current_step}: {e}")
                logging.error(f"Exception type: {type(e).__name__}")
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
