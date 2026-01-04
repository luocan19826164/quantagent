"""
工具清单（仅能力与边界，不执行调用）

说明：
- 这些函数全部用 @tool 注解，仅用于向LLM暴露"可用能力/参数边界/返回结构/示例用法"。
- 在本策略收集Agent中，这些工具不会被实际调用；它们是"能力约束"的知识，不产生 action。
- 未来若实现执行Agent，可复用这些定义对接真实数据源。
"""

from typing import List, Dict, Any
from langchain.tools import tool
from .binance.client import get_binance_client

# ============ 能力常量 ============

SUPPORTED_TIMEFRAMES: List[str] = ["1m","5m","15m","30m","1h","4h","1d","1w","1M"]

# ============ 交易所与产品映射（默认数据）===========

# 交易所支持的产品类型（代码级别使用英文）
EXCHANGE_PRODUCTS: Dict[str, List[str]] = {
    "Binance": ["spot", "contract"],
    "OKX": ["spot", "contract"],
    "Bybit": ["spot", "contract"],
    "Coinbase": ["spot"],
    "Kraken": ["spot"],
    "NYSE": [],  # 股票交易所，不支持加密货币产品
    "NASDAQ": [],  # 股票交易所，不支持加密货币产品
}


@tool
def list_exchanges() -> List[str]:
    """
    获取支持的交易所列表。
    
    返回：交易所名称列表，如 ["Binance", "OKX", "Bybit", "NYSE", "NASDAQ"]
    
    说明：
    - Binance, OKX, Bybit → 支持加密货币交易
    - NYSE, NASDAQ → 支持股票交易，不支持加密货币
    """
    return list(EXCHANGE_PRODUCTS.keys())


@tool  
def list_products_by_exchange(exchange: str) -> List[str]:
    """
    根据交易所获取其支持的产品类型。
    
    参数：
      - exchange: 交易所名称（如"Binance", "OKX", "NYSE"）
    
    返回：产品类型列表，如 ["spot", "contract"] 或 ["futures", "options"]
    
    产品类型说明：
    - spot: 现货
    - contract: 合约
    - futures: 期货
    - options: 期权
    """
    return EXCHANGE_PRODUCTS.get(exchange, [])


@tool
def list_symbols_by_exchange(exchange: str) -> List[str]:
    """
    根据交易所获取其支持的交易对列表。
    
    参数：
      - exchange: 交易所名称
    
    返回：交易对列表，如 ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    
    约束：
    - NYSE、NASDAQ等股票交易所不支持加密货币交易对
    - Binance、OKX等支持主流币种交易对
    """
    # 暂时固定返回一些主流币对，未来可对接真实的 list_symbols
    if exchange == "Binance":
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT"]
    return []


@tool
def validate_exchange_product_symbol(exchange: str, product: str, symbol: str) -> bool:
    """
    验证交易所、产品类型和交易对的组合是否有效。
    
    参数：
      - exchange: 交易所名称
      - product: 产品类型（"spot"、"contract"等）
      - symbol: 交易对（如"BTCUSDT"）
    
    返回：布尔值，True表示组合有效，False表示无效
    """
    supported_products = EXCHANGE_PRODUCTS.get(exchange, [])
    if product not in supported_products:
        return False
    
    # 简单的白名单验证
    valid_symbols = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "ADAUSDT"]
    if symbol not in valid_symbols:
        return False
        
    return True








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
    raise NotImplementedError("指标计算由LLM自行分析历史K线数据完成，此处仅为能力定义")


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
    raise NotImplementedError("指标计算由LLM自行分析历史K线数据完成，此处仅为能力定义")


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
    raise NotImplementedError("指标计算由LLM自行分析历史K线数据完成，此处仅为能力定义")


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
    raise NotImplementedError("指标计算由LLM自行分析历史K线数据完成，此处仅为能力定义")


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
    raise NotImplementedError("指标计算由LLM自行分析历史K线数据完成，此处仅为能力定义")


@tool
def get_kline_data(exchange: str, symbol: str, timeframe: str, limit: int = 100) -> List[Dict[str, float]]:
    """
    获取K线数据。
    
    参数：
      - exchange: 交易所名称 (目前仅支持 Binance)
      - symbol: 交易对 (如 "BTCUSDT")
      - timeframe: 时间周期 (如 "1h", "1d")
      - limit: 获取数量 (默认100)
    
    返回：
      - [{"time": int, "open": float, "high": float, "low": float, "close": float, "volume": float}, ...]
    """
    if exchange == "Binance":
        client = get_binance_client()
        return client.get_kline_data(symbol, timeframe, limit)
    return []


@tool
def place_order(exchange: str, symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> Dict[str, Any]:
    """
    执行下单操作。
    
    参数：
      - exchange: 交易所 (目前仅支持 Binance)
      - symbol: 交易对 (如 "BTCUSDT")
      - side: "buy" 或 "sell"
      - order_type: "market" (市价) 或 "limit" (限价)
      - quantity: 交易数量 (Base Asset Quantity)，指要购买或出售的资产数量（例如 0.1 BTC）。
        *注意：如果你只知道投资金额（如 100 USDT），必须先计算 quantity = 投资金额 / 当前价格。*
      - price: 价格 (限价单必填)
    
    返回：
      - {"order_id": str, "status": str, "price": float, "quantity": float}
    """
    if exchange == "Binance":
        client = get_binance_client()
        return client.place_order(symbol, side, order_type, quantity, price)
    return {"error": f"Unsupported exchange: {exchange}", "status": "FAILED"}


# ============ 工具注册表（供 capability_manifest 自动提取信息） ============

ALL_TOOLS: List[Any] = [
    list_exchanges,
    list_products_by_exchange,
    list_symbols_by_exchange,
    validate_exchange_product_symbol,
    get_kline_data,
    place_order,
    indicator_ma,
    indicator_ema,
    indicator_rsi,
    indicator_macd,
    indicator_boll,
]


