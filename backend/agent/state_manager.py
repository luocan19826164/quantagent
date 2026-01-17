"""
状态管理模块
管理对话状态和收集的量化规则信息
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json


class QuantRuleState:
    """量化规则状态管理"""
    
    def __init__(self):
        self.user_requirements: Dict[str, Any] = {
            "exchange": None,  # 交易所名称
            "product": None,  # 产品类型（现货/合约/期货/期权）
            "symbols": [],  # 交易对列表
            "timeframe": None,  # K线周期
            "entry_rules": None,  # 建仓规则
            "exit_rules": None,  # 平仓规则
            "take_profit": None,  # 止盈
            "stop_loss": None,  # 止损
            "total_capital": None,  # 总本金
            "max_position_ratio": None,  # 最大仓位比例
            "other_conditions": [],  # 其他条件
            "execute_plan": None,  # 根据用户的完善策略条件，模拟描述执行的步骤，伪代码一步步说明
            "finish": False,  # 策略是否收集完成且可执行
        }
        
        # runtime_status 按 symbol 分别存储每个交易对的持仓状态
        # 结构: { "BTCUSDT": {...}, "ETHUSDT": {...} }
        # 每个 symbol 的状态结构:
        # {
        #     "is_holding": False,      # 是否持仓
        #     "entry_price": None,      # 开仓价格
        #     "quantity": 0.0,          # 持仓数量（base 资产）
        #     "position_side": None,    # 持仓方向：'long' 或 'short'（合约用）
        #     "db_order_id": None,      # 数据库订单 ID
        #     "last_update": None       # 最后更新时间
        # }
        self.runtime_status: Dict[str, Dict[str, Any]] = {}
        
        self.execution_logic: Dict[str, Any] = {
            "steps": [],  # 执行步骤
            "tools_used": [],  # 使用的工具
            "analysis": ""  # 逻辑分析
        }
        
        self.metadata = {
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "is_complete": False
        }
    
    def update_requirement(self, field: str, value: Any):
        """更新需求字段"""
        if field in self.user_requirements:
            self.user_requirements[field] = value
            self.metadata["updated_at"] = datetime.now().isoformat()
    
    def add_execution_step(self, step: str):
        """添加执行步骤"""
        if step not in self.execution_logic["steps"]:
            self.execution_logic["steps"].append(step)
    
    def add_tool_used(self, tool: str):
        """记录使用的工具"""
        if tool not in self.execution_logic["tools_used"]:
            self.execution_logic["tools_used"].append(tool)
    

    def set_analysis(self, analysis: str):
        """设置逻辑分析"""
        self.execution_logic["analysis"] = analysis
    
    def check_completeness(self) -> tuple[bool, List[str]]:
        """
        检查规则完整性
        
        完整性判断标准：
        1. 所有必填字段都已填写
        2. finish 字段为 True（表示工具充足，策略可执行）
        
        Returns:
            (是否完整, 缺失字段列表或原因列表)
        """
        required_fields = {
            "exchange": "交易所名称",
            "product": "产品类型",
            "symbols": "交易对",
            "timeframe": "K线周期",
            "entry_rules": "建仓规则",
            "take_profit": "止盈规则",
            "stop_loss": "止损规则",
            "max_position_ratio": "仓位比例",
            "total_capital": "总本金",
            "execute_plan": "执行计划"
        }
        
        missing = []
        
        # 检查必填字段
        for field, label in required_fields.items():
            value = self.user_requirements[field]
            if value is None or (isinstance(value, list) and len(value) == 0):
                missing.append(label)
        
        # 检查 finish 字段
        # 即使所有字段都填写了，如果 finish=false（工具不足），也不算完整
        finish_status = self.user_requirements.get("finish", False)
        if len(missing) == 0 and not finish_status:
            # 字段都填写了，但工具不足
            missing.append("系统工具不足（无法生成完整执行计划）")
        
        is_complete = len(missing) == 0 and finish_status
        self.metadata["is_complete"] = is_complete
        
        return is_complete, missing
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_requirements": self.user_requirements,
            "execution_logic": self.execution_logic,
            "runtime_status": self.runtime_status,
            "metadata": self.metadata
        }
    
    def to_json(self) -> str:
        """转换为JSON字符串"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
    
    def get_summary(self) -> str:
        """获取当前状态摘要"""
        summary = "📋 当前规则收集状态:\n\n"
        
        # 用户需求
        summary += "【用户需求】\n"
        
        # 产品类型映射
        product_map = {
            "spot": "现货",
            "contract": "合约",
            "futures": "期货",
            "options": "期权"
        }
        
        for key, value in self.user_requirements.items():
            if value:
                field_name = {
                    "exchange": "交易所",
                    "product": "产品类型",
                    "symbols": "交易对",
                    "timeframe": "K线周期",
                    "entry_rules": "建仓规则",
                    "exit_rules": "平仓规则",
                    "take_profit": "止盈",
                    "stop_loss": "止损",
                    "total_capital": "总本金",
                    "max_position_ratio": "最大仓位",
                    "other_conditions": "其他条件",
                    "finish": "完成状态"
                }.get(key, key)
                
                # 产品类型需要转换为中文显示
                display_value = value
                if key == "product" and value in product_map:
                    display_value = product_map[value]
                
                if isinstance(value, list) and len(value) > 0:
                    summary += f"• {field_name}: {', '.join(map(str, value))}\n"
                elif not isinstance(value, list):
                    summary += f"• {field_name}: {display_value}\n"
        
        
        # 完整性检查
        is_complete, missing = self.check_completeness()
        summary += f"\n【完整性】\n"
        if is_complete:
            summary += "✅ 规则信息已完整\n"
        else:
            summary += f"⚠️ 还需补充: {', '.join(missing)}\n"
        
        return summary


class SessionManager:
    """会话管理器"""
    
    def __init__(self):
        self.sessions: Dict[str, QuantRuleState] = {}
    
    def create_session(self, session_id: str) -> QuantRuleState:
        """创建新会话"""
        state = QuantRuleState()
        self.sessions[session_id] = state
        return state
    
    def get_session(self, session_id: str) -> Optional[QuantRuleState]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def delete_session(self, session_id: str):
        """删除会话"""
        if session_id in self.sessions:
            del self.sessions[session_id]
    
    def get_or_create_session(self, session_id: str) -> QuantRuleState:
        """获取或创建会话"""
        if session_id not in self.sessions:
            return self.create_session(session_id)
        return self.sessions[session_id]

