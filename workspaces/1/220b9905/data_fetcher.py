"""
数据获取模块
从yfinance获取BTC价格数据
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple


class DataFetcher:
    """数据获取类"""
    
    def __init__(self, symbol: str = "BTC-USD"):
        """
        初始化数据获取器
        
        Args:
            symbol: 交易对符号，默认为BTC-USD
        """
        self.symbol = symbol
        self.ticker = yf.Ticker(symbol)
    
    def fetch_historical_data(
        self, 
        days: int = 365,
        interval: str = "1d",
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        获取历史价格数据
        
        Args:
            days: 获取多少天的数据，默认365天
            interval: 数据间隔，默认"1d"（日线）
            end_date: 结束日期，格式"YYYY-MM-DD"，默认今天
            
        Returns:
            DataFrame包含以下列：
            - Open: 开盘价
            - High: 最高价
            - Low: 最低价
            - Close: 收盘价
            - Volume: 成交量
        """
        try:
            # 计算开始日期
            if end_date is None:
                end_date = datetime.now()
            else:
                end_date = datetime.strptime(end_date, "%Y-%m-%d")
            
            start_date = end_date - timedelta(days=days)
            
            # 获取数据
            data = self.ticker.history(
                start=start_date.strftime("%Y-%m-%d"),
                end=end_date.strftime("%Y-%m-%d"),
                interval=interval
            )
            
            if data.empty:
                raise ValueError(f"无法获取 {self.symbol} 的数据，请检查网络或符号")
            
            # 确保列名正确
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in data.columns:
                    raise ValueError(f"数据缺少必要列: {col}")
            
            # 清理数据：删除NaN值
            data = data.dropna()
            
            # 添加日期索引
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)
            
            print(f"成功获取 {self.symbol} 数据:")
            print(f"  时间范围: {data.index[0].date()} 到 {data.index[-1].date()}")
            print(f"  数据条数: {len(data)}")
            print(f"  数据列: {', '.join(data.columns.tolist())}")
            
            return data
            
        except Exception as e:
            print(f"获取数据失败: {e}")
            raise
    
    def get_data_info(self) -> dict:
        """
        获取交易对基本信息
        
        Returns:
            包含交易对信息的字典
        """
        try:
            info = self.ticker.info
            return {
                'symbol': info.get('symbol', self.symbol),
                'name': info.get('longName', 'Unknown'),
                'currency': info.get('currency', 'USD'),
                'market': info.get('market', 'crypto'),
            }
        except Exception as e:
            print(f"获取交易对信息失败: {e}")
            return {}


def fetch_btc_data(days: int = 365) -> Tuple[pd.DataFrame, dict]:
    """
    获取BTC数据的便捷函数
    
    Args:
        days: 获取多少天的数据
        
    Returns:
        (价格数据DataFrame, 交易对信息字典)
    """
    fetcher = DataFetcher("BTC-USD")
    info = fetcher.get_data_info()
    data = fetcher.fetch_historical_data(days=days)
    return data, info


if __name__ == "__main__":
    # 测试数据获取
    try:
        data, info = fetch_btc_data(days=30)  # 测试获取30天数据
        print("\n交易对信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")
        
        print("\n数据预览:")
        print(data.head())
        print(f"\n数据形状: {data.shape}")
        
    except Exception as e:
        print(f"测试失败: {e}")