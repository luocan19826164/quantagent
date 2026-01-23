"""
数据获取模块
从yfinance获取BTC/USD历史数据
"""

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import os
import pickle
from typing import Optional, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DataFetcher:
    """数据获取器，用于获取和缓存BTC历史数据"""
    
    def __init__(self, cache_dir: str = "data_cache"):
        """
        初始化数据获取器
        
        Args:
            cache_dir: 缓存目录路径
        """
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        
    def get_btc_data(
        self, 
        period: str = "1y",
        interval: str = "1d",
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        获取BTC/USD历史数据
        
        Args:
            period: 时间周期，如 "1d", "5d", "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "ytd", "max"
            interval: 数据间隔，如 "1m", "2m", "5m", "15m", "30m", "60m", "90m", "1h", "1d", "5d", "1wk", "1mo", "3mo"
            use_cache: 是否使用缓存
            force_refresh: 是否强制刷新数据（忽略缓存）
            
        Returns:
            pd.DataFrame: BTC历史数据，包含以下列：
                - Open: 开盘价
                - High: 最高价
                - Low: 最低价
                - Close: 收盘价
                - Volume: 成交量
                - Dividends: 分红（对于加密货币通常为0）
                - Stock Splits: 股票分割（对于加密货币通常为0）
        """
        # 生成缓存文件名
        cache_file = os.path.join(self.cache_dir, f"btc_{period}_{interval}.pkl")
        
        # 检查缓存
        if use_cache and not force_refresh and os.path.exists(cache_file):
            try:
                logger.info(f"从缓存加载数据: {cache_file}")
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                logger.info(f"数据加载成功，共 {len(data)} 条记录")
                return data
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}，重新下载数据")
        
        # 从yfinance下载数据
        logger.info(f"从yfinance下载BTC数据，周期: {period}, 间隔: {interval}")
        
        try:
            # BTC-USD在yfinance中的代码
            ticker = "BTC-USD"
            
            # 下载数据
            btc = yf.Ticker(ticker)
            data = btc.history(period=period, interval=interval)
            
            if data.empty:
                raise ValueError(f"未获取到数据，请检查参数: period={period}, interval={interval}")
            
            # 数据清理
            data = self._clean_data(data)
            
            logger.info(f"数据下载成功，共 {len(data)} 条记录")
            logger.info(f"数据时间范围: {data.index[0]} 到 {data.index[-1]}")
            
            # 保存到缓存
            if use_cache:
                with open(cache_file, 'wb') as f:
                    pickle.dump(data, f)
                logger.info(f"数据已缓存到: {cache_file}")
            
            return data
            
        except Exception as e:
            logger.error(f"数据下载失败: {e}")
            raise
    
    def get_btc_data_by_date(
        self,
        start_date: str,
        end_date: Optional[str] = None,
        interval: str = "1d",
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> pd.DataFrame:
        """
        通过日期范围获取BTC/USD历史数据
        
        Args:
            start_date: 开始日期，格式 "YYYY-MM-DD"
            end_date: 结束日期，格式 "YYYY-MM-DD"，默认为今天
            interval: 数据间隔
            use_cache: 是否使用缓存
            force_refresh: 是否强制刷新数据
            
        Returns:
            pd.DataFrame: BTC历史数据
        """
        if end_date is None:
            end_date = datetime.now().strftime("%Y-%m-%d")
        
        # 生成缓存文件名
        cache_file = os.path.join(
            self.cache_dir, 
            f"btc_{start_date}_{end_date}_{interval}.pkl"
        )
        
        # 检查缓存
        if use_cache and not force_refresh and os.path.exists(cache_file):
            try:
                logger.info(f"从缓存加载数据: {cache_file}")
                with open(cache_file, 'rb') as f:
                    data = pickle.load(f)
                logger.info(f"数据加载成功，共 {len(data)} 条记录")
                return data
            except Exception as e:
                logger.warning(f"缓存加载失败: {e}，重新下载数据")
        
        # 从yfinance下载数据
        logger.info(f"从yfinance下载BTC数据，日期范围: {start_date} 到 {end_date}")
        
        try:
            # BTC-USD在yfinance中的代码
            ticker = "BTC-USD"
            
            # 下载数据
            btc = yf.Ticker(ticker)
            data = btc.history(start=start_date, end=end_date, interval=interval)
            
            if data.empty:
                raise ValueError(f"未获取到数据，请检查日期范围: {start_date} 到 {end_date}")
            
            # 数据清理
            data = self._clean_data(data)
            
            logger.info(f"数据下载成功，共 {len(data)} 条记录")
            logger.info(f"数据时间范围: {data.index[0]} 到 {data.index[-1]}")
            
            # 保存到缓存
            if use_cache:
                with open(cache_file, 'wb') as f:
                    pickle.dump(data, f)
                logger.info(f"数据已缓存到: {cache_file}")
            
            return data
            
        except Exception as e:
            logger.error(f"数据下载失败: {e}")
            raise
    
    def _clean_data(self, data: pd.DataFrame) -> pd.DataFrame:
        """
        清理数据
        
        Args:
            data: 原始数据
            
        Returns:
            清理后的数据
        """
        # 确保索引是datetime类型
        if not isinstance(data.index, pd.DatetimeIndex):
            data.index = pd.to_datetime(data.index)
        
        # 删除包含NaN的行
        data = data.dropna()
        
        # 确保列名正确
        expected_columns = ['Open', 'High', 'Low', 'Close', 'Volume', 'Dividends', 'Stock Splits']
        for col in expected_columns:
            if col not in data.columns:
                logger.warning(f"列 {col} 不存在于数据中")
        
        # 按日期排序
        data = data.sort_index()
        
        return data
    
    def get_data_info(self, data: pd.DataFrame) -> dict:
        """
        获取数据基本信息
        
        Args:
            data: BTC历史数据
            
        Returns:
            dict: 包含数据基本信息的字典
        """
        info = {
            "start_date": data.index[0].strftime("%Y-%m-%d"),
            "end_date": data.index[-1].strftime("%Y-%m-%d"),
            "total_days": len(data),
            "price_range": {
                "min": data['Close'].min(),
                "max": data['Close'].max(),
                "current": data['Close'].iloc[-1]
            },
            "volume_info": {
                "avg_volume": data['Volume'].mean(),
                "max_volume": data['Volume'].max()
            },
            "missing_dates": self._find_missing_dates(data)
        }
        return info
    
    def _find_missing_dates(self, data: pd.DataFrame) -> list:
        """
        查找缺失的日期
        
        Args:
            data: 时间序列数据
            
        Returns:
            list: 缺失的日期列表
        """
        if len(data) < 2:
            return []
        
        # 生成完整的日期范围
        full_range = pd.date_range(start=data.index[0], end=data.index[-1], freq='D')
        
        # 找出缺失的日期
        missing_dates = full_range.difference(data.index)
        
        return missing_dates.tolist()


def test_data_fetcher():
    """测试数据获取器"""
    print("测试数据获取模块...")
    
    # 创建数据获取器
    fetcher = DataFetcher()
    
    try:
        # 测试方法1：使用周期参数
        print("\n1. 测试获取最近一年的日线数据...")
        data1 = fetcher.get_btc_data(period="1y", interval="1d")
        info1 = fetcher.get_data_info(data1)
        print(f"  数据时间范围: {info1['start_date']} 到 {info1['end_date']}")
        print(f"  数据条数: {info1['total_days']}")
        print(f"  价格范围: ${info1['price_range']['min']:.2f} - ${info1['price_range']['max']:.2f}")
        print(f"  当前价格: ${info1['price_range']['current']:.2f}")
        
        # 显示前几行数据
        print(f"\n  前5行数据:")
        print(data1.head())
        
        # 测试方法2：使用日期范围
        print("\n2. 测试获取指定日期范围的数据...")
        # 获取最近3个月的数据
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=90)).strftime("%Y-%m-%d")
        
        data2 = fetcher.get_btc_data_by_date(
            start_date=start_date,
            end_date=end_date,
            interval="1d"
        )
        info2 = fetcher.get_data_info(data2)
        print(f"  数据时间范围: {info2['start_date']} 到 {info2['end_date']}")
        print(f"  数据条数: {info2['total_days']}")
        
        print("\n数据获取测试完成！")
        
    except Exception as e:
        print(f"测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    test_data_fetcher()