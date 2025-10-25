"""
量化Agent核心模块
基于LangChain实现的智能量化规则收集Agent
"""

from typing import Dict, Any
from langchain_openai import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from .state_manager import QuantRuleState
from .capability_manifest import get_capability_manifest_text
import os
from dotenv import load_dotenv

load_dotenv()


class QuantRuleCollectorAgent:
    """量化规则收集Agent"""
    
    def __init__(self, session_state: QuantRuleState):
        self.state = session_state
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True,
            output_key="output"
        )
        
        # 初始化LLM
        self.llm = ChatOpenAI(
            model=os.getenv("MODEL_NAME", "gpt-4o-mini"),
            temperature=0.7,
            api_key=os.getenv("OPENAI_API_KEY"),
            base_url=os.getenv("OPENAI_BASE_URL")
        )
        
        # 创建对话提示模板（无工具执行）
        self.prompt = self._create_prompt()
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """创建无工具执行的提示模板，并注入能力清单（仅作为判断依据）。"""
        capability_text = get_capability_manifest_text()
        # 转义花括号，避免被 ChatPromptTemplate 误认为变量占位符
        capability_text = capability_text.replace("{", "{{").replace("}", "}}")
        # 定义输出schema并转义
        output_schema = (
            '{\n'
            '  "reply": "给用户的自然语言回复",\n'
            '  "state_update": {\n'
            '    "market": null,\n'
            '    "symbols": [],\n'
            '    "timeframe": null,\n'
            '    "entry_rules": null,\n'
            '    "take_profit": null,\n'
            '    "stop_loss": null,\n'
            '    "max_position_ratio": null,\n'
            '    "indicators_required": [],\n'
            '    "feasible": false,\n'
            '    "reasons": "",\n'
            '    "missing_fields": []\n'
            '  }\n'
            '}'
        )
        output_schema = output_schema.replace("{", "{{").replace("}", "}}")
        
        system_prompt = f"""你是一个专业的量化交易策略顾问，你的任务是通过多轮对话帮助用户完善他们的量化交易策略。

你的职责：
1. 理解用户的策略想法，判断是否可以用【以下能力清单】实现。注意：这些能力仅用于判断与约束，你不能也无需返回任何工具调用或action。
2. 如果可以实现，引导用户逐步完善策略细节
3. 如果不能实现，友好地提示用户调整需求，建议在现有能力范围内的替代方案
4. 必须收集的关键信息：
   - 市场类型（现货/合约/期货/期权）
   - 交易对列表（具体的币种）
   - K线时间周期（1分钟/5分钟/1小时/日线等）
   - 建仓规则（什么条件下开仓）
   - 止盈规则（达到什么条件止盈）
   - 止损规则（达到什么条件止损）
   - 最大仓位比例（单次最大投入资金比例）

对话风格：
- 专业但友好，循序渐进
- 每次只问1-2个关键问题，不要一次问太多
- 用例子帮助用户理解
- 当用户描述不清楚时，给出具体的选项供选择
- 定期总结已收集的信息

【能力清单（仅用于判断，不可调用工具）】
{capability_text}

当你认为信息收集完整时，明确告知用户，并询问是否需要调整。

当前状态总结：
{{state_summary}}

输出格式（必须返回可被JSON解析；不要返回工具调用或action）：
{output_schema}
"""
        
        # 创建提示模板
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}")
        ])
        return prompt
    
    def chat(self, user_input: str) -> Dict[str, Any]:
        """
        处理用户输入
        
        Args:
            user_input: 用户输入的消息
            
        Returns:
            包含回复和状态的字典
        """
        try:
            # 获取当前状态摘要
            state_summary = self.state.get_summary()
            
            # 生成LLM回复（不执行工具）
            chain = self.prompt | self.llm
            # 注入历史对话
            mem_vars = self.memory.load_memory_variables({})
            chat_history = mem_vars.get("chat_history", [])
            raw = chain.invoke({
                "input": user_input,
                "state_summary": state_summary,
                "chat_history": chat_history
            })
            output_text = raw.content if hasattr(raw, "content") else str(raw)
            
            # 解析期望JSON
            import json
            reply = ""
            state_update: Dict[str, Any] = {}
            try:
                parsed = json.loads(output_text)
                reply = parsed.get("reply", "")
                state_update = parsed.get("state_update", {})
            except Exception:
                # 兜底：将文本作为回复，同时启用关键词提取辅助更新
                reply = output_text
                state_update = {}
            
            # 应用结构化更新
            self._apply_state_update(state_update)
            # 兜底：从自然语言中辅助提取
            if not state_update:
                self._update_state_from_conversation(user_input, reply)

            # 持久化到对话记忆
            try:
                self.memory.save_context({"input": user_input}, {"output": reply})
            except Exception:
                pass
            
            # 检查完整性
            is_complete, missing_fields = self.state.check_completeness()
            
            return {
                "success": True,
                "response": reply,
                "state": self.state.to_dict(),
                "is_complete": is_complete,
                "missing_fields": missing_fields
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "response": f"抱歉，处理您的请求时出现了错误：{str(e)}"
            }
    
    def _update_state_from_conversation(self, user_input: str, agent_response: str):
        """从对话中提取信息更新状态"""
        combined_text = (user_input + " " + agent_response).lower()
        
        # 提取市场类型
        markets = ["现货", "合约", "期货", "期权"]
        for market in markets:
            if market in combined_text:
                self.state.update_requirement("market", market)
                break
        
        # 提取时间周期
        timeframes = ["1分钟", "5分钟", "15分钟", "30分钟", "1小时", "4小时", "日线", "周线", "月线"]
        timeframe_map = {
            "1分钟": "1m", "5分钟": "5m", "15分钟": "15m", "30分钟": "30m",
            "1小时": "1h", "4小时": "4h", "日线": "1d", "周线": "1w", "月线": "1M"
        }
        for tf_label, tf_value in timeframe_map.items():
            if tf_label in user_input or tf_value in user_input:
                self.state.update_requirement("timeframe", tf_value)
                break
        
        # 提取指标
        indicators = ["MA", "EMA", "RSI", "MACD", "BOLL", "KDJ", "ATR", "VOLUME", "OBV", "SAR"]
        for indicator in indicators:
            if indicator.lower() in combined_text or self._get_chinese_name(indicator) in user_input:
                self.state.add_indicator_used(indicator)
        
        # 提取交易对
        symbols = ["BTC", "ETH", "BNB", "ADA", "DOGE", "SOL", "XRP", "DOT", "MATIC", "LINK"]
        found_symbols = []
        for symbol in symbols:
            if symbol.lower() in combined_text:
                found_symbols.append(f"{symbol}USDT")
        if found_symbols:
            current_symbols = self.state.user_requirements.get("symbols", [])
            updated_symbols = list(set(current_symbols + found_symbols))
            self.state.update_requirement("symbols", updated_symbols)
        
        # 提取建仓规则
        if any(keyword in user_input for keyword in ["建仓", "买入", "入场", "开仓", "做多", "做空"]):
            # 提取包含这些关键词的句子作为规则
            self.state.update_requirement("entry_rules", user_input)
        
        # 提取止盈止损
        if "止盈" in user_input or "获利" in user_input:
            # 尝试提取百分比
            import re
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', user_input)
            if match:
                self.state.update_requirement("take_profit", f"{match.group(1)}%")
        
        if "止损" in user_input or "停损" in user_input:
            import re
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', user_input)
            if match:
                self.state.update_requirement("stop_loss", f"{match.group(1)}%")
        
        # 提取仓位比例
        if "仓位" in user_input or "资金" in user_input:
            import re
            match = re.search(r'(\d+(?:\.\d+)?)\s*%', user_input)
            if match:
                ratio = float(match.group(1)) / 100
                self.state.update_requirement("max_position_ratio", ratio)
    
    def _get_chinese_name(self, indicator: str) -> str:
        """获取指标的中文名称"""
        names = {
            "MA": "均线",
            "EMA": "指数均线",
            "RSI": "相对强弱",
            "MACD": "指数平滑",
            "BOLL": "布林带",
            "KDJ": "随机指标",
            "ATR": "波幅",
            "VOLUME": "成交量"
        }
        return names.get(indicator, indicator)
    
    def _apply_state_update(self, su: Dict[str, Any]):
        """将模型返回的 state_update 应用到当前状态。"""
        if not su:
            return
        if su.get("market"):
            self.state.update_requirement("market", su["market"])
        if su.get("symbols"):
            self.state.update_requirement("symbols", su["symbols"])
        if su.get("timeframe"):
            self.state.update_requirement("timeframe", su["timeframe"])
        if su.get("entry_rules"):
            self.state.update_requirement("entry_rules", su["entry_rules"])
        if su.get("take_profit"):
            self.state.update_requirement("take_profit", su["take_profit"])
        if su.get("stop_loss"):
            self.state.update_requirement("stop_loss", su["stop_loss"])
        if su.get("max_position_ratio") is not None:
            self.state.update_requirement("max_position_ratio", su["max_position_ratio"])
        if su.get("indicators_required"):
            for ind in su["indicators_required"]:
                self.state.add_indicator_used(ind)

    def get_final_rules(self) -> Dict[str, Any]:
        """获取最终的规则配置"""
        return self.state.to_dict()
    
    def reset(self):
        """重置Agent"""
        self.memory.clear()
        self.state = QuantRuleState()

