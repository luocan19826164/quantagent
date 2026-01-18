"""
量化策略主程序 - RSI策略回测

策略规则：
1. 当RSI(14) < 20时买入
2. 买入后当RSI(14) > 60时卖出
3. 回测最近一年的BTC数据
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import datetime, timedelta

from data_fetcher import DataFetcher
from indicators import calculate_rsi
from strategy import RSIStrategy
from backtester import Backtester


def main():
    """主函数：执行完整的RSI策略回测"""
    print("=== RSI策略回测系统 ===")
    print("策略：RSI(14) < 20买入，RSI(14) > 60卖出")
    print("币种：BTC-USD")
    print("周期：最近一年")
    print("=" * 30)
    
    # 1. 初始化组件
    print("\n1. 初始化组件...")
    data_fetcher = DataFetcher()
    strategy = RSIStrategy(rsi_period=14, buy_threshold=20, sell_threshold=60)
    backtester = Backtester(initial_capital=10000.0, commission_rate=0.001, slippage_rate=0.0005)
    
    # 2. 获取数据
    print("\n2. 获取BTC数据...")
    try:
        btc_data = data_fetcher.get_btc_data(period="1y", interval="1d")
        if btc_data is None or btc_data.empty:
            print("错误：无法获取BTC数据")
            return
        
        print(f"数据获取成功：{len(btc_data)} 条记录")
        print(f"数据时间范围：{btc_data.index[0]} 到 {btc_data.index[-1]}")
        print(f"数据列：{list(btc_data.columns)}")
    except Exception as e:
        print(f"获取数据时出错：{e}")
        return
    
    # 3. 计算RSI指标
    print("\n3. 计算RSI指标...")
    try:
        # 使用收盘价计算RSI
        close_prices = btc_data['Close'].values
        rsi_values = calculate_rsi(close_prices, period=14)
        
        # 将RSI值添加到数据中
        btc_data['RSI'] = rsi_values
        
        print(f"RSI计算完成，有效数据点：{len(rsi_values[~np.isnan(rsi_values)])}")
        print(f"RSI范围：{np.nanmin(rsi_values):.2f} - {np.nanmax(rsi_values):.2f}")
    except Exception as e:
        print(f"计算RSI时出错：{e}")
        return
    
    # 4. 生成交易信号
    print("\n4. 生成交易信号...")
    try:
        signals = strategy.generate_signals_vectorized(close_prices, rsi_values)
        
        # 统计信号数量
        buy_signals = np.sum(signals == 1)
        sell_signals = np.sum(signals == -1)
        hold_signals = np.sum(signals == 0)
        
        print(f"信号统计：买入 {buy_signals} 次，卖出 {sell_signals} 次，持有 {hold_signals} 次")
        
        # 将信号添加到数据中
        btc_data['Signal'] = signals
    except Exception as e:
        print(f"生成信号时出错：{e}")
        return
    
    # 5. 运行回测
    print("\n5. 运行回测...")
    try:
        performance = backtester.run_backtest(btc_data, signals, "RSI策略")
        
        if performance is None:
            print("回测失败：未生成有效的回测结果")
            return
        
        print("回测完成！")
    except Exception as e:
        print(f"运行回测时出错：{e}")
        return
    
    # 6. 输出结果
    print("\n6. 回测结果：")
    print("=" * 50)
    backtester.print_backtest_results(performance)
    print("=" * 50)
    
    # 7. 显示交易统计
    print("\n7. 交易统计：")
    print("-" * 30)
    backtester.print_trade_statistics(performance)
    
    # 8. 显示策略信息
    print("\n8. 策略配置：")
    print("-" * 30)
    strategy_info = strategy.get_strategy_info()
    for key, value in strategy_info.items():
        print(f"{key}: {value}")
    
    # 9. 保存数据到CSV（可选）
    try:
        btc_data.to_csv('btc_rsi_backtest_data.csv')
        print("\n数据已保存到：btc_rsi_backtest_data.csv")
    except Exception as e:
        print(f"\n保存数据时出错：{e}")
    
    # 10. 询问是否显示图表
    print("\n10. 是否显示回测图表？(y/n)")
    show_plot = input().strip().lower()
    
    if show_plot == 'y':
        try:
            backtester.plot_results(performance)
            plt.show()
        except Exception as e:
            print(f"显示图表时出错：{e}")
    
    print("\n=== 回测完成 ===")


def run_quick_test():
    """快速测试函数，用于验证基本功能"""
    print("运行快速测试...")
    
    # 测试数据获取
    data_fetcher = DataFetcher()
    data = data_fetcher.get_btc_data(period="1mo", interval="1d")
    
    if data is not None:
        print(f"测试数据获取成功：{len(data)} 条记录")
        
        # 测试RSI计算
        close_prices = data['Close'].values
        rsi_values = calculate_rsi(close_prices, period=14)
        print(f"RSI计算成功：{len(rsi_values)} 个值")
        
        # 测试策略
        strategy = RSIStrategy(rsi_period=14, buy_threshold=20, sell_threshold=60)
        signals = strategy.generate_signals_vectorized(close_prices, rsi_values)
        print(f"信号生成成功：{len(signals)} 个信号")
        
        # 测试回测
        backtester = Backtester(initial_capital=10000.0)
        performance = backtester.run_backtest(data, signals, "测试策略")
        
        if performance:
            print("回测运行成功！")
            backtester.print_backtest_results(performance)
    else:
        print("测试数据获取失败")


if __name__ == "__main__":
    # 可以选择运行完整回测或快速测试
    print("选择运行模式：")
    print("1. 完整回测（默认）")
    print("2. 快速测试")
    
    choice = input("请输入选择 (1/2): ").strip()
    
    if choice == "2":
        run_quick_test()
    else:
        main()
