#!/usr/bin/env python3
"""
测试比特币数据获取
"""

import pandas as pd
import numpy as np
import yfinance as yf
from datetime import datetime, timedelta
import time

def fetch_bitcoin_data_simple():
    """简单的数据获取函数"""
    print("尝试获取比特币数据...")
    
    # 尝试不同的时间间隔
    intervals = ["1h", "1d"]  # 先尝试小时线，再尝试日线
    
    for interval in intervals:
        print(f"\n尝试获取 {interval} 间隔数据...")
        try:
            # 创建 ticker 对象
            ticker = yf.Ticker("BTC-USD")
            
            # 获取最近一年的数据
            print(f"获取最近一年的 {interval} 数据...")
            data = ticker.history(period="1y", interval=interval)
            
            if data.empty:
                print(f"未获取到 {interval} 数据")
                continue
            
            print(f"成功获取 {len(data)} 条 {interval} 数据")
            print(f"时间范围: {data.index[0]} 到 {data.index[-1]}")
            print(f"数据列: {list(data.columns)}")
            
            # 显示基本信息
            print(f"\n数据基本信息:")
            print(f"开盘价范围: ${data['Open'].min():,.2f} - ${data['Open'].max():,.2f}")
            print(f"收盘价范围: ${data['Close'].min():,.2f} - ${data['Close'].max():,.2f}")
            print(f"成交量均值: {data['Volume'].mean():,.0f}")
            
            # 保存到 CSV
            filename = f"btc_{interval}_data.csv"
            data.to_csv(filename)
            print(f"数据已保存到: {filename}")
            
            return data, interval
            
        except Exception as e:
            print(f"获取 {interval} 数据失败: {e}")
            time.sleep(2)  # 等待2秒后重试
    
    return None, None

def create_sample_data():
    """如果无法获取实时数据，创建示例数据"""
    print("\n无法获取实时数据，创建示例数据...")
    
    # 创建最近一年的日期范围
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)
    dates = pd.date_range(start=start_date, end=end_date, freq='D')
    
    # 创建示例价格数据（基于比特币历史价格范围）
    np.random.seed(42)
    n = len(dates)
    
    # 模拟比特币价格走势
    base_price = 30000  # 起始价格
    returns = np.random.normal(0.001, 0.03, n)  # 日收益率
    
    prices = [base_price]
    for r in returns:
        prices.append(prices[-1] * (1 + r))
    prices = prices[1:]  # 去掉第一个重复值
    
    # 将价格列表转换为 numpy 数组
    prices_array = np.array(prices)
    
    # 创建 DataFrame
    data = pd.DataFrame({
        'Open': prices_array * 0.99,  # 开盘价略低于收盘价
        'High': prices_array * 1.02,  # 最高价
        'Low': prices_array * 0.98,   # 最低价
        'Close': prices_array,        # 收盘价
        'Volume': np.random.lognormal(15, 1, n)  # 成交量
    }, index=dates)
    
    # 添加调整后收盘价
    data['Adj Close'] = data['Close']
    
    print(f"创建了 {len(data)} 条示例数据")
    print(f"时间范围: {data.index[0].date()} 到 {data.index[-1].date()}")
    print(f"价格范围: ${data['Close'].min():,.2f} - ${data['Close'].max():,.2f}")
    
    # 保存到 CSV
    data.to_csv("btc_sample_data.csv")
    print("示例数据已保存到: btc_sample_data.csv")
    
    return data

if __name__ == "__main__":
    print("比特币数据获取测试")
    print("=" * 50)
    
    # 尝试获取真实数据
    data, interval = fetch_bitcoin_data_simple()
    
    if data is not None:
        print(f"\n✓ 成功获取比特币 {interval} 数据")
        print(f"数据形状: {data.shape}")
        print(f"前3行数据:")
        print(data.head(3))
        print(f"\n后3行数据:")
        print(data.tail(3))
    else:
        print("\n⚠️ 无法获取实时数据，使用示例数据")
        data = create_sample_data()
        print(f"\n示例数据形状: {data.shape}")
        print(f"前3行数据:")
        print(data.head(3))