"""
技术指标计算模块
包含各种技术指标的计算函数
"""

import pandas as pd
import numpy as np
from typing import Optional, Union


def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算相对强弱指数（RSI）
    
    RSI计算公式：
    1. 计算价格变化：delta = price.diff()
    2. 分离上涨和下跌：gain = delta.where(delta > 0, 0), loss = -delta.where(delta < 0, 0)
    3. 计算平均上涨和平均下跌（使用指数移动平均）
    4. RS = avg_gain / avg_loss
    5. RSI = 100 - (100 / (1 + RS))
    
    Args:
        prices: 价格序列（通常是收盘价）
        period: RSI计算周期，默认为14
        
    Returns:
        pd.Series: RSI值序列，前period-1个值为NaN
        
    Raises:
        ValueError: 如果输入数据长度不足或包含无效值
    """
    if len(prices) < period:
        raise ValueError(f"数据长度({len(prices)})不足，至少需要{period}个数据点来计算RSI({period})")
    
    if prices.isna().any():
        raise ValueError("价格序列包含NaN值，请先处理缺失数据")
    
    # 计算价格变化
    delta = prices.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 使用指数移动平均计算平均上涨和平均下跌
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    # 计算RS和RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # 处理除零情况（当avg_loss为0时，RS为无穷大，RSI应为100）
    rsi = rsi.where(avg_loss > 0, 100)
    
    return rsi


def add_rsi_to_data(data: pd.DataFrame, period: int = 14, price_column: str = 'Close') -> pd.DataFrame:
    """
    将RSI指标添加到数据DataFrame中
    
    Args:
        data: 包含价格数据的DataFrame
        period: RSI计算周期，默认为14
        price_column: 用于计算RSI的价格列名，默认为'Close'
        
    Returns:
        pd.DataFrame: 添加了RSI列的新DataFrame
        
    Raises:
        ValueError: 如果数据中缺少指定的价格列
    """
    if price_column not in data.columns:
        raise ValueError(f"数据中缺少价格列: {price_column}")
    
    # 创建数据副本以避免修改原始数据
    data_with_rsi = data.copy()
    
    # 计算RSI
    rsi_values = calculate_rsi(data_with_rsi[price_column], period)
    
    # 添加RSI列
    data_with_rsi[f'RSI_{period}'] = rsi_values
    
    return data_with_rsi


def calculate_simple_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    计算RSI的简化版本（使用简单移动平均）
    
    这个版本使用简单移动平均而不是指数移动平均，更接近传统RSI计算方法
    
    Args:
        prices: 价格序列
        period: RSI计算周期
        
    Returns:
        pd.Series: RSI值序列
    """
    if len(prices) < period:
        raise ValueError(f"数据长度({len(prices)})不足，至少需要{period}个数据点来计算RSI({period})")
    
    # 计算价格变化
    delta = prices.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 使用简单移动平均计算平均上涨和平均下跌
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # 计算RS和RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    # 处理除零情况
    rsi = rsi.where(avg_loss > 0, 100)
    
    return rsi


def test_rsi_calculation():
    """测试RSI计算函数"""
    print("测试RSI计算函数...")
    
    # 创建测试数据
    test_prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 
                             110, 108, 107, 106, 105, 104, 103, 102, 101, 100])
    
    # 计算RSI
    rsi_ema = calculate_rsi(test_prices, period=14)
    rsi_sma = calculate_simple_rsi(test_prices, period=14)
    
    print(f"测试价格序列长度: {len(test_prices)}")
    print(f"RSI(14) EMA版本 - 最后5个值:")
    print(rsi_ema.tail())
    print(f"\nRSI(14) SMA版本 - 最后5个值:")
    print(rsi_sma.tail())
    
    # 检查结果
    print(f"\nRSI值范围检查:")
    print(f"EMA RSI范围: [{rsi_ema.min():.2f}, {rsi_ema.max():.2f}]")
    print(f"SMA RSI范围: [{rsi_sma.min():.2f}, {rsi_sma.max():.2f}]")
    
    # 验证RSI值在0-100之间
    assert (rsi_ema.dropna() >= 0).all() and (rsi_ema.dropna() <= 100).all(), "RSI值超出0-100范围"
    assert (rsi_sma.dropna() >= 0).all() and (rsi_sma.dropna() <= 100).all(), "RSI值超出0-100范围"
    
    print("\nRSI计算测试通过！")


if __name__ == "__main__":
    # 运行测试
    test_rsi_calculation()