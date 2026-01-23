"""
数据获取模块
负责从不同数据源获取价格数据
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import os

from config.settings import settings


class DataFetcher:
    """数据获取器"""
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        初始化数据获取器
        
        Args:
            config: 数据配置，如果为None则使用默认配置
        """
        self.config = config or settings.DATA_CONFIG
        self.logger = logging.getLogger(__name__)
        
    def fetch_data(self) -> pd.DataFrame:
        """
        获取数据
        
        Returns:
            pd.DataFrame: 包含价格数据的DataFrame
            
        Raises:
            ValueError: 数据源不支持
            Exception: 数据获取失败
        """
        data_source = self.config.get('data_source', 'yfinance')
        
        if data_source == 'yfinance':
            return self._fetch_from_yfinance()
        elif data_source == 'ccxt':
            return self._fetch_from_ccxt()
        elif data_source == 'csv':
            return self._load_from_csv()
        else:
            raise ValueError(f"不支持的数据源: {data_source}")
    
    def _fetch_from_yfinance(self) -> pd.DataFrame:
        """
        从yfinance获取数据
        
        Returns:
            pd.DataFrame: 价格数据
        """
        try:
            import yfinance as yf
            
            symbol = self.config['symbol']
            start_date = self.config['start_date']
            end_date = self.config['end_date']
            interval = self.config['interval']
            
            self.logger.info(f"从yfinance获取数据: {symbol}, {start_date} 到 {end_date}, 间隔: {interval}")
            
            # 下载数据
            ticker = yf.Ticker(symbol)
            data = ticker.history(
                start=start_date,
                end=end_date,
                interval=interval
            )
            
            if data.empty:
                raise ValueError(f"未获取到数据，请检查参数: {symbol}")
            
            # 重命名列以符合标准格式
            data = data.rename(columns={
                'Open': 'open',
                'High': 'high', 
                'Low': 'low',
                'Close': 'close',
                'Volume': 'volume'
            })
            
            # 确保所有必需的列都存在
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            for col in required_columns:
                if col not in data.columns:
                    raise ValueError(f"数据缺少必需列: {col}")
            
            # 添加时间戳列
            data['timestamp'] = data.index
            data['date'] = data.index.date
            
            self.logger.info(f"成功获取 {len(data)} 条数据")
            
            # 保存到本地文件
            self._save_to_csv(data)
            
            return data
            
        except ImportError:
            self.logger.error("请安装yfinance: pip install yfinance")
            raise
        except Exception as e:
            self.logger.error(f"从yfinance获取数据失败: {e}")
            raise
    
    def _fetch_from_ccxt(self) -> pd.DataFrame:
        """
        从CCXT获取数据（加密货币交易所）
        
        Returns:
            pd.DataFrame: 价格数据
        """
        try:
            import ccxt
            
            symbol = self.config['symbol']
            start_date = self.config['start_date']
            end_date = self.config['end_date']
            interval = self.config['interval']
            
            self.logger.info(f"从CCXT获取数据: {symbol}, {start_date} 到 {end_date}")
            
            # 创建交易所实例（默认使用币安）
            exchange = ccxt.binance()
            
            # 转换时间间隔为CCXT格式
            timeframe_map = {
                '1d': '1d',
                '1h': '1h',
                '30m': '30m',
                '15m': '15m',
                '5m': '5m',
                '1m': '1m'
            }
            
            timeframe = timeframe_map.get(interval, '1d')
            
            # 获取数据
            since = exchange.parse8601(f"{start_date}T00:00:00Z")
            data = []
            
            while True:
                ohlcv = exchange.fetch_ohlcv(symbol, timeframe, since)
                if not ohlcv:
                    break
                
                data.extend(ohlcv)
                since = ohlcv[-1][0] + 1  # 下一批数据的开始时间
                
                # 检查是否达到结束日期
                last_timestamp = ohlcv[-1][0]
                last_date = datetime.fromtimestamp(last_timestamp / 1000).date()
                end_date_obj = datetime.strptime(end_date, '%Y-%m-%d').date()
                
                if last_date >= end_date_obj:
                    break
            
            # 转换为DataFrame
            df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df.set_index('timestamp', inplace=True)
            df['date'] = df.index.date
            
            self.logger.info(f"成功获取 {len(df)} 条数据")
            
            # 保存到本地文件
            self._save_to_csv(df)
            
            return df
            
        except ImportError:
            self.logger.error("请安装ccxt: pip install ccxt")
            raise
        except Exception as e:
            self.logger.error(f"从CCXT获取数据失败: {e}")
            raise
    
    def _load_from_csv(self) -> pd.DataFrame:
        """
        从CSV文件加载数据
        
        Returns:
            pd.DataFrame: 价格数据
        """
        try:
            symbol = self.config['symbol']
            csv_file = os.path.join(settings.DATA_DIR, f"{symbol.replace('/', '_')}.csv")
            
            if not os.path.exists(csv_file):
                raise FileNotFoundError(f"数据文件不存在: {csv_file}")
            
            self.logger.info(f"从CSV文件加载数据: {csv_file}")
            
            df = pd.read_csv(csv_file, index_col='timestamp', parse_dates=True)
            
            # 确保索引是datetime类型
            if not isinstance(df.index, pd.DatetimeIndex):
                df.index = pd.to_datetime(df.index)
            
            # 添加日期列
            df['date'] = df.index.date
            
            self.logger.info(f"成功加载 {len(df)} 条数据")
            
            return df
            
        except Exception as e:
            self.logger.error(f"从CSV加载数据失败: {e}")
            raise
    
    def _save_to_csv(self, data: pd.DataFrame) -> None:
        """
        保存数据到CSV文件
        
        Args:
            data: 要保存的数据
        """
        try:
            # 确保数据目录存在
            os.makedirs(settings.DATA_DIR, exist_ok=True)
            
            symbol = self.config['symbol']
            csv_file = os.path.join(settings.DATA_DIR, f"{symbol.replace('/', '_')}.csv")
            
            # 保存数据
            data.to_csv(csv_file)
            self.logger.info(f"数据已保存到: {csv_file}")
            
        except Exception as e:
            self.logger.warning(f"保存数据到CSV失败: {e}")
    
    def get_data_info(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        获取数据基本信息
        
        Args:
            data: 价格数据
            
        Returns:
            Dict[str, Any]: 数据信息
        """
        if data.empty:
            return {}
        
        return {
            'start_date': data.index[0].strftime('%Y-%m-%d'),
            'end_date': data.index[-1].strftime('%Y-%m-%d'),
            'total_rows': len(data),
            'columns': list(data.columns),
            'price_range': {
                'min': float(data['close'].min()),
                'max': float(data['close'].max()),
                'mean': float(data['close'].mean())
            },
            'volume_info': {
                'total': float(data['volume'].sum()),
                'avg': float(data['volume'].mean())
            }
        }


def test_data_fetcher():
    """测试数据获取器"""
    import logging
    logging.basicConfig(level=logging.INFO)
    
    try:
        fetcher = DataFetcher()
        data = fetcher.fetch_data()
        
        print(f"数据形状: {data.shape}")
        print(f"数据列: {data.columns.tolist()}")
        print(f"数据范围: {data.index[0]} 到 {data.index[-1]}")
        print(f"前5行数据:")
        print(data.head())
        
        info = fetcher.get_data_info(data)
        print(f"\n数据信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")
            
        return True
        
    except Exception as e:
        print(f"测试失败: {e}")
        return False


if __name__ == "__main__":
    test_data_fetcher()