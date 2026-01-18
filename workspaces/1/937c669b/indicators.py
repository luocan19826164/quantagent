"""
技术指标计算模块
包含RSI、移动平均线等常用技术指标的计算函数
"""

import pandas as pd
import numpy as np
from typing import Optional, Union


def calculate_rsi(prices: Union[pd.Series, np.ndarray], 
                  period: int = 14) -> pd.Series:
    """
    计算相对强弱指数（RSI）
    
    RSI计算公式：
    1. 计算价格变化：change = price_t - price_{t-1}
    2. 计算上涨和下跌：gain = max(change, 0), loss = max(-change, 0)
    3. 计算平均上涨和平均下跌（使用指数移动平均）
    4. RS = 平均上涨 / 平均下跌
    5. RSI = 100 - (100 / (1 + RS))
    
    Args:
        prices: 价格序列，可以是pandas Series或numpy数组
        period: RSI计算周期，默认为14
        
    Returns:
        RSI值序列，与输入长度相同，前period-1个值为NaN
        
    Raises:
        ValueError: 如果period小于等于0或价格数据长度不足
    """
    if period <= 0:
        raise ValueError(f"周期必须大于0，当前为{period}")
    
    # 转换为pandas Series以便处理
    if isinstance(prices, np.ndarray):
        prices = pd.Series(prices)
    
    if len(prices) < period + 1:
        raise ValueError(f"价格数据长度({len(prices)})不足，至少需要{period + 1}个数据点")
    
    # 计算价格变化
    delta = prices.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 计算指数移动平均
    avg_gain = gain.ewm(alpha=1/period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, adjust=False).mean()
    
    # 计算RS和RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_simple_rsi(prices: Union[pd.Series, np.ndarray], 
                         period: int = 14) -> pd.Series:
    """
    计算RSI的简化版本（使用简单移动平均）
    
    这个版本使用简单移动平均而不是指数移动平均，
    在某些情况下可能更符合传统RSI计算
    
    Args:
        prices: 价格序列
        period: RSI计算周期
        
    Returns:
        RSI值序列
    """
    if period <= 0:
        raise ValueError(f"周期必须大于0，当前为{period}")
    
    if isinstance(prices, np.ndarray):
        prices = pd.Series(prices)
    
    if len(prices) < period + 1:
        raise ValueError(f"价格数据长度({len(prices)})不足，至少需要{period + 1}个数据点")
    
    # 计算价格变化
    delta = prices.diff()
    
    # 分离上涨和下跌
    gain = delta.where(delta > 0, 0)
    loss = -delta.where(delta < 0, 0)
    
    # 计算简单移动平均
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    
    # 计算RS和RSI
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def test_rsi_calculation():
    """
    测试RSI计算函数
    使用已知数据验证RSI计算的正确性
    """
    # 创建测试数据
    test_prices = pd.Series([44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 
                             45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 
                             45.61, 46.28, 46.28, 46.00, 46.03, 46.41, 
                             46.22, 45.64, 46.21, 46.25, 45.71, 46.45])
    
    print("测试数据:")
    print(test_prices)
    print()
    
    # 计算RSI
    rsi_values = calculate_rsi(test_prices, period=14)
    print(f"RSI(14)值（使用指数移动平均）:")
    print(rsi_values.tail(10))
    print()
    
    # 计算简化版RSI
    simple_rsi = calculate_simple_rsi(test_prices, period=14)
    print(f"RSI(14)值（使用简单移动平均）:")
    print(simple_rsi.tail(10))
    print()
    
    # 验证数据长度
    print(f"输入数据长度: {len(test_prices)}")
    print(f"RSI输出长度: {len(rsi_values)}")
    print(f"前{13}个值应为NaN: {rsi_values[:13].isna().all()}")
    
    return rsi_values, simple_rsi


if __name__ == "__main__":
    print("=" * 50)
    print("RSI指标计算模块测试")
    print("=" * 50)
    print()
    
    rsi, simple_rsi = test_rsi_calculation()
    
    print()
    print("测试完成！")