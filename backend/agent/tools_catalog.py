"""
工具清单（仅能力与边界，不执行调用）

说明：
- 这些函数全部用 @tool 注解，仅用于向LLM暴露“可用能力/参数边界/返回结构/示例用法”。
- 在本策略收集Agent中，这些工具不会被实际调用；它们是“能力约束”的知识，不产生 action。
- 未来若实现执行Agent，可复用这些定义对接真实数据源。
"""

from typing import List, Dict, Any
from langchain.tools import tool

# ============ 能力常量（供清单生成使用；避免在运行期调用 @tool ============

SUPPORTED_MARKETS: List[str] = ["现货", "合约", "期货", "期权"]
SUPPORTED_TIMEFRAMES: List[str] = ["1m","5m","15m","30m","1h","4h","1d","1w","1M"]
SUPPORTED_SYMBOLS: List[str] = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT",
    "SOLUSDT", "XRPUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT",
    "AVAXUSDT", "ATOMUSDT", "UNIUSDT", "LTCUSDT", "ETCUSDT"
]

# （INDICATOR_SPECS 已删除，改为从 @tool 函数自动提取）


# ============ 市场 / 交易元信息 ============

@tool
def list_markets() -> List[str]:
    """
    获取支持的市场类型。
    用途：用于校验用户给出的 market 是否在能力范围内。

    返回：固定集合
    ["现货", "合约", "期货", "期权"]

    限制：只支持上述四种；其他市场类型（如股票、外汇等）不在当前能力范围。
    示例：
    - 校验：如果用户给出 "现货" → 可支持；"股票" → 不支持。
    """
    return SUPPORTED_MARKETS


@tool
def list_symbols() -> List[str]:
    """
    获取支持的交易对。
    用途：用于校验 symbols 白名单。

    返回：固定白名单（示例）
    [
      "BTCUSDT", "ETHUSDT", "BNBUSDT", "ADAUSDT", "DOGEUSDT",
      "SOLUSDT", "XRPUSDT", "DOTUSDT", "MATICUSDT", "LINKUSDT",
      "AVAXUSDT", "ATOMUSDT", "UNIUSDT", "LTCUSDT", "ETCUSDT"
    ]

    限制：只支持白名单内交易对；其他交易对视为超出能力范围。
    示例：
    - 校验："BTCUSDT" 支持；"BTCUSD" 不支持。
    """
    return SUPPORTED_SYMBOLS


@tool
def list_timeframes() -> List[str]:
    """
    获取支持的K线时间周期。
    用途：用于校验 timeframe 是否在能力范围内。

    返回：固定集合
    ["1m","5m","15m","30m","1h","4h","1d","1w","1M"]

    限制：仅支持上述集合；例如 "2m"、"3h" 不支持，应建议最近的可替代周期（如 1m 或 5m，1h 或 4h）。
    """
    return SUPPORTED_TIMEFRAMES


# ============ 指标能力（仅定义参数与返回结构） ============

@tool
def indicator_ma(period: int) -> float:
    """
    简单移动平均（MA）。
    参数：
      - period: int，范围 [1, 500]
    返回：
      - 当前周期的 MA 数值（float）
    适用：
      - 趋势跟随、均线突破、金叉/死叉（与双均线一起使用）
    限制：
      - 仅定义能力，未提供真实数据计算；需结合收盘价 close 等基础数据。
    示例：
      - 价格突破 MA(30) 视为看多信号。
    """
    raise NotImplementedError("能力定义占位：执行Agent中对接数据源后实现")


@tool
def indicator_ema(period: int) -> float:
    """
    指数移动平均（EMA）。
    参数：
      - period: int，范围 [1, 500]
    返回：
      - 当前周期的 EMA 数值（float）
    适用：
      - 更敏感的趋势判断、双均线交叉（快/慢 EMA）
    限制：
      - 仅能力声明；需结合 close 数据。
    示例：
      - EMA(12) 向上穿越 EMA(26) 视为金叉。
    """
    raise NotImplementedError("能力定义占位：执行Agent中对接数据源后实现")


@tool
def indicator_rsi(period: int) -> float:
    """
    相对强弱指标（RSI）。
    参数：
      - period: int，范围 [2, 100]
    返回：
      - RSI 数值（float，区间 0–100）
    适用：
      - 超买超卖（>70 超买，<30 超卖）
    限制：
      - 仅能力声明；阈值需由策略指定。
    示例：
      - RSI(14) < 30 视为超卖。
    """
    raise NotImplementedError("能力定义占位：执行Agent中对接数据源后实现")


@tool
def indicator_macd(fast: int, slow: int, signal: int) -> Dict[str, float]:
    """
    MACD 指标。
    参数：
      - fast:   int，范围 [2, 50]
      - slow:   int，范围 [fast+1, 100]
      - signal: int，范围 [1, 50]
    返回：
      - {"dif": float, "dea": float, "hist": float}
    适用：
      - 金叉/死叉（DIF 与 DEA 交叉）、柱体由负转正或回落。
    限制：
      - 仅能力声明；阈值/交叉方向由策略指定。
    示例：
      - DIF 上穿 DEA 视为金叉。
    """
    raise NotImplementedError("能力定义占位：执行Agent中对接数据源后实现")


@tool
def indicator_boll(period: int, std: float) -> Dict[str, float]:
    """
    布林带（BOLL）。
    参数：
      - period: int，范围 [5, 100]
      - std:    float，范围 [0.5, 3.0]
    返回：
      - {"upper": float, "middle": float, "lower": float}
    适用：
      - 突破上轨/下轨、回归中轨等策略。
    限制：
      - 仅能力声明；突破判定由策略指定。
    示例：
      - 收盘价上穿上轨视为突破。
    """
    raise NotImplementedError("能力定义占位：执行Agent中对接数据源后实现")


# ============ 工具注册表（供 capability_manifest 自动提取信息） ============

ALL_TOOLS: List[Any] = [
    list_markets,
    list_symbols,
    list_timeframes,
    indicator_ma,
    indicator_ema,
    indicator_rsi,
    indicator_macd,
    indicator_boll,
]


