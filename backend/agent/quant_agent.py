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
from .prompt_loader import get_prompt_loader
import os
import json
import logging
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
        
        # 当前使用的模型信息
        self.current_model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        self.current_api_key = os.getenv("OPENAI_API_KEY")
        self.current_base_url = os.getenv("OPENAI_BASE_URL")
        
        # 初始化LLM (启用JSON模式)
        self.llm = ChatOpenAI(
            model=self.current_model,
            temperature=0.7,
            api_key=self.current_api_key,
            base_url=self.current_base_url,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
        
        # 创建对话提示模板（无工具执行）
        self.prompt = self._create_prompt()
    
    def _create_prompt(self) -> ChatPromptTemplate:
        """创建无工具执行的提示模板，并注入能力清单（仅作为判断依据）。"""
        # 从配置文件加载prompt
        prompt_loader = get_prompt_loader()
        capability_text = get_capability_manifest_text()
        
        # 构建系统提示词
        system_prompt = prompt_loader.build_system_prompt(
            capability_text=capability_text,
            state_summary=""
        )
        
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
            reply = ""
            state_update: Dict[str, Any] = {}
            try:
                parsed = json.loads(output_text)
                reply = parsed.get("reply", "")
                state_update = parsed.get("state_update", {})
                # 添加调试日志
                logging.info(f"AI返回的state_update: {state_update}")
            except Exception as e:
                # 兜底：将文本作为回复，同时启用关键词提取辅助更新
                logging.error(f"JSON解析失败: {e}")
                logging.error(f"AI原始输出: {output_text[:500]}")
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
        """轻量兜底：当AI未返回有效state_update时记录日志"""
        logging.warning(
            f"AI未返回有效的state_update，建议优化prompt。"
            f"用户输入: {user_input[:100]}{'...' if len(user_input) > 100 else ''}"
        )
        # 不做硬编码提取，完全依赖AI的理解能力
        # 如果频繁触发这个警告，说明需要优化prompt或检查AI输出格式
    
    def _apply_state_update(self, su: Dict[str, Any]):
        """将模型返回的 state_update 应用到当前状态，并进行基本的格式验证。"""
        if not su:
            return
        
        # 交易所验证
        if su.get("exchange"):
            valid_exchanges = ["Binance", "OKX", "Bybit", "NYSE", "NASDAQ", "Coinbase", "Kraken"]
            if su["exchange"] in valid_exchanges:
                self.state.update_requirement("exchange", su["exchange"])
            else:
                logging.warning(f"无效的交易所: {su['exchange']}")
        
        # 产品类型验证（验证与交易所的兼容性）
        if su.get("product"):
            from .tools_catalog import EXCHANGE_PRODUCTS
            exchange = self.state.user_requirements.get("exchange")
            
            if exchange and exchange in EXCHANGE_PRODUCTS:
                # 检查该交易所是否支持该产品
                if su["product"] in EXCHANGE_PRODUCTS[exchange]:
                    self.state.update_requirement("product", su["product"])
                else:
                    logging.warning(f"交易所 {exchange} 不支持产品 {su['product']}")
            else:
                # 没有交易所时，先保存
                valid_products = ["spot", "contract", "futures", "options"]
                if su["product"] in valid_products:
                    self.state.update_requirement("product", su["product"])
                else:
                    logging.warning(f"无效的产品类型: {su['product']}")
        
        # 交易对验证（数组累加）
        if su.get("symbols"):
            exchange = self.state.user_requirements.get("exchange")
            
            # 验证交易对格式（简单验证）
            if exchange in ["NYSE", "NASDAQ"]:
                # 股票交易所不支持USDT交易对
                filtered_symbols = [s for s in su["symbols"] if "USDT" not in s]
                if filtered_symbols != su["symbols"]:
                    logging.warning(f"股票交易所 {exchange} 不支持加密货币交易对，已过滤")
                su["symbols"] = filtered_symbols
            
            current_symbols = self.state.user_requirements.get("symbols", [])
            # 合并去重
            updated_symbols = list(set(current_symbols + su["symbols"]))
            self.state.update_requirement("symbols", updated_symbols)
        
        # K线周期验证
        if su.get("timeframe"):
            valid_timeframes = ["1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1M"]
            if su["timeframe"] in valid_timeframes:
                self.state.update_requirement("timeframe", su["timeframe"])
            else:
                logging.warning(f"无效的时间周期: {su['timeframe']}")
        
        # 建仓规则
        if su.get("entry_rules"):
            self.state.update_requirement("entry_rules", su["entry_rules"])
        
        # 止盈规则
        if su.get("take_profit"):
            self.state.update_requirement("take_profit", su["take_profit"])
        
        # 止损规则
        if su.get("stop_loss"):
            self.state.update_requirement("stop_loss", su["stop_loss"])
        
        # 仓位比例验证
        if su.get("max_position_ratio") is not None:
            ratio = su["max_position_ratio"]
            if isinstance(ratio, (int, float)) and 0 < ratio <= 1:
                self.state.update_requirement("max_position_ratio", ratio)
            else:
                logging.warning(f"无效的仓位比例: {ratio}，应该在0-1之间")
        
        # 指标验证（数组累加）
        if su.get("indicators_required"):
            valid_indicators = ["MA", "EMA", "RSI", "MACD", "BOLL", "KDJ", "ATR", "VOLUME", "OBV", "SAR"]
            for ind in su["indicators_required"]:
                if ind in valid_indicators:
                    self.state.add_indicator_used(ind)
                else:
                    logging.warning(f"无效的指标: {ind}")
        
        # 执行计划（仅在策略完善后生成）
        if su.get("execute_plan"):
            self.state.update_requirement("execute_plan", su["execute_plan"])
            logging.info(f"已生成执行计划，长度: {len(su['execute_plan'])} 字符")
        
        # finish 字段（标识策略是否完整可执行）
        if "finish" in su:
            self.state.update_requirement("finish", su["finish"])
            if su["finish"]:
                logging.info("策略收集完成且可执行")
            else:
                logging.info("策略信息收集中或工具不足")

    def get_final_rules(self) -> Dict[str, Any]:
        """获取最终的规则配置"""
        return self.state.to_dict()
    
    def reset(self):
        """重置Agent"""
        self.memory.clear()
        self.state = QuantRuleState()
    
    def switch_model(self, model_name: str, api_key: str, base_url: str = None):
        """
        切换模型，保持上下文和历史记录不变
        
        Args:
            model_name: 新的模型名称
            api_key: API密钥
            base_url: API基础URL（可选）
        """
        # 更新模型信息
        self.current_model = model_name
        self.current_api_key = api_key
        self.current_base_url = base_url
        
        # 重新创建LLM实例（memory和state保持不变）
        self.llm = ChatOpenAI(
            model=self.current_model,
            temperature=0.7,
            api_key=self.current_api_key,
            base_url=self.current_base_url,
            model_kwargs={"response_format": {"type": "json_object"}}
        )
    
    def get_current_model_info(self) -> Dict[str, Any]:
        """获取当前模型信息"""
        return {
            "model": self.current_model,
            "api_key_set": bool(self.current_api_key),
            "base_url": self.current_base_url
        }

