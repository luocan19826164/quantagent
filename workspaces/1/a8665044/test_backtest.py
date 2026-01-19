#!/usr/bin/env python3
"""
测试回测引擎功能
"""

import pandas as pd
import numpy as np
from backtest import BacktestEngine, run_rsi_backtest, Trade
from indicators import TechnicalIndicators


def test_backtest_basic():
    """测试基本回测功能"""
    print("测试基本回测功能")
    print("=" * 50)
    
    # 创建回测引擎
    engine = BacktestEngine(initial_capital=10000.0)
    
    print(f"初始资金: ${engine.initial_capital:,.2f}")
    print(f"当前现金: ${engine.cash:,.2f}")
    print(f"当前持仓: {engine.position}")
    print(f"是否持仓: {engine.in_position}")
    
    # 测试买入
    print("\n测试买入操作...")
    timestamp = pd.Timestamp('2024-01-01')
    price = 100.0
    rsi_value = 18.5
    
    success = engine.buy(timestamp, price, rsi_value)
    print(f"买入成功: {success}")
    print(f"买入后现金: ${engine.cash:,.2f}")
    print(f"买入后持仓: {engine.position}")
    print(f"是否持仓: {engine.in_position}")
    
    # 测试卖出
    print("\n测试卖出操作...")
    timestamp2 = pd.Timestamp('2024-01-10')
    price2 = 110.0
    rsi_value2 = 65.0
    
    success2 = engine.sell(timestamp2, price2, rsi_value2)
    print(f"卖出成功: {success2}")
    print(f"卖出后现金: ${engine.cash:,.2f}")
    print(f"卖出后持仓: {engine.position}")
    print(f"是否持仓: {engine.in_position}")
    
    # 显示交易记录
    print(f"\n交易记录 ({len(engine.trades)} 笔):")
    for trade in engine.trades:
        print(f"  {trade}")
    
    return engine


def test_rsi_strategy_simulation():
    """测试RSI策略模拟"""
    print("\n\n测试RSI策略模拟")
    print("=" * 50)
    
    # 创建模拟数据
    np.random.seed(42)
    n = 200
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 创建价格序列（有趋势的随机游走）
    prices = [100.0]
    for i in range(1, n):
        # 模拟趋势 + 噪声
        trend = 0.0005  # 轻微上涨趋势
        noise = np.random.normal(0, 0.02)
        new_price = prices[-1] * (1 + trend + noise)
        prices.append(new_price)
    
    # 创建RSI序列（模拟超买超卖周期）
    rsi_values = []
    for i in range(n):
        # 模拟RSI周期：在20-80之间波动
        cycle = 50 + 30 * np.sin(2 * np.pi * i / 40)  # 40天周期
        noise = np.random.normal(0, 5)
        rsi = cycle + noise
        # 限制在0-100范围内
        rsi = max(0, min(100, rsi))
        rsi_values.append(rsi)
    
    # 创建DataFrame
    data = pd.DataFrame({
        'Open': np.array(prices) * 0.99,
        'High': np.array(prices) * 1.02,
        'Low': np.array(prices) * 0.98,
        'Close': prices,
        'Volume': np.random.lognormal(15, 1, n),
        'RSI': rsi_values
    }, index=dates)
    
    print(f"模拟数据形状: {data.shape}")
    print(f"时间范围: {data.index[0].date()} 到 {data.index[-1].date()}")
    print(f"价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
    print(f"RSI范围: {data['RSI'].min():.2f} - {data['RSI'].max():.2f}")
    
    # 运行回测
    print("\n运行RSI策略回测...")
    result_data, stats, engine = run_rsi_backtest(
        data=data,
        initial_capital=10000.0,
        oversold_threshold=20.0,
        overbought_threshold=60.0,
        commission_rate=0.001
    )
    
    # 显示结果
    print(f"\n回测统计:")
    print(f"初始资金: ${stats['initial_capital']:,.2f}")
    print(f"最终价值: ${stats['final_value']:,.2f}")
    print(f"总收益率: {stats['total_return_pct']:.2f}%")
    print(f"交易次数: {stats['total_trades']} 次")
    print(f"胜率: {stats['win_rate_pct']:.1f}%")
    print(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
    
    # 显示交易记录
    if engine.trades:
        print(f"\n交易记录 ({len(engine.trades)} 笔):")
        for i, trade in enumerate(engine.trades, 1):
            date_str = trade.timestamp.strftime('%Y-%m-%d')
            rsi_str = f"RSI={trade.rsi_value:.2f}" if trade.rsi_value else "RSI=N/A"
            print(f"{i:2d}. {date_str}: {trade.trade_type.upper():4s} "
                  f"@ ${trade.price:,.2f}, 数量={trade.quantity:.4f}, "
                  f"现金=${trade.cash_balance:,.2f}, {rsi_str}")
    
    # 显示权益曲线
    print(f"\n权益曲线统计:")
    print(f"起始价值: ${result_data['Portfolio_Value'].iloc[0]:,.2f}")
    print(f"结束价值: ${result_data['Portfolio_Value'].iloc[-1]:,.2f}")
    print(f"最高价值: ${result_data['Portfolio_Value'].max():,.2f}")
    print(f"最低价值: ${result_data['Portfolio_Value'].min():,.2f}")
    
    return result_data, stats, engine


def test_edge_cases():
    """测试边界情况"""
    print("\n\n测试边界情况")
    print("=" * 50)
    
    # 测试1: 没有交易信号的情况
    print("\n测试1: 没有交易信号")
    np.random.seed(42)
    n = 50
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 创建RSI始终在30-50之间的数据（没有超买超卖）
    data_no_signal = pd.DataFrame({
        'Close': np.linspace(100, 110, n),
        'RSI': np.random.uniform(30, 50, n)
    }, index=dates)
    
    result_no_signal, stats_no_signal, engine_no_signal = run_rsi_backtest(
        data=data_no_signal,
        initial_capital=10000.0,
        oversold_threshold=20.0,
        overbought_threshold=60.0
    )
    
    print(f"  交易次数: {stats_no_signal['total_trades']} 次")
    print(f"  最终价值: ${stats_no_signal['final_value']:,.2f}")
    
    # 测试2: 频繁交易的情况
    print("\n测试2: 频繁交易")
    # 创建RSI在超买超卖之间频繁波动的数据
    rsi_volatile = []
    for i in range(n):
        # 每5天切换一次超买超卖状态
        if (i // 5) % 2 == 0:
            rsi_volatile.append(np.random.uniform(10, 20))  # 超卖
        else:
            rsi_volatile.append(np.random.uniform(70, 80))  # 超买
    
    data_volatile = pd.DataFrame({
        'Close': np.linspace(100, 110, n),
        'RSI': rsi_volatile
    }, index=dates)
    
    result_volatile, stats_volatile, engine_volatile = run_rsi_backtest(
        data=data_volatile,
        initial_capital=10000.0,
        oversold_threshold=20.0,
        overbought_threshold=60.0
    )
    
    print(f"  交易次数: {stats_volatile['total_trades']} 次")
    print(f"  最终价值: ${stats_volatile['final_value']:,.2f}")
    
    # 测试3: 数据包含NaN值
    print("\n测试3: 数据包含NaN值")
    data_with_nan = data_volatile.copy()
    data_with_nan.loc[data_with_nan.index[10:15], 'RSI'] = np.nan
    
    result_nan, stats_nan, engine_nan = run_rsi_backtest(
        data=data_with_nan,
        initial_capital=10000.0,
        oversold_threshold=20.0,
        overbought_threshold=60.0
    )
    
    print(f"  交易次数: {stats_nan['total_trades']} 次")
    print(f"  最终价值: ${stats_nan['final_value']:,.2f}")
    print(f"  NaN值数量: {data_with_nan['RSI'].isna().sum()}")


def test_trade_class():
    """测试Trade类"""
    print("\n\n测试Trade类")
    print("=" * 50)
    
    # 创建交易记录
    timestamp = pd.Timestamp('2024-01-15')
    buy_trade = Trade(
        trade_type='buy',
        timestamp=timestamp,
        price=100.0,
        quantity=10.0,
        cash_balance=9000.0,
        position=10.0,
        rsi_value=18.5
    )
    
    sell_trade = Trade(
        trade_type='sell',
        timestamp=timestamp + pd.Timedelta(days=5),
        price=110.0,
        quantity=10.0,
        cash_balance=10900.0,
        position=0.0,
        rsi_value=65.0
    )
    
    print(f"买入交易: {buy_trade}")
    print(f"卖出交易: {sell_trade}")
    
    print(f"\n买入金额: ${buy_trade.amount:,.2f} (应为负值)")
    print(f"卖出金额: ${sell_trade.amount:,.2f} (应为正值)")
    
    # 验证金额计算
    expected_buy_amount = -100.0 * 10.0
    expected_sell_amount = 110.0 * 10.0
    
    assert abs(buy_trade.amount - expected_buy_amount) < 0.01, "买入金额计算错误"
    assert abs(sell_trade.amount - expected_sell_amount) < 0.01, "卖出金额计算错误"
    
    print("✓ Trade类测试通过")


if __name__ == "__main__":
    print("回测引擎功能测试")
    print("=" * 60)
    
    # 运行测试
    engine = test_backtest_basic()
    result_data, stats, engine = test_rsi_strategy_simulation()
    test_edge_cases()
    test_trade_class()
    
    print("\n" + "=" * 60)
    print("所有测试完成!")
    
    # 保存测试结果
    if 'result_data' in locals():
        result_data.to_csv("test_backtest_results.csv")
        print(f"测试结果已保存到: test_backtest_results.csv")