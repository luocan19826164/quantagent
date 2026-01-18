"""
量化策略主程序
实现基于RSI的BTC交易策略回测

功能:
1. 获取BTC历史数据
2. 计算RSI技术指标
3. 运行RSI策略回测
4. 分析回测结果
5. 生成报告和图表

使用说明:
1. 修改config.py中的参数配置
2. 运行: python main.py
3. 查看results目录中的结果文件

策略规则:
- 当RSI(14) < 20时买入
- 买入后当RSI > 60时卖出
- 每次交易使用全部可用资金

作者: 量化助手
版本: 1.0.0
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime
from data_fetcher import fetch_btc_data
from indicators import add_rsi_to_data
from backtest_engine import BacktestEngine, run_rsi_strategy_backtest
from performance_analyzer import analyze_backtest_performance
from config import (
    DEFAULT_STRATEGY_CONFIG,
    DEFAULT_BACKTEST_CONFIG,
    DEFAULT_PERFORMANCE_CONFIG,
    create_config_from_dict
)
from performance_analyzer import analyze_backtest_performance


def main():
    """
    主函数：运行完整的RSI策略回测流程
    
    流程:
    1. 加载配置参数
    2. 获取历史数据
    3. 计算技术指标
    4. 运行回测
    5. 分析结果
    6. 生成报告
    """
    
    print("开始BTC RSI策略回测...")
    print("=" * 60)
    
    # 加载配置
    print("\n=== 步骤1: 加载配置 ===")
    try:
        # 使用默认配置
        strategy_config = DEFAULT_STRATEGY_CONFIG
        backtest_config = DEFAULT_BACKTEST_CONFIG
        performance_config = DEFAULT_PERFORMANCE_CONFIG
        
        print(f"策略配置:")
        print(f"  RSI周期: {strategy_config.rsi_period}")
        print(f"  买入阈值: {strategy_config.rsi_buy_threshold}")
        print(f"  卖出阈值: {strategy_config.rsi_sell_threshold}")
        print(f"  仓位比例: {strategy_config.position_size:.0%}")
        print(f"  交易手续费: {strategy_config.transaction_fee:.2%}")
        
        print(f"\n回测配置:")
        print(f"  初始资金: ${backtest_config.initial_capital:,.2f}")
        print(f"  交易对: {backtest_config.symbol}")
        print(f"  数据周期: {backtest_config.period}")
        print(f"  数据间隔: {backtest_config.interval}")
        
        # 创建输出目录
        if backtest_config.save_results:
            os.makedirs(backtest_config.output_dir, exist_ok=True)
            print(f"\n输出目录: {backtest_config.output_dir}")
        
    except Exception as e:
        print(f"✗ 配置加载失败: {e}")
        return
    
    # 步骤2: 获取数据
    print("\n=== 步骤2: 获取BTC数据 ===")
    try:
        btc_data = fetch_btc_data(
            period=backtest_config.period, 
            interval=backtest_config.interval
        )
        print(f"✓ 成功获取 {len(btc_data)} 条BTC数据")
        print(f"  时间范围: {btc_data.index[0]} 到 {btc_data.index[-1]}")
        print(f"  数据列: {', '.join(btc_data.columns.tolist())}")
        
        # 显示数据基本信息
        print("\n数据基本信息:")
        print(f"  开盘价范围: ${btc_data['Open'].min():.2f} - ${btc_data['Open'].max():.2f}")
        print(f"  收盘价范围: ${btc_data['Close'].min():.2f} - ${btc_data['Close'].max():.2f}")
        print(f"  成交量均值: {btc_data['Volume'].mean():.2f}")
        
        # 保存原始数据
        if backtest_config.save_results:
            data_path = os.path.join(backtest_config.output_dir, "btc_historical_data.csv")
            btc_data.to_csv(data_path)
            print(f"\n✓ 原始数据已保存到: {data_path}")
        
    except Exception as e:
        print(f"✗ 数据获取失败: {e}")
        return
    
    # 步骤3: 计算RSI指标
    print("\n=== 步骤3: 计算RSI指标 ===")
    try:
        btc_data_with_rsi = add_rsi_to_data(
            btc_data, 
            period=strategy_config.rsi_period, 
            price_column='Close'
        )
        print(f"✓ RSI({strategy_config.rsi_period})计算完成")
        
        # 显示RSI统计信息
        rsi_column = f'RSI_{strategy_config.rsi_period}'
        rsi_data = btc_data_with_rsi[rsi_column].dropna()
        print(f"  RSI有效数据点: {len(rsi_data)}")
        print(f"  RSI平均值: {rsi_data.mean():.2f}")
        print(f"  RSI范围: [{rsi_data.min():.2f}, {rsi_data.max():.2f}]")
        print(f"  RSI < {strategy_config.rsi_buy_threshold} 的比例: "
              f"{(rsi_data < strategy_config.rsi_buy_threshold).sum() / len(rsi_data):.2%}")
        print(f"  RSI > {strategy_config.rsi_sell_threshold} 的比例: "
              f"{(rsi_data > strategy_config.rsi_sell_threshold).sum() / len(rsi_data):.2%}")
        
        # 保存带RSI的数据
        if backtest_config.save_results:
            data_path = os.path.join(backtest_config.output_dir, "btc_data_with_rsi.csv")
            btc_data_with_rsi.to_csv(data_path)
            print(f"\n✓ 带RSI的数据已保存到: {data_path}")
        
    except Exception as e:
        print(f"✗ RSI计算失败: {e}")
        return
    
    # 步骤4: 运行回测
    print("\n=== 步骤4: 运行回测 ===")
    try:
        print(f"回测参数:")
        print(f"  初始资金: ${backtest_config.initial_capital:,.2f}")
        print(f"  RSI买入阈值: {strategy_config.rsi_buy_threshold}")
        print(f"  RSI卖出阈值: {strategy_config.rsi_sell_threshold}")
        print(f"  仓位比例: {strategy_config.position_size:.0%}")
        print(f"  交易手续费: {strategy_config.transaction_fee:.2%}")
        print(f"  滑点: {strategy_config.slippage:.2%}")
        
        # 运行回测
        backtest_results, metrics = run_rsi_strategy_backtest(
            data=btc_data_with_rsi,
            initial_capital=backtest_config.initial_capital,
            rsi_buy_threshold=strategy_config.rsi_buy_threshold,
            rsi_sell_threshold=strategy_config.rsi_sell_threshold,
            position_size=strategy_config.position_size,
            transaction_fee=strategy_config.transaction_fee,
            slippage=strategy_config.slippage
        )
        
        print(f"\n✓ 回测完成，共 {len(backtest_results)} 个交易日")
        
        # 显示回测结果摘要
        print("\n回测结果摘要:")
        print(f"  初始组合价值: ${metrics['initial_capital']:,.2f}")
        print(f"  最终组合价值: ${metrics['final_portfolio_value']:,.2f}")
        print(f"  总收益率: {metrics['total_return_pct']:.2f}%")
        print(f"  年化收益率: {metrics['annualized_return_pct']:.2f}%")
        print(f"  夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"  最大回撤: {metrics['max_drawdown_pct']:.2f}%")
        print(f"  交易次数: {metrics['num_trades']} (买入: {metrics['num_buys']}, 卖出: {metrics['num_sells']})")
        print(f"  胜率: {metrics['win_rate_pct']:.2f}%")
        
        # 保存回测结果
        if backtest_config.save_results:
            results_path = os.path.join(backtest_config.output_dir, "backtest_results.csv")
            backtest_results.to_csv(results_path)
            print(f"\n✓ 回测结果已保存到: {results_path}")
        
        # 显示交易记录
        engine = BacktestEngine(
            initial_capital=backtest_config.initial_capital,
            transaction_fee=strategy_config.transaction_fee,
            slippage=strategy_config.slippage,
            rsi_buy_threshold=strategy_config.rsi_buy_threshold,
            rsi_sell_threshold=strategy_config.rsi_sell_threshold,
            position_size=strategy_config.position_size
        )
        engine.run_backtest(btc_data_with_rsi)
        trades = engine.get_trade_summary()
        
        if not trades.empty:
            if backtest_config.save_results:
                trades_path = os.path.join(backtest_config.output_dir, "trade_records.csv")
                trades.to_csv(trades_path, index=False)
                print(f"✓ 交易记录已保存到: {trades_path}")
            
            print("\n交易记录:")
            for i, trade in trades.iterrows():
                print(f"  {i+1}. {trade['timestamp'].date()} {trade['action']} "
                      f"@ ${trade['price']:.2f} (RSI: {trade['rsi']:.2f})")
        else:
            print("\n⚠️ 没有交易记录")
        
        # 保存性能指标
        metrics_df = pd.DataFrame([metrics])
        metrics_df.to_csv("performance_metrics.csv", index=False)
        print(f"\n✓ 性能指标已保存到: performance_metrics.csv")
        
        # 步骤4: 进行全面的绩效分析
        print("\n=== 步骤4: 全面绩效分析 ===")
        try:
            # 获取交易记录
            engine = BacktestEngine(
                initial_capital=initial_capital,
                rsi_buy_threshold=rsi_buy_threshold,
                rsi_sell_threshold=rsi_sell_threshold,
                position_size=position_size
            )
            engine.run_backtest(btc_data_with_rsi)
            trades_df = engine.get_trade_summary()
            
            # 运行全面的绩效分析
            print("运行全面的绩效分析...")
            comprehensive_metrics = analyze_backtest_performance(
                backtest_results=backtest_results,
                trades_df=trades_df,
                initial_capital=initial_capital,
                rsi_buy_threshold=rsi_buy_threshold,
                rsi_sell_threshold=rsi_sell_threshold,
                position_size=position_size,
                generate_report=True,
                generate_charts=True,
                export_excel=True
            )
            
            print(f"\n✓ 全面绩效分析完成！")
            
        except Exception as e:
            print(f"⚠️ 全面绩效分析遇到问题: {e}")
            print("继续执行基本回测结果...")
        
    except Exception as e:
        print(f"✗ 回测失败: {e}")
        return
    
    print("\n" + "=" * 60)
    print("回测完成！请查看生成的文件进行分析。")
    print("生成的文件:")
    print("  - btc_historical_data.csv: 原始BTC数据")
    print("  - btc_data_with_rsi.csv: 带RSI指标的BTC数据")
    print("  - backtest_results.csv: 每日回测结果")
    print("  - trade_records.csv: 交易记录")
    print("  - performance_metrics.csv: 性能指标")
    print("  - backtest_results.xlsx: 完整的Excel报告")
    print("=" * 60)


if __name__ == "__main__":
    main()
