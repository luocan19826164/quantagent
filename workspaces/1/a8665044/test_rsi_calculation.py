#!/usr/bin/env python3
"""
测试RSI计算功能
"""

import pandas as pd
import numpy as np
from indicators import calculate_rsi, TechnicalIndicators


def test_rsi_basic():
    """测试基本的RSI计算"""
    print("测试基本RSI计算")
    print("=" * 50)
    
    # 创建简单的测试数据
    # 价格序列：前10天上涨，后10天下跌
    n = 30
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 创建有趋势的价格序列
    np.random.seed(42)
    trend = np.linspace(0, 0.5, n)  # 上升趋势
    noise = np.random.normal(0, 0.02, n)
    prices = 100 * (1 + trend + noise)
    
    price_series = pd.Series(prices, index=dates)
    
    print(f"测试数据长度: {len(price_series)}")
    print(f"价格范围: {price_series.min():.2f} - {price_series.max():.2f}")
    
    # 计算RSI
    rsi = calculate_rsi(price_series, period=14)
    
    print(f"\nRSI计算结果:")
    print(f"RSI长度: {len(rsi)}")
    print(f"有效RSI值数量: {rsi.notna().sum()}")
    
    # 显示部分结果
    print(f"\n前10个价格和RSI值:")
    for i in range(min(10, len(price_series))):
        date = price_series.index[i].strftime('%Y-%m-%d')
        price = price_series.iloc[i]
        rsi_value = rsi.iloc[i]
        print(f"  {date}: 价格={price:.2f}, RSI={rsi_value if pd.notna(rsi_value) else 'NaN':.2f}")
    
    # 验证RSI值在0-100范围内
    rsi_valid = rsi.dropna()
    if len(rsi_valid) > 0:
        print(f"\nRSI值验证:")
        print(f"  RSI最小值: {rsi_valid.min():.2f} (应在0-100范围内)")
        print(f"  RSI最大值: {rsi_valid.max():.2f} (应在0-100范围内)")
        
        if rsi_valid.min() >= 0 and rsi_valid.max() <= 100:
            print("  ✓ RSI值在有效范围内 (0-100)")
        else:
            print("  ✗ RSI值超出有效范围")
    
    return rsi


def test_rsi_edge_cases():
    """测试边界情况"""
    print("\n\n测试RSI边界情况")
    print("=" * 50)
    
    # 测试1: 数据长度小于周期
    print("\n测试1: 数据长度小于RSI周期")
    short_prices = pd.Series([100, 101, 102, 103, 104])
    try:
        rsi_short = calculate_rsi(short_prices, period=14)
        print(f"  结果: 成功计算，但应失败")
    except ValueError as e:
        print(f"  结果: 正确抛出错误 - {e}")
    
    # 测试2: 完全上涨的价格序列
    print("\n测试2: 完全上涨的价格序列")
    rising_prices = pd.Series(np.linspace(100, 200, 30))
    rsi_rising = calculate_rsi(rising_prices, period=14)
    rsi_rising_valid = rsi_rising.dropna()
    if len(rsi_rising_valid) > 0:
        print(f"  RSI值应接近100: {rsi_rising_valid.iloc[-1]:.2f}")
    
    # 测试3: 完全下跌的价格序列
    print("\n测试3: 完全下跌的价格序列")
    falling_prices = pd.Series(np.linspace(200, 100, 30))
    rsi_falling = calculate_rsi(falling_prices, period=14)
    rsi_falling_valid = rsi_falling.dropna()
    if len(rsi_falling_valid) > 0:
        print(f"  RSI值应接近0: {rsi_falling_valid.iloc[-1]:.2f}")
    
    # 测试4: 恒定价格序列
    print("\n测试4: 恒定价格序列")
    constant_prices = pd.Series([100] * 30)
    rsi_constant = calculate_rsi(constant_prices, period=14)
    rsi_constant_valid = rsi_constant.dropna()
    if len(rsi_constant_valid) > 0:
        print(f"  RSI值应为50: {rsi_constant_valid.iloc[-1]:.2f}")


def test_rsi_with_dataframe():
    """测试将RSI添加到DataFrame"""
    print("\n\n测试将RSI添加到DataFrame")
    print("=" * 50)
    
    # 创建示例DataFrame
    n = 50
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    np.random.seed(42)
    
    data = pd.DataFrame({
        'Open': np.random.normal(100, 5, n),
        'High': np.random.normal(105, 5, n),
        'Low': np.random.normal(95, 5, n),
        'Close': np.random.normal(100, 5, n),
        'Volume': np.random.lognormal(10, 1, n)
    }, index=dates)
    
    print(f"原始DataFrame形状: {data.shape}")
    print(f"原始列: {list(data.columns)}")
    
    # 添加RSI
    from indicators import add_rsi_to_dataframe
    data_with_rsi = add_rsi_to_dataframe(data, period=14)
    
    print(f"\n添加RSI后的DataFrame形状: {data_with_rsi.shape}")
    print(f"添加RSI后的列: {list(data_with_rsi.columns)}")
    
    # 检查RSI列是否存在
    if 'RSI' in data_with_rsi.columns:
        print(f"✓ RSI列已成功添加")
        print(f"  RSI有效值数量: {data_with_rsi['RSI'].notna().sum()}")
        
        # 检查RSI信号列
        if 'RSI_signal' in data_with_rsi.columns:
            print(f"✓ RSI_signal列已成功添加")
            signal_counts = data_with_rsi['RSI_signal'].value_counts(dropna=False)
            print(f"  RSI信号分布:")
            for signal, count in signal_counts.items():
                print(f"    {signal}: {count} 次")
    
    # 获取统计信息
    stats = TechnicalIndicators.get_rsi_statistics(data_with_rsi['RSI'])
    if stats:
        print(f"\nRSI统计信息:")
        for key, value in stats.items():
            if isinstance(value, float):
                print(f"  {key}: {value:.2f}")
            else:
                print(f"  {key}: {value}")


if __name__ == "__main__":
    print("RSI计算功能测试")
    print("=" * 60)
    
    # 运行测试
    test_rsi_basic()
    test_rsi_edge_cases()
    test_rsi_with_dataframe()
    
    print("\n" + "=" * 60)
    print("所有测试完成!")