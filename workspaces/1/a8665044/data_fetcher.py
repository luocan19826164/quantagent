"""
比特币历史数据获取模块
使用 yfinance 获取比特币最近一年的价格数据
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Tuple
import logging
import time
from requests.exceptions import RequestException

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BitcoinDataFetcher:
    """比特币数据获取器"""
    
    def __init__(self, symbol: str = "BTC-USD"):
        """
        初始化数据获取器
        
        Args:
            symbol: 交易对符号，默认为 BTC-USD
        """
        self.symbol = symbol
        self.ticker = yf.Ticker(symbol)
        
    def fetch_historical_data(
        self, 
        period: str = "1y",
        interval: str = "1d",
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        max_retries: int = 3,
        retry_delay: int = 5
    ) -> pd.DataFrame:
        """
        获取历史价格数据，包含重试机制
        
        Args:
            period: 数据周期，如 "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
            interval: 数据间隔，如 "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
            
        Returns:
            DataFrame 包含以下列：
            - Open: 开盘价
            - High: 最高价
            - Low: 最低价
            - Close: 收盘价
            - Volume: 成交量
            - Adj Close: 调整后收盘价
        """
        for attempt in range(max_retries):
            try:
                logger.info(f"开始获取 {self.symbol} 历史数据 (尝试 {attempt + 1}/{max_retries})...")
                
                # 使用 period 或 start_date/end_date 获取数据
                if start_date and end_date:
                    logger.info(f"获取日期范围: {start_date} 到 {end_date}")
                    data = self.ticker.history(start=start_date, end=end_date, interval=interval)
                else:
                    logger.info(f"获取周期: {period}, 间隔: {interval}")
                    data = self.ticker.history(period=period, interval=interval)
                
                if data.empty:
                    raise ValueError(f"未获取到 {self.symbol} 的历史数据")
                
                # 确保索引是 datetime 类型
                if not isinstance(data.index, pd.DatetimeIndex):
                    data.index = pd.to_datetime(data.index)
                
                # 按时间排序
                data = data.sort_index()
                
                # 计算日收益率
                data['Returns'] = data['Close'].pct_change()
                
                # 计算对数收益率（用于某些指标）
                data['Log_Returns'] = np.log(data['Close'] / data['Close'].shift(1))
                
                logger.info(f"成功获取 {len(data)} 条数据")
                logger.info(f"数据时间范围: {data.index[0]} 到 {data.index[-1]}")
                logger.info(f"数据列: {list(data.columns)}")
                
                return data
                
            except RequestException as e:
                logger.warning(f"网络请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    logger.info(f"等待 {retry_delay} 秒后重试...")
                    time.sleep(retry_delay)
                else:
                    logger.error(f"所有重试均失败")
                    raise
            except Exception as e:
                logger.error(f"获取数据失败: {e}")
                raise
        
        # 理论上不会执行到这里
        raise RuntimeError("获取数据失败")
    
    def get_recent_year_data(self, interval: str = "1d") -> pd.DataFrame:
        """
        获取最近一年的日线数据（默认方法）
        
        Args:
            interval: 数据间隔，默认为 "1d"（日线）
            
        Returns:
            最近一年的比特币价格数据
        """
        return self.fetch_historical_data(period="1y", interval=interval)
    
    def get_data_info(self, data: pd.DataFrame) -> dict:
        """
        获取数据的基本统计信息
        
        Args:
            data: 价格数据 DataFrame
            
        Returns:
            包含数据统计信息的字典
        """
        if data.empty:
            return {}
        
        info = {
            "symbol": self.symbol,
            "start_date": data.index[0].strftime("%Y-%m-%d"),
            "end_date": data.index[-1].strftime("%Y-%m-%d"),
            "total_days": len(data),
            "price_range": {
                "min": float(data['Close'].min()),
                "max": float(data['Close'].max()),
                "current": float(data['Close'].iloc[-1])
            },
            "volume_stats": {
                "avg_volume": float(data['Volume'].mean()),
                "max_volume": float(data['Volume'].max())
            },
            "return_stats": {
                "total_return": float((data['Close'].iloc[-1] / data['Close'].iloc[0] - 1) * 100),
                "avg_daily_return": float(data['Returns'].mean() * 100),
                "daily_return_std": float(data['Returns'].std() * 100)
            }
        }
        
        return info


def fetch_bitcoin_data(
    period: str = "1y",
    interval: str = "1d",
    save_to_csv: bool = True,
    csv_path: str = "data/btc_historical_data.csv"
) -> Tuple[pd.DataFrame, dict]:
    """
    获取比特币数据的便捷函数
    
    Args:
        period: 数据周期
        interval: 数据间隔
        save_to_csv: 是否保存到 CSV 文件
        csv_path: CSV 文件保存路径
        
    Returns:
        (数据 DataFrame, 统计信息字典)
    """
    # 创建数据获取器
    fetcher = BitcoinDataFetcher()
    
    # 获取数据
    data = fetcher.fetch_historical_data(period=period, interval=interval)
    
    # 获取统计信息
    info = fetcher.get_data_info(data)
    
    # 保存到 CSV
    if save_to_csv:
        import os
        os.makedirs(os.path.dirname(csv_path), exist_ok=True)
        data.to_csv(csv_path)
        logger.info(f"数据已保存到: {csv_path}")
    
    return data, info


if __name__ == "__main__":
    # 测试数据获取
    print("测试比特币数据获取...")
    
    try:
        # 获取最近一年的日线数据
        data, info = fetch_bitcoin_data(period="1y", interval="1d")
        
        print(f"\n数据获取成功!")
        print(f"数据形状: {data.shape}")
        print(f"时间范围: {info['start_date']} 到 {info['end_date']}")
        print(f"总天数: {info['total_days']}")
        print(f"价格范围: ${info['price_range']['min']:,.2f} - ${info['price_range']['max']:,.2f}")
        print(f"当前价格: ${info['price_range']['current']:,.2f}")
        print(f"总收益率: {info['return_stats']['total_return']:.2f}%")
        
        # 显示前几行数据
        print(f"\n前5行数据:")
        print(data.head())
        
        # 显示后几行数据
        print(f"\n后5行数据:")
        print(data.tail())
        
    except Exception as e:
        print(f"数据获取失败: {e}")