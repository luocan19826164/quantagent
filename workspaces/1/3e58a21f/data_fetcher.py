"""
数据获取模块
用于获取BTC最近一年的OHLCV数据
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
from typing import Optional, Tuple

# 导入指标计算模块
from indicators import add_rsi_to_data


class DataFetcher:
    """数据获取器类"""
    
    def __init__(self, symbol: str = "BTC-USD"):
        """
        初始化数据获取器
        
        Args:
            symbol: 交易对符号，默认为BTC-USD
        """
        self.symbol = symbol
        self.data: Optional[pd.DataFrame] = None
        
    def fetch_last_year_data(self, period: str = "1y", interval: str = "1d", add_rsi: bool = True, rsi_period: int = 14) -> pd.DataFrame:
        """
        获取最近一年的OHLCV数据
        
        Args:
            period: 时间周期，默认为1年
            interval: 数据间隔，默认为1天
            add_rsi: 是否添加RSI指标，默认为True
            rsi_period: RSI计算周期，默认为14
            
        Returns:
            pd.DataFrame: 包含OHLCV数据和可选技术指标的DataFrame
        """
        try:
            print(f"正在获取 {self.symbol} 的 {period} 数据，间隔: {interval}...")
            
            # 使用yfinance获取数据
            ticker = yf.Ticker(self.symbol)
            data = ticker.history(period=period, interval=interval)
            
            if data.empty:
                raise ValueError(f"无法获取 {self.symbol} 的数据，请检查交易对符号")
            
            # 确保列名正确
            required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_columns:
                if col not in data.columns:
                    raise ValueError(f"数据缺少必要列: {col}")
            
            # 重命名列以保持一致性
            data = data[required_columns].copy()
            
            # 添加时间索引
            data.index.name = 'Date'
            
            # 确保数据按时间排序
            data = data.sort_index()
            
            # 检查数据质量
            self._validate_data(data)
            
            self.data = data
            print(f"数据获取成功！共获取 {len(data)} 条记录")
            print(f"时间范围: {data.index[0]} 到 {data.index[-1]}")
            print(f"数据列: {', '.join(data.columns.tolist())}")
            
            # 如果需要，添加RSI指标
            if add_rsi:
                self.add_technical_indicators(rsi_period=rsi_period)
                print(f"最终数据列: {', '.join(self.data.columns.tolist())}")
            
            return self.data
            
        except Exception as e:
            print(f"数据获取失败: {e}")
            raise
    
    def _validate_data(self, data: pd.DataFrame) -> None:
        """
        验证数据质量
        
        Args:
            data: 要验证的DataFrame
            
        Raises:
            ValueError: 如果数据质量有问题
        """
        # 检查是否有NaN值
        nan_count = data.isna().sum().sum()
        if nan_count > 0:
            print(f"警告: 数据中包含 {nan_count} 个NaN值")
            
        # 检查是否有零或负值
        price_columns = ['Open', 'High', 'Low', 'Close']
        for col in price_columns:
            if (data[col] <= 0).any():
                print(f"警告: {col} 列包含零或负值")
    
    def add_technical_indicators(self, rsi_period: int = 14) -> pd.DataFrame:
        """
        添加技术指标到数据中
        
        Args:
            rsi_period: RSI计算周期，默认为14
            
        Returns:
            pd.DataFrame: 添加了技术指标的数据
            
        Raises:
            ValueError: 如果数据尚未获取
        """
        if self.data is None:
            raise ValueError("请先获取数据")
        
        print(f"正在添加技术指标...")
        print(f"计算RSI({rsi_period})指标")
        
        # 添加RSI指标
        data_with_indicators = add_rsi_to_data(self.data, period=rsi_period)
        
        # 更新数据
        self.data = data_with_indicators
        
        # 显示RSI统计信息
        rsi_column = f'RSI_{rsi_period}'
        if rsi_column in self.data.columns:
            rsi_data = self.data[rsi_column].dropna()
            print(f"RSI({rsi_period})统计:")
            print(f"  数据点: {len(rsi_data)}")
            print(f"  平均值: {rsi_data.mean():.2f}")
            print(f"  最小值: {rsi_data.min():.2f}")
            print(f"  最大值: {rsi_data.max():.2f}")
            print(f"  <20的比例: {(rsi_data < 20).sum() / len(rsi_data):.2%}")
            print(f"  >60的比例: {(rsi_data > 60).sum() / len(rsi_data):.2%}")
        
        print(f"技术指标添加完成！")
        return self.data
    
    def get_data_summary(self) -> dict:
        """
        获取数据摘要信息
        
        Returns:
            dict: 包含数据摘要的字典
        """
        if self.data is None:
            raise ValueError("请先获取数据")
            
        summary = {
            'symbol': self.symbol,
            'start_date': self.data.index[0],
            'end_date': self.data.index[-1],
            'num_records': len(self.data),
            'columns': self.data.columns.tolist(),
            'price_stats': {
                'open_mean': self.data['Open'].mean(),
                'close_mean': self.data['Close'].mean(),
                'high_max': self.data['High'].max(),
                'low_min': self.data['Low'].min(),
            },
            'volume_stats': {
                'volume_mean': self.data['Volume'].mean(),
                'volume_max': self.data['Volume'].max(),
                'volume_min': self.data['Volume'].min(),
            }
        }
        return summary
    
    def save_to_csv(self, filepath: str = "btc_data.csv") -> None:
        """
        将数据保存到CSV文件
        
        Args:
            filepath: CSV文件路径
        """
        if self.data is None:
            raise ValueError("请先获取数据")
            
        self.data.to_csv(filepath)
        print(f"数据已保存到: {filepath}")


def fetch_btc_data(period: str = "1y", interval: str = "1d", add_rsi: bool = True, rsi_period: int = 14) -> pd.DataFrame:
    """
    获取BTC数据的便捷函数
    
    Args:
        period: 时间周期，默认为1年
        interval: 数据间隔，默认为1天
        add_rsi: 是否添加RSI指标，默认为True
        rsi_period: RSI计算周期，默认为14
        
    Returns:
        pd.DataFrame: BTC的OHLCV数据和可选技术指标
    """
    fetcher = DataFetcher("BTC-USD")
    return fetcher.fetch_last_year_data(period, interval, add_rsi, rsi_period)


if __name__ == "__main__":
    # 测试数据获取功能
    try:
        # 创建数据获取器
        fetcher = DataFetcher("BTC-USD")
        
        # 获取最近一年的数据（包含RSI指标）
        data = fetcher.fetch_last_year_data(add_rsi=True, rsi_period=14)
        
        # 显示数据摘要
        summary = fetcher.get_data_summary()
        print("\n数据摘要:")
        print(f"交易对: {summary['symbol']}")
        print(f"时间范围: {summary['start_date']} 到 {summary['end_date']}")
        print(f"数据条数: {summary['num_records']}")
        print(f"平均收盘价: ${summary['price_stats']['close_mean']:.2f}")
        print(f"最高价: ${summary['price_stats']['high_max']:.2f}")
        print(f"最低价: ${summary['price_stats']['low_min']:.2f}")
        
        # 显示包含RSI的前5行数据
        print("\n前5行数据（包含RSI）:")
        print(data.head())
        
        # 显示包含RSI的后5行数据
        print("\n后5行数据（包含RSI）:")
        print(data.tail())
        
        # 显示RSI统计信息
        if 'RSI_14' in data.columns:
            rsi_data = data['RSI_14'].dropna()
            print("\nRSI(14)详细统计:")
            print(f"有效数据点: {len(rsi_data)}")
            print(f"平均值: {rsi_data.mean():.2f}")
            print(f"中位数: {rsi_data.median():.2f}")
            print(f"标准差: {rsi_data.std():.2f}")
            print(f"最小值: {rsi_data.min():.2f}")
            print(f"最大值: {rsi_data.max():.2f}")
            print(f"<20的交易日数: {(rsi_data < 20).sum()} ({(rsi_data < 20).sum() / len(rsi_data):.2%})")
            print(f">60的交易日数: {(rsi_data > 60).sum()} ({(rsi_data > 60).sum() / len(rsi_data):.2%})")
            
            # 显示RSI极值点
            print("\nRSI最低的5个交易日:")
            low_rsi_days = data.nsmallest(5, 'RSI_14')[['Close', 'RSI_14']]
            print(low_rsi_days)
            
            print("\nRSI最高的5个交易日:")
            high_rsi_days = data.nlargest(5, 'RSI_14')[['Close', 'RSI_14']]
            print(high_rsi_days)
        
        # 保存数据到CSV
        fetcher.save_to_csv()
        
    except Exception as e:
        print(f"测试失败: {e}")