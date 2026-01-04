import os
from binance.client import Client
from typing import List, Dict, Any
import logging

class BinanceToolClient:
    """Binance现货API工具客户端"""
    
    def __init__(self):
        self.api_key = os.getenv("BINANCE_API_KEY")
        self.api_secret = os.getenv("BINANCE_API_SECRET")
        # 如果没有配置，可以使用默认客户端进行只读操作（或报错）
        self.client = Client(self.api_key, self.api_secret)
        
    def get_kline_data(self, symbol: str, interval: str, limit: int = 100) -> List[Dict[str, float]]:
        """获取K线数据"""
        try:
            klines = self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
            result = []
            for k in klines:
                result.append({
                    "time": k[0],
                    "open": float(k[1]),
                    "high": float(k[2]),
                    "low": float(k[3]),
                    "close": float(k[4]),
                    "volume": float(k[5])
                })
            return result
        except Exception as e:
            logging.error(f"Binance get_kline_data error: {e}")
            return []

    def place_order(self, symbol: str, side: str, order_type: str, quantity: float, price: float = None) -> Dict[str, Any]:
        """下单"""
        try:
            side = side.upper()
            order_type = order_type.upper()
            
            params = {
                "symbol": symbol,
                "side": side,
                "type": order_type,
                "quantity": quantity
            }
            
            if order_type == "LIMIT":
                params["price"] = price
                params["timeInForce"] = "GTC"
            
            order = self.client.create_order(**params)
            return {
                "order_id": str(order.get("orderId")),
                "status": order.get("status"),
                "price": float(order.get("price", 0)) or price,
                "quantity": float(order.get("executedQty", 0)) or quantity
            }
        except Exception as e:
            logging.error(f"Binance place_order error: {e}")
            return {"error": str(e), "status": "FAILED"}

    def get_account_balance(self, asset: str) -> float:
        """获取资产余额"""
        try:
            balance = self.client.get_asset_balance(asset=asset)
            if balance:
                return float(balance.get("free", 0))
            return 0.0
        except Exception as e:
            logging.error(f"Binance get_account_balance error: {e}")
            return 0.0

# 单例模式
_binance_client = None

def get_binance_client():
    global _binance_client
    if _binance_client is None:
        _binance_client = BinanceToolClient()
    return _binance_client
