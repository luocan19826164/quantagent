"""
数据获取模块
用于获取加密货币历史价格数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
import yfinance as yf


class DataFetcher:
    """数据获取器类"""
    
    def __init__(self):
        """初始化数据获取器"""
        pass
    
    def get_btc_data(self, 
                     period: str = "1y", 
                     interval: str = "1d") -> Optional[pd.DataFrame]:
        """
        获取BTC历史价格数据
        
        Args:
            period: 数据周期，默认"1y"(一年)
            interval: 数据间隔，默认"1d"(日线)
            
        Returns:
            包含OHLCV数据的DataFrame，列名为['Open', 'High', 'Low', 'Close', 'Volume']
            如果获取失败返回None
        """
        try:
            # 使用yfinance获取BTC-USD数据
            ticker = "BTC-USD"
            btc = yf.Ticker(ticker)
            
            # 获取历史数据
            data = btc.history(period=period, interval=interval)
            
            if data.empty:
                print(f"警告: 未能获取到{ticker}的数据")
                return None
            
            # 重置索引，将日期作为普通列
            data = data.reset_index()
            
            # 确保数据按日期排序
            data = data.sort_values('Date').reset_index(drop=True)
            
            # 检查数据完整性
            if len(data) < 100:  # 至少需要100个数据点
                print(f"警告: 数据点数量不足，仅有{len(data)}个数据点")
                return None
            
            print(f"成功获取{ticker}数据:")
            print(f"数据范围: {data['Date'].min()} 到 {data['Date'].max()}")
            print(f"数据点数量: {len(data)}")
            print(f"数据列: {list(data.columns)}")
            
            return data
            
        except Exception as e:
            print(f"获取数据时发生错误: {str(e)}")
            return None
    
    def get_custom_period_data(self, 
                              start_date: str, 
                              end_date: str, 
                              interval: str = "1d") -> Optional[pd.DataFrame]:
        """
        获取自定义时间段的BTC数据
        
        Args:
            start_date: 开始日期，格式"YYYY-MM-DD"
            end_date: 结束日期，格式"YYYY-MM-DD"
            interval: 数据间隔，默认"1d"
            
        Returns:
            包含OHLCV数据的DataFrame
        """
        try:
            ticker = "BTC-USD"
            btc = yf.Ticker(ticker)
            
            # 获取指定时间段的数据
            data = btc.history(start=start_date, end=end_date, interval=interval)
            
            if data.empty:
                print(f"警告: 指定时间段内未能获取到数据")
                return None
            
            # 重置索引
            data = data.reset_index()
            data = data.sort_values('Date').reset_index(drop=True)
            
            print(f"成功获取自定义时间段数据:")
            print(f"数据范围: {data['Date'].min()} 到 {data['Date'].max()}")
            print(f"数据点数量: {len(data)}")
            
            return data
            
        except Exception as e:
            print(f"获取自定义时间段数据时发生错误: {str(e)}")
            return None
    
    def validate_data(self, data: pd.DataFrame) -> bool:
        """
        验证数据质量
        
        Args:
            data: 价格数据DataFrame
            
        Returns:
            数据是否有效
        """
        if data is None or data.empty:
            return False
        
        required_columns = ['Date', 'Open', 'High', 'Low', 'Close', 'Volume']
        if not all(col in data.columns for col in required_columns):
            print(f"数据缺少必要列，需要: {required_columns}")
            return False
        
        # 检查是否有空值
        if data[['Open', 'High', 'Low', 'Close']].isnull().any().any():
            print("数据中存在空值")
            return False
        
        # 检查价格逻辑性
        invalid_rows = (data['High'] < data['Low']) | \
                      (data['High'] < data['Open']) | \
                      (data['High'] < data['Close']) | \
                      (data['Low'] > data['Open']) | \
                      (data['Low'] > data['Close'])
        
        if invalid_rows.any():
            print(f"发现{invalid_rows.sum()}行价格数据不合理")
            return False
        
        print("数据验证通过")
        return True


def test_data_fetcher():
    """测试数据获取功能"""
    print("=== 测试数据获取模块 ===")
    
    fetcher = DataFetcher()
    
    # 测试获取最近一年数据
    print("\n1. 获取BTC最近一年数据:")
    data = fetcher.get_btc_data()
    
    if data is not None:
        print(f"数据预览:")
        print(data.head())
        print(f"\n数据统计:")
        print(data[['Open', 'High', 'Low', 'Close']].describe())
        
        # 验证数据
        is_valid = fetcher.validate_data(data)
        print(f"数据验证结果: {'通过' if is_valid else '失败'}")
    
    return data


if __name__ == "__main__":
    test_data_fetcher()