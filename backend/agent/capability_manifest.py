"""
能力清单生成器（从 @tool 注解自动提取）：
- 遍历 tools_catalog.ALL_TOOLS，从函数签名、docstring、类型注解中提取能力信息
- 不执行工具，仅读取元数据生成清单文本或JSON
- 真正实现单一事实源（SSOT）
"""

from typing import Dict, Any, List, Optional
from . import tools_catalog as tc
import inspect
from .tools_catalog import EXCHANGE_PRODUCTS
from .tools_catalog import EXCHANGE_PRODUCTS

def _extract_tool_metadata(tool: Any) -> Dict[str, Any]:
    """
    从单个 @tool 对象中提取完整的元数据。
    
    这是唯一的提取逻辑，所有上层函数都调用它，避免重复代码。
    
    Returns:
        {
            "name": str,           # 工具名称
            "description": str,    # 完整描述（docstring）
            "parameters": Dict,    # 参数信息 {param_name: {type, required}}
            "param_names": List,   # 参数名列表（用于简单展示）
        }
    """
    # 提取名称
    tool_name = tool.name if hasattr(tool, 'name') else str(tool)
    
    # 提取描述（完整 docstring）
    tool_desc = tool.description if hasattr(tool, 'description') else ""
    
    # 提取参数信息
    parameters = {}
    param_names = []
    
    if hasattr(tool, 'args_schema') and tool.args_schema:
        # Pydantic model (如果使用了 args_schema)
        try:
            for field_name, field_info in tool.args_schema.__fields__.items():
                param_type = field_info.annotation.__name__ if hasattr(field_info.annotation, '__name__') else str(field_info.annotation)
                parameters[field_name] = {
                    "type": param_type,
                    "required": field_info.is_required()
                }
                param_names.append(field_name)
        except Exception:
            pass
    elif hasattr(tool, 'func'):
        # 直接从函数签名提取
        try:
            sig = inspect.signature(tool.func)
            for param_name, param in sig.parameters.items():
                if param_name in ('self', 'cls'):
                    continue
                param_type = param.annotation if param.annotation != inspect.Parameter.empty else 'Any'
                type_name = param_type.__name__ if hasattr(param_type, '__name__') else str(param_type)
                parameters[param_name] = {
                    "type": type_name,
                    "required": param.default == inspect.Parameter.empty
                }
                param_names.append(param_name)
        except Exception:
            pass
    
    return {
        "name": tool_name,
        "description": tool_desc,
        "parameters": parameters,
        "param_names": param_names,
    }


def _parse_docstring_details(docstring: str) -> Dict[str, str]:
    """
    从 docstring 中解析结构化信息（用于前端展示）。
    
    提取：
    - first_line: 第一行（简要说明）
    - example: 示例行
    """
    lines = [line.strip() for line in docstring.split('\n') if line.strip()]
    
    first_line = lines[0] if lines else "无说明"
    example = ""
    
    # 查找"示例："行
    for i, line in enumerate(lines):
        if '示例：' in line or '示例:' in line:
            if i + 1 < len(lines):
                example = lines[i + 1].strip('- ')
                break
    
    return {
        "first_line": first_line,
        "example": example
    }


# ============ 上层格式化函数（只负责组装，不做提取） ============

def get_capability_manifest_text() -> str:
    """从 @tool 函数自动提取能力清单文本，供 Agent System Prompt 注入"""
    parts = []
    parts.append("=== 工具能力清单（仅作判断依据，禁止返回action或调用） ===\n")
    
    # 固定常量信息
    parts.append(f"支持的时间周期: {', '.join(tc.SUPPORTED_TIMEFRAMES)}")
    
    # 交易所信息
    parts.append(f"\n支持的交易所: {', '.join(EXCHANGE_PRODUCTS.keys())}")
    parts.append("\n交易所支持的产品类型：")
    for exchange, products in EXCHANGE_PRODUCTS.items():
        if products:
            parts.append(f"  • {exchange}: {', '.join(products)}")
        else:
            parts.append(f"  • {exchange}: （股票交易所，不支持加密货币产品）")
    parts.append("")
    
    # 从工具中自动提取
    parts.append("可用工具与指标:")
    for tool in tc.ALL_TOOLS:
        meta = _extract_tool_metadata(tool)
        doc_info = _parse_docstring_details(meta["description"])
        
        # 格式化参数
        if meta["param_names"]:
            param_strs = []
            for pname in meta["param_names"]:
                pinfo = meta["parameters"].get(pname, {})
                param_strs.append(f"{pname}: {pinfo.get('type', 'Any')}")
            param_str = ", ".join(param_strs)
        else:
            param_str = "无参数"
        
        parts.append(f"  • {meta['name']}({param_str})")
        parts.append(f"    {doc_info['first_line']}")
    
    parts.append("")
    parts.append("策略需求与指标映射示例:")
    parts.append("  • 均线突破/金叉/死叉 → 需要 MA/EMA + close 数据")
    parts.append("  • RSI 超买超卖 → 需要 RSI，阈值范围建议 10–90")
    parts.append("  • MACD 金叉/死叉/柱转向 → 需要 MACD")
    parts.append("  • 布林带突破/回归 → 需要 BOLL + close")
    parts.append("")
    parts.append("重要提醒:")
    parts.append("  - 若用户需求超出以上能力（如不支持的周期、不支持的指标如KDJ/ATR/SAR/OBV），")
    parts.append("    需明确告知不可实现，并提供等价可行的替代方案。")
    parts.append("  - 禁止返回任何工具调用或action，这些能力仅用于可行性判断与引导提问。")
    
    return "\n".join(parts)


def get_capability_manifest_json() -> Dict[str, Any]:
    """从 @tool 函数自动提取能力清单 JSON，供程序消费"""
    tools_info = []
    
    for tool in tc.ALL_TOOLS:
        meta = _extract_tool_metadata(tool)
        tools_info.append({
            "name": meta["name"],
            "description": meta["description"],
            "parameters": meta["parameters"]
        })
    
    return {
        "timeframes": tc.SUPPORTED_TIMEFRAMES,
        "exchanges": EXCHANGE_PRODUCTS,
        "tools": tools_info
    }


def get_indicators_for_api() -> List[Dict[str, Any]]:
    """为 /api/indicators 接口生成指标列表（从 @tool 自动提取）"""
    indicators = []
    
    for tool in tc.ALL_TOOLS:
        meta = _extract_tool_metadata(tool)
        
        # 只返回指标相关的工具（名称包含 indicator）
        if 'indicator' not in meta["name"]:
            continue
        
        doc_info = _parse_docstring_details(meta["description"])
        
        # 提取指标名称（去除 indicator_ 前缀）
        display_name = meta["name"].replace('indicator_', '').upper()
        
        indicators.append({
            "name": display_name,
            "full_name": doc_info["first_line"],
            "description": doc_info.get("first_line", "无说明"),
            "parameters": meta["param_names"],
            "example": doc_info.get("example") or f"{display_name}(...) - 请参考文档"
        })
    
    return indicators
