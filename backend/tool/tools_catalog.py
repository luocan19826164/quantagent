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









@tool
def get_kline_data(exchange: str, symbol: str, timeframe: str, limit: int = 100, mock: bool = False) -> List[Dict[str, float]]:
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
    # mock 参数保留供扩展使用，当前逻辑不变
    if exchange == "Binance":
        client = get_binance_client()
        return client.get_kline_data(symbol, timeframe, limit)
    return []


@tool
def place_order(exchange: str, symbol: str, side: str, order_type: str, quantity: float, price: float = None, mock: bool = False) -> Dict[str, Any]:
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
    import uuid
    from datetime import datetime
    
    # mock 模式：返回模拟订单信息
    if mock:
        mock_order_id = f"mock_{uuid.uuid4().hex[:12]}"
        return {
            "order_id": mock_order_id,
            "status": "FILLED",
            "symbol": symbol,
            "side": side,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,  # 可能为 None，由调用方处理
            "filled_at": datetime.now().isoformat(),
            "mock": True
        }
    
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
]


