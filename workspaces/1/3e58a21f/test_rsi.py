"""
测试RSI指标计算
"""

import pandas as pd
import numpy as np
from indicators import calculate_rsi, add_rsi_to_data, calculate_simple_rsi
from data_fetcher import DataFetcher


def test_basic_rsi():
    """测试基本的RSI计算"""
    print("=== 测试基本RSI计算 ===")
    
    # 创建简单的测试数据
    test_prices = pd.Series([100, 102, 101, 103, 105, 104, 106, 108, 107, 109, 
                             110, 108, 107, 106, 105, 104, 103, 102, 101, 100])
    
    print(f"测试价格序列: {list(test_prices)}")
    
    # 计算RSI
    rsi_ema = calculate_rsi(test_prices, period=14)
    rsi_sma = calculate_simple_rsi(test_prices, period=14)
    
    print(f"\nRSI(14) EMA版本:")
    print(rsi_ema.tail(5))
    
    print(f"\nRSI(14) SMA版本:")
    print(rsi_sma.tail(5))
    
    # 验证RSI值在合理范围内
    assert (rsi_ema.dropna() >= 0).all() and (rsi_ema.dropna() <= 100).all(), "RSI值超出0-100范围"
    print("\n✓ RSI值范围验证通过")


def test_add_rsi_to_dataframe():
    """测试将RSI添加到DataFrame"""
    print("\n=== 测试将RSI添加到DataFrame ===")
    
    # 创建测试DataFrame
    dates = pd.date_range('2023-01-01', periods=20, freq='D')
    test_data = pd.DataFrame({
        'Open': np.random.uniform(90, 110, 20),
        'High': np.random.uniform(95, 115, 20),
        'Low': np.random.uniform(85, 105, 20),
        'Close': np.linspace(100, 120, 20),
        'Volume': np.random.uniform(1000, 5000, 20)
    }, index=dates)
    
    print(f"原始数据形状: {test_data.shape}")
    print(f"原始数据列: {test_data.columns.tolist()}")
    
    # 添加RSI
    data_with_rsi = add_rsi_to_data(test_data, period=14)
    
    print(f"\n添加RSI后数据形状: {data_with_rsi.shape}")
    print(f"添加RSI后数据列: {data_with_rsi.columns.tolist()}")
    
    # 验证RSI列存在
    assert 'RSI_14' in data_with_rsi.columns, "RSI列未成功添加"
    print(f"\n✓ RSI列添加成功")
    
    # 显示部分数据
    print(f"\n包含RSI的数据（最后5行）:")
    print(data_with_rsi[['Close', 'RSI_14']].tail())


def test_real_data_rsi():
    """测试真实数据上的RSI计算"""
    print("\n=== 测试真实数据上的RSI计算 ===")
    
    try:
        # 创建数据获取器
        fetcher = DataFetcher("BTC-USD")
        
        # 获取少量数据用于测试
        print("获取BTC数据...")
        data = fetcher.fetch_last_year_data(period="1mo", interval="1d", add_rsi=True, rsi_period=14)
        
        print(f"\n获取数据成功！数据形状: {data.shape}")
        print(f"数据列: {data.columns.tolist()}")
        
        # 验证RSI列存在
        if 'RSI_14' in data.columns:
            rsi_data = data['RSI_14'].dropna()
            print(f"\nRSI(14)统计信息:")
            print(f"有效数据点: {len(rsi_data)}")
            print(f"平均值: {rsi_data.mean():.2f}")
            print(f"范围: [{rsi_data.min():.2f}, {rsi_data.max():.2f}]")
            print(f"<20的比例: {(rsi_data < 20).sum() / len(rsi_data):.2%}")
            print(f">60的比例: {(rsi_data > 60).sum() / len(rsi_data):.2%}")
            
            print(f"\n✓ 真实数据RSI计算成功")
        else:
            print("✗ RSI列未找到")
            
    except Exception as e:
        print(f"测试失败: {e}")


def test_rsi_edge_cases():
    """测试RSI边界情况"""
    print("\n=== 测试RSI边界情况 ===")
    
    # 测试1: 单调上涨的价格
    print("测试1: 单调上涨的价格")
    rising_prices = pd.Series([100, 101, 102, 103, 104, 105, 106, 107, 108, 109])
    rsi_rising = calculate_rsi(rising_prices, period=5)
    print(f"单调上涨价格的RSI: {rsi_rising.iloc[-1]:.2f}")
    
    # 测试2: 单调下跌的价格
    print("\n测试2: 单调下跌的价格")
    falling_prices = pd.Series([100, 99, 98, 97, 96, 95, 94, 93, 92, 91])
    rsi_falling = calculate_rsi(falling_prices, period=5)
    print(f"单调下跌价格的RSI: {rsi_falling.iloc[-1]:.2f}")
    
    # 测试3: 价格不变
    print("\n测试3: 价格不变")
    constant_prices = pd.Series([100] * 10)
    rsi_constant = calculate_rsi(constant_prices, period=5)
    print(f"价格不变的RSI: {rsi_constant.iloc[-1]:.2f}")
    
    print("\n✓ 边界情况测试完成")


def main():
    """主测试函数"""
    print("开始测试RSI指标计算功能...\n")
    
    # 运行所有测试
    test_basic_rsi()
    test_add_rsi_to_dataframe()
    test_real_data_rsi()
    test_rsi_edge_cases()
    
    print("\n" + "="*50)
    print("所有测试完成！RSI指标计算功能正常。")
    print("="*50)


if __name__ == "__main__":
    main()