"""
Prompt配置加载器
从YAML文件加载prompt配置，实现代码和prompt的分离

重构说明：
- YAML中直接存储格式化好的文本块，避免复杂的字符串拼装
- Loader只负责读取YAML和填充模板占位符
- 支持多个配置文件（收集Agent、执行Agent等）
"""

import os
import yaml
from typing import Dict, Any, List
import inspect


class PromptLoader:
    """Prompt配置加载器"""
    
    def __init__(self, config_path: str = None):
        """
        初始化加载器
        
        Args:
            config_path: 配置文件路径，默认为当前目录下的prompts/prompt_config.yaml
        """
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "prompts", "rule_collect_agent_prompt.yaml")
        
        self.config_path = config_path
        self.config = self._load_config()
        self._prompts_dir = os.path.dirname(config_path)
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载prompt配置文件 {self.config_path}: {e}")
    
    def _load_yaml(self, filename: str) -> Dict[str, Any]:
        """加载指定的YAML文件"""
        filepath = os.path.join(self._prompts_dir, filename)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载配置文件 {filepath}: {e}")
    
    def build_system_prompt(self, capability_text: str, state_summary: str = "") -> str:
        """
        构建完整的系统提示词
        
        Args:
            capability_text: 能力清单文本
            state_summary: 当前状态摘要
            
        Returns:
            完整的系统提示词
        """
        template = self.config.get('system_prompt_template', '')
        
        # 转义花括号，避免被ChatPromptTemplate误认为变量占位符
        # 这些内容在后续的LangChain处理中需要保持原样
        capability_text = capability_text.replace("{", "{{").replace("}", "}}")
        output_schema = self.config.get('output_schema', '').replace("{", "{{").replace("}", "}}")
        field_instructions = self.config.get('field_instructions', '').replace("{", "{{").replace("}", "}}")
        examples = self.config.get('examples', '').replace("{", "{{").replace("}", "}}")
        
        # 填充模板占位符
        prompt = template.format(
            capability_text=capability_text,
            field_instructions=field_instructions,
            examples=examples,
            state_summary="{state_summary}",  # 保留为ChatPromptTemplate的变量
            output_schema=output_schema
        )
        
        return prompt


class ExecutionPromptLoader:
    """执行Agent Prompt加载器"""
    
    def __init__(self, config_path: str = None):
        if config_path is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(current_dir, "prompts", "execution_agent_prompt.yaml")
        
        self.config_path = config_path
        self.config = self._load_config()
    
    def _load_config(self) -> Dict[str, Any]:
        """加载YAML配置文件"""
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception as e:
            raise RuntimeError(f"无法加载prompt配置文件 {self.config_path}: {e}")
    
    def get_position_constraint(self, product: str, is_holding: bool, position_side: str = None) -> str:
        """根据产品类型和持仓状态获取约束提示"""
        constraints = self.config.get('position_constraints', {})
        
        if product == 'spot':
            if is_holding:
                return constraints.get('spot_holding', '')
            else:
                return constraints.get('spot_no_position', '')
        else:  # contract
            if not is_holding:
                return constraints.get('contract_no_position', '')
            elif position_side == 'long':
                return constraints.get('contract_long', '')
            elif position_side == 'short':
                return constraints.get('contract_short', '')
            else:
                return constraints.get('contract_no_position', '')
    
    def get_task_section(self, is_holding: bool, entry_rules: str, take_profit: str, stop_loss: str) -> str:
        """根据持仓状态获取任务描述"""
        templates = self.config.get('task_templates', {})
        
        if is_holding:
            template = templates.get('holding', '')
        else:
            template = templates.get('not_holding', '')
        
        return template.format(
            entry_rules=entry_rules,
            take_profit=take_profit,
            stop_loss=stop_loss
        )
    
    def get_execute_plan_section(self, execute_plan: str = None) -> str:
        """获取执行计划部分"""
        if execute_plan:
            return f"""
【执行计划】（请严格按照以下步骤执行）
{execute_plan}
"""
        else:
            return self.config.get('default_execute_flow', '')
    
    def generate_tools_text(self, tool_map: Dict[str, Any]) -> str:
        """从工具映射动态生成工具说明文本"""
        lines = []
        for tool_name, tool_func in tool_map.items():
            # 获取工具描述
            if hasattr(tool_func, 'description'):
                desc = tool_func.description.split('\n')[0]  # 取第一行作为简要说明
            else:
                desc = "无说明"
            
            # 获取参数信息
            params = []
            if hasattr(tool_func, 'args_schema') and tool_func.args_schema:
                try:
                    for field_name, field_info in tool_func.args_schema.__fields__.items():
                        if field_name == 'mock':  # 跳过 mock 参数
                            continue
                        params.append(field_name)
                except Exception:
                    pass
            elif hasattr(tool_func, 'func'):
                try:
                    sig = inspect.signature(tool_func.func)
                    for param_name, param in sig.parameters.items():
                        if param_name in ('self', 'cls', 'mock'):
                            continue
                        params.append(param_name)
                except Exception:
                    pass
            
            param_str = ', '.join(params) if params else "无参数"
            lines.append(f"- {tool_name}: {desc}")
            lines.append(f"  参数: {param_str}")
        
        return '\n'.join(lines)
    
    def build_system_prompt(self, context: Dict[str, Any], tool_map: Dict[str, Any]) -> str:
        """构建完整的系统提示词"""
        # 提取上下文信息
        symbol = context.get('symbol', 'N/A')
        exchange = context.get('exchange', 'Binance')
        timeframe = context.get('timeframe', '5m')
        product = context.get('product', 'spot')
        is_holding = context.get('is_holding', False)
        position_side = context.get('position_side')
        entry_price = context.get('entry_price')
        quantity = context.get('quantity', 0.0)
        entry_rules = context.get('entry_rules', '')
        take_profit = context.get('take_profit', '')
        stop_loss = context.get('stop_loss', '')
        execute_plan = context.get('execute_plan', '')
        current_time = context.get('current_time', '')
        
        # 生成各部分内容
        position_constraint = self.get_position_constraint(product, is_holding, position_side)
        task_section = self.get_task_section(is_holding, entry_rules, take_profit, stop_loss)
        execute_plan_section = self.get_execute_plan_section(execute_plan)
        available_tools = self.generate_tools_text(tool_map)
        
        # 获取模板
        template = self.config.get('system_prompt_template', '')
        role = self.config.get('role', '')
        output_format = self.config.get('output_format', {})
        important_rules = self.config.get('important_rules', '')
        
        # 填充模板
        prompt = template.format(
            role=role,
            current_time=current_time,
            symbol=symbol,
            exchange=exchange,
            timeframe=timeframe,
            product=product,
            product_display="现货" if product == "spot" else "合约",
            task_section=task_section,
            is_holding_display="是" if is_holding else "否",
            position_side_display=position_side if position_side else "无",
            entry_price_display=entry_price if entry_price else "无",
            quantity_display=quantity if quantity else "无",
            position_constraint=position_constraint,
            available_tools=available_tools,
            execute_plan_section=execute_plan_section,
            output_format_tool_call=output_format.get('tool_call', ''),
            output_format_calculation=output_format.get('calculation', ''),
            output_format_decision=output_format.get('decision', ''),
            important_rules=important_rules
        )
        
        return prompt
    
    def get_human_message(self) -> str:
        """获取 human 消息模板"""
        return self.config.get('human_message', '请分析当前状态并返回JSON格式的下一步操作。')


# 单例模式，避免重复加载配置文件
_prompt_loader_instance = None
_execution_prompt_loader_instance = None


def get_prompt_loader() -> PromptLoader:
    """获取PromptLoader单例（收集Agent用）"""
    global _prompt_loader_instance
    if _prompt_loader_instance is None:
        _prompt_loader_instance = PromptLoader()
    return _prompt_loader_instance


def get_execution_prompt_loader() -> ExecutionPromptLoader:
    """获取ExecutionPromptLoader单例（执行Agent用）"""
    global _execution_prompt_loader_instance
    if _execution_prompt_loader_instance is None:
        _execution_prompt_loader_instance = ExecutionPromptLoader()
    return _execution_prompt_loader_instance
