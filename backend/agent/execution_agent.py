import logging
import json
import asyncio
from typing import Dict, Any, List
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from langchain_openai import ChatOpenAI
from .state_manager import QuantRuleState
from tool.tools_catalog import get_kline_data, place_order

class QuantExecutionAgent:
    """量化规则执行Agent"""
    
    def __init__(self, db_module):
        self.db = db_module
        self.scheduler = BackgroundScheduler()
        self.scheduler.start()
        self.running_jobs = {}  # rule_id -> job_id
        
        # 初始化LLM用于决策分析
        import os
        self.llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            temperature=0,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )

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
        """单次执行逻辑"""
        logging.info(f"Executing step for rule {rule_id}")
        rule = self._get_rule_from_db(rule_id)
        if not rule:
            return
            
        requirements = rule['content']['user_requirements']
        runtime_status = rule['content'].get('runtime_status', {"is_holding": False, "entry_price": None})
        
        exchange = requirements.get('exchange', 'Binance')
        symbols = requirements.get('symbols', [])
        timeframe = requirements.get('timeframe', '1d')
        total_capital = rule.get('total_capital', 0)
        max_position_ratio = requirements.get('max_position_ratio', 0.1)
        
        for symbol in symbols:
            try:
                # 1. 获取数据
                kline_data = get_kline_data.invoke({
                    "exchange": exchange,
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "limit": 100
                })
                
                if not kline_data:
                    logging.warning(f"No kline data for {symbol}")
                    continue

                current_price = kline_data[-1]['close']
                
                # 2. LLM决策
                decision = self._get_llm_decision(rule, symbol, kline_data, runtime_status, current_price)
                
                # 3. 执行下单
                if decision.get('action') == 'buy' and not runtime_status.get('is_holding'):
                    amount = total_capital * max_position_ratio
                    quantity = amount / current_price
                    
                    logging.info(f"LLM Decision: BUY {symbol} at {current_price} with quantity {quantity}")
                    
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
                        # 更新运行态：已持仓，记录成交均价
                        runtime_status['is_holding'] = True
                        runtime_status['entry_price'] = current_price # 实际场景可以使用 order_res['price']
                        runtime_status['last_update'] = datetime.now().isoformat()
                        self._update_rule_runtime_status(rule_id, runtime_status)
                        
                elif decision.get('action') == 'sell' and runtime_status.get('is_holding'):
                    logging.info(f"LLM Decision: SELL {symbol} at {current_price}")
                    # 卖出通常需要获取持仓数量，此处简化为全平
                    # 在真实场景中，系统应该维护持仓量，这里我们简单假设卖出全部
                    # ...下单逻辑
                    
                    # 假定平仓成功
                    runtime_status['is_holding'] = False
                    runtime_status['entry_price'] = None
                    runtime_status['last_update'] = datetime.now().isoformat()
                    self._update_rule_runtime_status(rule_id, runtime_status)
                    self._record_order(rule_id, symbol, "sell", 0, current_price, "SELL_ALL")
                    
            except Exception as e:
                logging.error(f"Error in execute_step for rule {rule_id}, symbol {symbol}: {e}")

    def _get_llm_decision(self, rule: Dict, symbol: str, kdata: List, runtime_status: Dict, current_price: float) -> Dict:
        """调用LLM进行决策，注入运行态上下文"""
        
        is_holding = runtime_status.get('is_holding', False)
        entry_price = runtime_status.get('entry_price')
        pnl_pct = 0
        if is_holding and entry_price:
            pnl_pct = (current_price - entry_price) / entry_price * 100

        prompt = f"""
        你是一个专业的量化交易执行助手。请基于以下规则、数据和当前持仓状态，决定是否对交易对 {symbol} 进行操作。
        
        【当前账户/持仓状态】
        - 是否持仓: {"是" if is_holding else "否"}
        - 开仓价格 (entry_price): {entry_price if entry_price else "N/A"}
        - 当前价格 (current_price): {current_price}
        - 当前浮动盈亏: {f"{pnl_pct:.2f}%" if is_holding else "N/A"}
        
        【策略规则】
        {json.dumps(rule['content']['user_requirements'], ensure_ascii=False, indent=2)}
        
        【行情数据 (最近10条)】
        {json.dumps(kdata[-10:], indent=2)}
        
        请精确分析：
        1. 如果目前【未持仓】，是否满足建仓(entry_rules)条件？
        2. 如果目前【已持仓】，是否满足止盈(take_profit)或止损(stop_loss)条件？
        
        返回JSON格式:
        {{
            "analysis": "你的分析过程",
            "action": "buy" | "sell" | "hold",
            "reason": "操作原因"
        }}
        """
        try:
            res = self.llm.invoke(prompt)
            # 处理可能的markdown包裹
            content = res.content
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            return json.loads(content)
        except Exception as e:
            logging.error(f"LLM decision error: {e}")
            return {"action": "hold"}

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
