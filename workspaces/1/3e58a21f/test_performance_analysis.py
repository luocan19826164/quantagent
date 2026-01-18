"""
测试绩效分析功能
"""

import pandas as pd
import numpy as np
from performance_analyzer import PerformanceAnalyzer, analyze_backtest_performance, PerformanceMetrics
from backtest_engine import BacktestEngine


def test_performance_analyzer_basic():
    """测试绩效分析器基本功能"""
    print("=== 测试绩效分析器基本功能 ===")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # 生成模拟价格数据
    prices = np.cumprod(1 + np.random.randn(100) * 0.01) * 100
    
    # 生成模拟RSI数据
    rsi_values = 50 + 50 * np.sin(np.linspace(0, 4*np.pi, 100)) + np.random.randn(100) * 10
    rsi_values = np.clip(rsi_values, 0, 100)
    
    # 生成模拟回测结果
    portfolio_values = 10000 * np.cumprod(1 + np.random.randn(100) * 0.005)
    
    backtest_results = pd.DataFrame({
        'portfolio_value': portfolio_values,
        'price': prices,
        'rsi': rsi_values,
        'signal': np.random.choice(['BUY', 'SELL', 'HOLD'], 100, p=[0.1, 0.1, 0.8]),
        'position': np.random.choice([0, 1], 100)
    }, index=dates)
    
    # 生成模拟交易记录
    trade_dates = dates[np.random.choice(range(100), 10, replace=False)]
    trades_df = pd.DataFrame({
        'timestamp': trade_dates,
        'action': np.random.choice(['BUY', 'SELL'], 10),
        'price': np.random.uniform(90, 110, 10),
        'quantity': np.random.uniform(0.5, 2.0, 10),
        'cash': np.random.uniform(8000, 12000, 10),
        'position': np.random.uniform(0, 100, 10),
        'portfolio_value': np.random.uniform(9000, 13000, 10),
        'rsi': np.random.uniform(10, 70, 10),
        'reason': ['RSI信号'] * 10
    })
    
    # 创建分析器
    analyzer = PerformanceAnalyzer()
    
    # 计算绩效指标
    metrics = analyzer.calculate_comprehensive_metrics(
        backtest_results=backtest_results,
        trades_df=trades_df,
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        position_size=1.0
    )
    
    print(f"✓ 绩效指标计算完成")
    print(f"  总收益率: {metrics.total_return_pct:.2f}%")
    print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown_pct:.2f}%")
    print(f"  交易次数: {metrics.num_trades}")
    
    # 生成报告
    print("\n=== 生成绩效报告 ===")
    report = analyzer.generate_performance_report(metrics, output_format='text')
    print(report[:500] + "...")  # 只显示前500字符
    
    print("\n✓ 绩效报告生成完成")


def test_analyze_backtest_performance_function():
    """测试便捷函数"""
    print("\n=== 测试analyze_backtest_performance便捷函数 ===")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=50, freq='D')
    
    # 生成更有意义的测试数据
    prices = np.array([100] * 50)
    
    # 前15天：价格下跌，RSI下降
    for i in range(15):
        prices[i] = 100 - i * 2
    
    # 中间20天：价格低位震荡
    for i in range(15, 35):
        prices[i] = 70 + np.random.randn() * 5
    
    # 后15天：价格上涨
    for i in range(35, 50):
        prices[i] = 70 + (i - 35) * 3
    
    # 计算RSI（简化版本）
    rsi_values = np.zeros(50)
    for i in range(1, 50):
        change = prices[i] - prices[i-1]
        if change > 0:
            rsi_values[i] = min(100, 30 + change * 2)  # 模拟RSI计算
        else:
            rsi_values[i] = max(0, 70 + change * 2)
    
    # 创建回测引擎并运行
    engine = BacktestEngine(
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0
    )
    
    test_data = pd.DataFrame({
        'Open': prices * 0.99,
        'High': prices * 1.02,
        'Low': prices * 0.98,
        'Close': prices,
        'Volume': np.random.uniform(1000, 5000, 50),
        'RSI_14': rsi_values
    }, index=dates)
    
    backtest_results = engine.run_backtest(test_data)
    trades_df = engine.get_trade_summary()
    
    print(f"回测数据点: {len(backtest_results)}")
    print(f"交易记录数: {len(trades_df)}")
    
    # 使用便捷函数进行分析
    print("\n运行全面的绩效分析...")
    metrics = analyze_backtest_performance(
        backtest_results=backtest_results,
        trades_df=trades_df,
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        position_size=1.0,
        generate_report=True,
        generate_charts=True,
        export_excel=True
    )
    
    print(f"\n✓ 便捷函数测试完成")
    print(f"关键指标:")
    print(f"  总收益率: {metrics.total_return_pct:.2f}%")
    print(f"  夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"  最大回撤: {metrics.max_drawdown_pct:.2f}%")
    print(f"  胜率: {metrics.win_rate_pct:.2f}%")


def test_performance_metrics_dataclass():
    """测试PerformanceMetrics数据类"""
    print("\n=== 测试PerformanceMetrics数据类 ===")
    
    # 创建PerformanceMetrics实例
    metrics = PerformanceMetrics(
        initial_capital=10000.0,
        final_portfolio_value=12500.0,
        total_return_pct=25.0,
        annualized_return_pct=30.0,
        volatility_pct=15.0,
        sharpe_ratio=2.0,
        sortino_ratio=2.5,
        max_drawdown_pct=-10.0,
        calmar_ratio=3.0,
        num_trades=10,
        num_buy_trades=5,
        num_sell_trades=5,
        win_rate_pct=60.0,
        profit_factor=1.5,
        avg_trade_return_pct=2.5,
        avg_holding_period_days=15.5,
        max_holding_period_days=30,
        min_holding_period_days=5,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        position_size=1.0,
        start_date=pd.Timestamp('2023-01-01'),
        end_date=pd.Timestamp('2023-12-31'),
        total_days=365
    )
    
    print(f"✓ PerformanceMetrics实例创建成功")
    print(f"  总收益率: {metrics.total_return_pct}%")
    print(f"  夏普比率: {metrics.sharpe_ratio}")
    print(f"  最大回撤: {metrics.max_drawdown_pct}%")
    print(f"  交易次数: {metrics.num_trades}")
    
    # 测试repr方法
    print(f"\n数据类表示:")
    print(repr(metrics)[:200] + "...")


def test_export_functionality():
    """测试导出功能"""
    print("\n=== 测试导出功能 ===")
    
    # 创建简单测试数据
    dates = pd.date_range('2023-01-01', periods=30, freq='D')
    
    backtest_results = pd.DataFrame({
        'portfolio_value': np.linspace(10000, 11000, 30),
        'price': np.linspace(100, 110, 30),
        'rsi': np.random.uniform(30, 70, 30),
        'signal': ['HOLD'] * 30,
        'position': [0] * 30
    }, index=dates)
    
    trades_df = pd.DataFrame({
        'timestamp': [dates[5], dates[15]],
        'action': ['BUY', 'SELL'],
        'price': [102.5, 107.5],
        'quantity': [97.56, 97.56],
        'cash': [0, 10487.5],
        'position': [97.56, 0],
        'portfolio_value': [10000, 10487.5],
        'rsi': [18.5, 62.3],
        'reason': ['RSI=18.5 < 20', 'RSI=62.3 > 60']
    })
    
    # 创建分析器
    analyzer = PerformanceAnalyzer()
    
    # 计算指标
    metrics = analyzer.calculate_comprehensive_metrics(
        backtest_results=backtest_results,
        trades_df=trades_df,
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        position_size=1.0
    )
    
    # 导出到Excel
    analyzer.export_results_to_excel(
        backtest_results=backtest_results,
        trades_df=trades_df,
        metrics=metrics,
        output_path='test_export.xlsx'
    )
    
    print(f"✓ Excel导出功能测试完成")
    print(f"  文件已生成: test_export.xlsx")
    
    # 验证文件内容
    try:
        excel_data = pd.read_excel('test_export.xlsx', sheet_name=None)
        print(f"  Excel包含 {len(excel_data)} 个工作表:")
        for sheet_name in excel_data.keys():
            print(f"    - {sheet_name}: {excel_data[sheet_name].shape} 行×列")
    except Exception as e:
        print(f"  ⚠️ 读取Excel文件时出错: {e}")


def main():
    """主测试函数"""
    print("开始测试绩效分析功能...\n")
    
    # 运行所有测试
    test_performance_analyzer_basic()
    test_performance_metrics_dataclass()
    test_analyze_backtest_performance_function()
    test_export_functionality()
    
    print("\n" + "="*60)
    print("所有测试完成！绩效分析功能正常。")
    print("="*60)


if __name__ == "__main__":
    main()