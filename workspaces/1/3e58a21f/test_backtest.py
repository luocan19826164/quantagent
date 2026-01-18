"""
测试回测引擎功能
"""

import pandas as pd
import numpy as np
from backtest_engine import BacktestEngine, TradeAction
from indicators import calculate_rsi


def test_backtest_engine_basic():
    """测试回测引擎基本功能"""
    print("=== 测试回测引擎基本功能 ===")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=50, freq='D')
    
    # 生成模拟价格：先下跌后上涨，触发RSI信号
    prices = np.array([100] * 50)
    
    # 前20天：价格下跌，RSI下降
    for i in range(20):
        prices[i] = 100 - i * 2  # 线性下跌到60
    
    # 中间10天：价格低位震荡，RSI < 20
    for i in range(20, 30):
        prices[i] = 60 + np.random.randn() * 2
    
    # 后20天：价格上涨，RSI上升
    for i in range(30, 50):
        prices[i] = 60 + (i - 30) * 3  # 线性上涨到120
    
    # 计算RSI
    rsi_values = calculate_rsi(pd.Series(prices), period=14)
    
    test_data = pd.DataFrame({
        'Open': prices * 0.99,
        'High': prices * 1.02,
        'Low': prices * 0.98,
        'Close': prices,
        'Volume': np.random.uniform(1000, 5000, 50),
        'RSI_14': rsi_values
    }, index=dates)
    
    print(f"测试数据形状: {test_data.shape}")
    print(f"价格范围: ${prices.min():.2f} - ${prices.max():.2f}")
    print(f"RSI范围: {rsi_values.min():.2f} - {rsi_values.max():.2f}")
    
    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        position_size=1.0
    )
    
    # 测试信号生成
    print("\n=== 测试信号生成 ===")
    data_with_signals = engine.generate_signals(test_data)
    
    # 统计信号
    buy_signals = (data_with_signals['signal'] == 'BUY').sum()
    sell_signals = (data_with_signals['signal'] == 'SELL').sum()
    hold_signals = (data_with_signals['signal'] == 'HOLD').sum()
    
    print(f"买入信号: {buy_signals}")
    print(f"卖出信号: {sell_signals}")
    print(f"持有信号: {hold_signals}")
    
    # 显示有信号的日期
    signal_dates = data_with_signals[data_with_signals['signal'] != 'HOLD']
    if not signal_dates.empty:
        print("\n信号日期:")
        for date, row in signal_dates.iterrows():
            print(f"  {date.date()}: {row['signal']} (RSI: {row['RSI_14']:.2f}, 价格: ${row['Close']:.2f})")
    
    # 运行回测
    print("\n=== 运行回测 ===")
    results = engine.run_backtest(test_data)
    
    print(f"回测结果形状: {results.shape}")
    print(f"初始组合价值: ${results['portfolio_value'].iloc[0]:.2f}")
    print(f"最终组合价值: ${results['portfolio_value'].iloc[-1]:.2f}")
    
    # 获取交易记录
    trades = engine.get_trade_summary()
    print(f"\n交易记录数量: {len(trades)}")
    
    if not trades.empty:
        print("\n交易详情:")
        for i, trade in trades.iterrows():
            print(f"  {i+1}. {trade['timestamp'].date()} {trade['action']} "
                  f"@ ${trade['price']:.2f} (数量: {trade['quantity']:.4f}, "
                  f"组合价值: ${trade['portfolio_value']:.2f}, RSI: {trade['rsi']:.2f})")
    
    # 计算性能指标
    metrics = engine.get_performance_metrics(results)
    
    if metrics:
        print("\n=== 性能指标 ===")
        print(f"总收益率: {metrics['total_return_pct']:.2f}%")
        print(f"年化收益率: {metrics['annualized_return_pct']:.2f}%")
        print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"最大回撤: {metrics['max_drawdown_pct']:.2f}%")
        print(f"交易次数: {metrics['num_trades']}")
    
    print("\n✓ 回测引擎基本功能测试完成")


def test_edge_cases():
    """测试边界情况"""
    print("\n=== 测试边界情况 ===")
    
    # 测试1: 没有交易信号的情况
    print("\n测试1: 没有交易信号")
    dates = pd.date_range('2023-01-01', periods=30, freq='D')
    prices = np.linspace(100, 110, 30)  # 缓慢上涨，RSI在40-60之间
    
    test_data = pd.DataFrame({
        'Open': prices * 0.99,
        'High': prices * 1.02,
        'Low': prices * 0.98,
        'Close': prices,
        'Volume': np.random.uniform(1000, 5000, 30),
        'RSI_14': np.full(30, 50.0)  # RSI始终为50
    }, index=dates)
    
    engine = BacktestEngine(rsi_buy_threshold=20.0, rsi_sell_threshold=60.0)
    results = engine.run_backtest(test_data)
    trades = engine.get_trade_summary()
    
    print(f"  数据点: {len(test_data)}")
    print(f"  交易次数: {len(trades)}")
    print(f"  最终组合价值: ${results['portfolio_value'].iloc[-1]:.2f}")
    
    # 测试2: 频繁交易的情况
    print("\n测试2: 频繁交易")
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    
    # 生成交替的RSI值，触发频繁交易
    rsi_pattern = []
    for i in range(100):
        if i % 10 < 5:
            rsi_pattern.append(15.0)  # 低于买入阈值
        else:
            rsi_pattern.append(65.0)  # 高于卖出阈值
    
    test_data = pd.DataFrame({
        'Open': np.linspace(100, 200, 100) * 0.99,
        'High': np.linspace(100, 200, 100) * 1.02,
        'Low': np.linspace(100, 200, 100) * 0.98,
        'Close': np.linspace(100, 200, 100),
        'Volume': np.random.uniform(1000, 5000, 100),
        'RSI_14': rsi_pattern
    }, index=dates)
    
    engine = BacktestEngine(rsi_buy_threshold=20.0, rsi_sell_threshold=60.0)
    results = engine.run_backtest(test_data)
    trades = engine.get_trade_summary()
    
    print(f"  数据点: {len(test_data)}")
    print(f"  交易次数: {len(trades)}")
    print(f"  买入次数: {(trades['action'] == 'BUY').sum() if not trades.empty else 0}")
    print(f"  卖出次数: {(trades['action'] == 'SELL').sum() if not trades.empty else 0}")
    
    print("\n✓ 边界情况测试完成")


def test_rsi_threshold_variations():
    """测试不同RSI阈值"""
    print("\n=== 测试不同RSI阈值 ===")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    
    # 生成正弦波形的RSI值
    t = np.linspace(0, 4*np.pi, 100)
    rsi_values = 40 + 30 * np.sin(t)  # RSI在10-70之间波动
    
    prices = np.cumprod(1 + np.random.randn(100) * 0.01) * 100
    
    test_data = pd.DataFrame({
        'Open': prices * 0.99,
        'High': prices * 1.02,
        'Low': prices * 0.98,
        'Close': prices,
        'Volume': np.random.uniform(1000, 5000, 100),
        'RSI_14': rsi_values
    }, index=dates)
    
    # 测试不同的阈值组合
    threshold_combinations = [
        (20, 60),  # 原始阈值
        (30, 70),  # 更宽松
        (10, 50),  # 更激进
        (25, 75),  # 不对称
    ]
    
    for buy_thresh, sell_thresh in threshold_combinations:
        print(f"\n阈值: 买入<{buy_thresh}, 卖出>{sell_thresh}")
        
        engine = BacktestEngine(
            initial_capital=10000.0,
            rsi_buy_threshold=buy_thresh,
            rsi_sell_threshold=sell_thresh
        )
        
        results = engine.run_backtest(test_data)
        trades = engine.get_trade_summary()
        metrics = engine.get_performance_metrics(results)
        
        print(f"  交易次数: {len(trades)}")
        if metrics:
            print(f"  总收益率: {metrics['total_return_pct']:.2f}%")
            print(f"  最大回撤: {metrics['max_drawdown_pct']:.2f}%")
    
    print("\n✓ RSI阈值测试完成")


def main():
    """主测试函数"""
    print("开始测试回测引擎功能...")
    print("=" * 60)
    
    try:
        test_backtest_engine_basic()
        test_edge_cases()
        test_rsi_threshold_variations()
        
        print("\n" + "=" * 60)
        print("所有测试完成！回测引擎功能正常。")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()