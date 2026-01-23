"""
技术指标计算模块
实现RSI等常用技术指标
"""

import pandas as pd
import numpy as np
from typing import Optional


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算相对强弱指数（RSI）
    
    Args:
        prices: 价格序列（通常是收盘价）
        period: RSI计算周期，默认14
        
    Returns:
        RSI值序列，与输入序列长度相同，前period-1个值为NaN
    """
    if len(prices) < period:
        raise ValueError(f"价格序列长度({len(prices)})小于RSI周期({period})")
    
    # 计算价格变化
    delta = prices.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 计算平均上涨和平均下跌（使用简单移动平均）
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # 计算RS
    rs = avg_gain / avg_loss
    
    # 计算RSI
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_sma(prices: pd.Series, period: int = 20) -> pd.Series:
    """
    计算简单移动平均线（SMA）
    
    Args:
        prices: 价格序列
        period: 移动平均周期
        
    Returns:
        SMA序列
    """
    return prices.rolling(window=period).mean()


def calculate_ema(prices: pd.Series, period: int = 20) -> pd.Series:
    """
    计算指数移动平均线（EMA）
    
    Args:
        prices: 价格序列
        period: 移动平均周期
        
    Returns:
        EMA序列
    """
    return prices.ewm(span=period, adjust=False).mean()


def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> pd.DataFrame:
    """
    计算布林带
    
    Args:
        prices: 价格序列
        period: 移动平均周期
        std_dev: 标准差倍数
        
    Returns:
        DataFrame包含以下列：
        - middle: 中轨（SMA）
        - upper: 上轨（SMA + std_dev * 标准差）
        - lower: 下轨（SMA - std_dev * 标准差）
    """
    sma = calculate_sma(prices, period)
    rolling_std = prices.rolling(window=period).std()
    
    upper_band = sma + (rolling_std * std_dev)
    lower_band = sma - (rolling_std * std_dev)
    
    return pd.DataFrame({
        'middle': sma,
        'upper': upper_band,
        'lower': lower_band
    })


def calculate_macd(prices: pd.Series, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """
    计算MACD指标
    
    Args:
        prices: 价格序列
        fast_period: 快线EMA周期
        slow_period: 慢线EMA周期
        signal_period: 信号线EMA周期
        
    Returns:
        DataFrame包含以下列：
        - macd: MACD线（快线EMA - 慢线EMA）
        - signal: 信号线（MACD线的EMA）
        - histogram: 柱状图（MACD - 信号线）
    """
    ema_fast = calculate_ema(prices, fast_period)
    ema_slow = calculate_ema(prices, slow_period)
    
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal_period)
    histogram = macd_line - signal_line
    
    return pd.DataFrame({
        'macd': macd_line,
        'signal': signal_line,
        'histogram': histogram
    })


def add_technical_indicators(data: pd.DataFrame, rsi_period: int = 14) -> pd.DataFrame:
    """
    为价格数据添加常用技术指标
    
    Args:
        data: 价格数据DataFrame，必须包含'Close'列
        rsi_period: RSI计算周期
        
    Returns:
        添加了技术指标的新DataFrame
    """
    if 'Close' not in data.columns:
        raise ValueError("数据必须包含'Close'列")
    
    # 创建数据副本
    result = data.copy()
    
    # 计算RSI
    result['RSI'] = calculate_rsi(result['Close'], period=rsi_period)
    
    # 计算移动平均线
    result['SMA_20'] = calculate_sma(result['Close'], period=20)
    result['SMA_50'] = calculate_sma(result['Close'], period=50)
    result['EMA_20'] = calculate_ema(result['Close'], period=20)
    
    # 计算布林带
    bollinger = calculate_bollinger_bands(result['Close'], period=20, std_dev=2.0)
    result['BB_middle'] = bollinger['middle']
    result['BB_upper'] = bollinger['upper']
    result['BB_lower'] = bollinger['lower']
    
    # 计算MACD
    macd = calculate_macd(result['Close'])
    result['MACD'] = macd['macd']
    result['MACD_signal'] = macd['signal']
    result['MACD_histogram'] = macd['histogram']
    
    return result


if __name__ == "__main__":
    # 测试指标计算
    print("测试技术指标计算...")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = pd.Series(np.random.randn(100).cumsum() + 100, index=dates)
    
    # 测试RSI
    rsi = calculate_rsi(prices, period=14)
    print(f"RSI前5个值: {rsi.head(10).tolist()}")
    print(f"RSI后5个值: {rsi.tail().tolist()}")
    
    # 测试添加技术指标
    test_data = pd.DataFrame({'Close': prices})
    enhanced_data = add_technical_indicators(test_data)
    print(f"\n增强数据列: {enhanced_data.columns.tolist()}")
    print(f"数据形状: {enhanced_data.shape}")
    print(f"\n数据预览:")
    print(enhanced_data.tail())