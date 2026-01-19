"""
技术指标计算模块
包含RSI、移动平均线等常用技术指标
"""

import pandas as pd
import numpy as np
from typing import Optional, Tuple
import logging

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TechnicalIndicators:
    """技术指标计算器"""
    
    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        计算相对强弱指数 (RSI)
        
        RSI计算公式:
        1. 计算价格变化: delta = price_t - price_{t-1}
        2. 分离上涨和下跌: 
           gain = delta if delta > 0 else 0
           loss = -delta if delta < 0 else 0
        3. 计算平均上涨和平均下跌 (使用简单移动平均):
           avg_gain = SMA(gain, period)
           avg_loss = SMA(loss, period)
        4. 计算相对强度: RS = avg_gain / avg_loss
        5. 计算RSI: RSI = 100 - (100 / (1 + RS))
        
        Args:
            prices: 价格序列 (通常是收盘价)
            period: RSI计算周期，默认为14
            
        Returns:
            RSI值序列，长度与输入相同，前period-1个值为NaN
        """
        if len(prices) < period:
            raise ValueError(f"数据长度({len(prices)})小于RSI周期({period})")
        
        # 计算价格变化
        delta = prices.diff()
        
        # 分离上涨和下跌
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)
        
        # 计算平均上涨和平均下跌
        # 使用简单移动平均 (SMA)
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()
        
        # 计算相对强度 (RS)
        # 避免除以零的情况
        rs = avg_gain / avg_loss.replace(0, np.nan)
        
        # 计算RSI
        rsi = 100 - (100 / (1 + rs))
        
        # 处理特殊情况：当avg_loss为0时，RSI为100
        rsi = rsi.where(avg_loss != 0, 100)
        
        logger.info(f"计算RSI({period})完成，有效数据点: {rsi.notna().sum()}")
        
        return rsi
    
    @staticmethod
    def calculate_sma(prices: pd.Series, period: int) -> pd.Series:
        """
        计算简单移动平均线 (SMA)
        
        Args:
            prices: 价格序列
            period: 移动平均周期
            
        Returns:
            移动平均值序列
        """
        return prices.rolling(window=period).mean()
    
    @staticmethod
    def calculate_ema(prices: pd.Series, period: int) -> pd.Series:
        """
        计算指数移动平均线 (EMA)
        
        Args:
            prices: 价格序列
            period: 移动平均周期
            
        Returns:
            指数移动平均值序列
        """
        return prices.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def calculate_bollinger_bands(prices: pd.Series, period: int = 20, 
                                 num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        计算布林带
        
        Args:
            prices: 价格序列
            period: 移动平均周期，默认为20
            num_std: 标准差倍数，默认为2.0
            
        Returns:
            (中轨, 上轨, 下轨) 三个序列
        """
        sma = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()
        
        upper_band = sma + (std * num_std)
        lower_band = sma - (std * num_std)
        
        return sma, upper_band, lower_band
    
    @staticmethod
    def add_rsi_to_dataframe(data: pd.DataFrame, price_column: str = 'Close', 
                            period: int = 14, rsi_column: str = 'RSI') -> pd.DataFrame:
        """
        将RSI指标添加到DataFrame中
        
        Args:
            data: 包含价格数据的DataFrame
            price_column: 价格列名，默认为'Close'
            period: RSI周期，默认为14
            rsi_column: RSI列名，默认为'RSI'
            
        Returns:
            添加了RSI列的DataFrame
        """
        if price_column not in data.columns:
            raise ValueError(f"DataFrame中不存在列: {price_column}")
        
        # 计算RSI
        rsi_values = TechnicalIndicators.calculate_rsi(data[price_column], period)
        
        # 添加到DataFrame
        data = data.copy()
        data[rsi_column] = rsi_values
        
        # 添加RSI信号列
        data[f'{rsi_column}_signal'] = pd.cut(
            rsi_values,
            bins=[0, 20, 30, 70, 80, 100],
            labels=['超卖', '弱势', '中性', '强势', '超买']
        )
        
        logger.info(f"已将RSI({period})添加到DataFrame，列名: {rsi_column}")
        
        return data
    
    @staticmethod
    def get_rsi_statistics(rsi_series: pd.Series) -> dict:
        """
        获取RSI统计信息
        
        Args:
            rsi_series: RSI值序列
            
        Returns:
            包含RSI统计信息的字典
        """
        # 移除NaN值
        rsi_valid = rsi_series.dropna()
        
        if len(rsi_valid) == 0:
            return {}
        
        stats = {
            'mean': float(rsi_valid.mean()),
            'std': float(rsi_valid.std()),
            'min': float(rsi_valid.min()),
            'max': float(rsi_valid.max()),
            'median': float(rsi_valid.median()),
            'oversold_count': int((rsi_valid < 20).sum()),
            'overbought_count': int((rsi_valid > 80).sum()),
            'oversold_percentage': float((rsi_valid < 20).sum() / len(rsi_valid) * 100),
            'overbought_percentage': float((rsi_valid > 80).sum() / len(rsi_valid) * 100),
            'neutral_percentage': float(((rsi_valid >= 30) & (rsi_valid <= 70)).sum() / len(rsi_valid) * 100)
        }
        
        return stats


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算RSI的便捷函数
    
    Args:
        prices: 价格序列
        period: RSI周期，默认为14
        
    Returns:
        RSI值序列
    """
    return TechnicalIndicators.calculate_rsi(prices, period)


def add_rsi_to_dataframe(data: pd.DataFrame, price_column: str = 'Close', 
                        period: int = 14, rsi_column: str = 'RSI') -> pd.DataFrame:
    """
    将RSI指标添加到DataFrame的便捷函数
    
    Args:
        data: 包含价格数据的DataFrame
        price_column: 价格列名，默认为'Close'
        period: RSI周期，默认为14
        rsi_column: RSI列名，默认为'RSI'
        
    Returns:
        添加了RSI列的DataFrame
    """
    return TechnicalIndicators.add_rsi_to_dataframe(data, price_column, period, rsi_column)


if __name__ == "__main__":
    """测试RSI计算"""
    print("测试RSI指标计算")
    print("=" * 50)
    
    # 创建测试数据
    np.random.seed(42)
    n = 100
    test_prices = pd.Series(
        np.cumsum(np.random.randn(n)) + 100,
        index=pd.date_range('2023-01-01', periods=n, freq='D')
    )
    
    print(f"测试数据长度: {len(test_prices)}")
    print(f"价格范围: {test_prices.min():.2f} - {test_prices.max():.2f}")
    
    # 计算RSI
    try:
        rsi = calculate_rsi(test_prices, period=14)
        print(f"\nRSI计算成功!")
        print(f"RSI长度: {len(rsi)}")
        print(f"有效RSI值数量: {rsi.notna().sum()}")
        print(f"前5个RSI值: {rsi.head().tolist()}")
        print(f"后5个RSI值: {rsi.tail().tolist()}")
        
        # 获取统计信息
        stats = TechnicalIndicators.get_rsi_statistics(rsi)
        if stats:
            print(f"\nRSI统计信息:")
            print(f"  均值: {stats['mean']:.2f}")
            print(f"  标准差: {stats['std']:.2f}")
            print(f"  最小值: {stats['min']:.2f}")
            print(f"  最大值: {stats['max']:.2f}")
            print(f"  超卖次数: {stats['oversold_count']} ({stats['oversold_percentage']:.1f}%)")
            print(f"  超买次数: {stats['overbought_count']} ({stats['overbought_percentage']:.1f}%)")
            print(f"  中性区域: {stats['neutral_percentage']:.1f}%")
        
    except Exception as e:
        print(f"RSI计算失败: {e}")