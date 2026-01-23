"""
量化策略主程序
BTC RSI策略回测系统

策略规则：
1. 当RSI(14) < 20时，全仓买入BTC
2. 当RSI(14) > 60时，全仓卖出BTC
3. 初始资金：10,000美元
4. 手续费：0.1%（每笔交易）
5. 时间范围：最近365天
"""

import pandas as pd
import numpy as np
from data_fetcher import fetch_btc_data
from indicators import add_technical_indicators
from strategy import run_rsi_strategy


def main():
    """主函数"""
    print("="*80)
    print("BTC RSI策略回测系统")
    print("="*80)
    
    try:
        # 1. 获取BTC价格数据
        print("\n步骤1: 获取BTC价格数据...")
        data, info = fetch_btc_data(days=365)
        
        print(f"\n交易对信息:")
        for key, value in info.items():
            print(f"  {key}: {value}")
        
        # 2. 计算技术指标
        print("\n步骤2: 计算技术指标...")
        enhanced_data = add_technical_indicators(data, rsi_period=14)
        print(f"数据形状: {enhanced_data.shape}")
        print(f"数据列: {', '.join(enhanced_data.columns.tolist())}")
        
        # 3. 运行RSI策略回测
        print("\n步骤3: 运行RSI策略回测...")
        backtest_result = run_rsi_strategy(
            data=enhanced_data,
            rsi_period=14,
            rsi_buy_threshold=20.0,
            rsi_sell_threshold=60.0,
            initial_capital=10000.0,
            fee_rate=0.001
        )
        
        # 4. 打印详细结果
        from strategy import RSIStrategy
        strategy = RSIStrategy()
        strategy.print_detailed_results(backtest_result)
        
        # 5. 保存结果到文件
        print("\n步骤4: 保存结果到文件...")
        save_results(backtest_result, enhanced_data)
        
        print("\n" + "="*80)
        print("回测完成！")
        print("="*80)
        
    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


def save_results(backtest_result: dict, data: pd.DataFrame):
    """
    保存回测结果到文件
    
    Args:
        backtest_result: 回测结果字典
        data: 价格数据
    """
    try:
        result = backtest_result['result']
        
        # 保存交易记录
        trades_df = pd.DataFrame([
            {
                '日期': trade.timestamp.date(),
                '类型': trade.type,
                '价格': trade.price,
                '数量': trade.quantity,
                '价值': trade.value,
                '手续费': trade.fee,
                '现金余额': trade.cash_after,
                '持仓数量': trade.position_after,
                '总价值': trade.total_value_after
            }
            for trade in result.trades
        ])
        
        if not trades_df.empty:
            trades_df.to_csv('trades.csv', index=False, encoding='utf-8-sig')
            print(f"  交易记录已保存到: trades.csv ({len(trades_df)} 笔交易)")
        
        # 保存权益曲线
        equity_df = pd.DataFrame({
            '日期': result.equity_curve.index.date,
            '权益价值': result.equity_curve.values
        })
        equity_df.to_csv('equity_curve.csv', index=False, encoding='utf-8-sig')
        print(f"  权益曲线已保存到: equity_curve.csv ({len(equity_df)} 个数据点)")
        
        # 保存性能摘要
        summary = {
            '初始资金': result.initial_capital,
            '最终资金': result.final_capital,
            '总收益率': result.total_return,
            '年化收益率': result.annual_return,
            '最大回撤': result.max_drawdown,
            '夏普比率': result.sharpe_ratio,
            '总交易次数': result.total_trades,
            '盈利交易': result.winning_trades,
            '亏损交易': result.losing_trades,
            '胜率': result.win_rate,
            '平均每笔交易利润': result.avg_profit_per_trade,
            '数据开始日期': data.index[0].date(),
            '数据结束日期': data.index[-1].date(),
            '数据天数': len(data)
        }
        
        summary_df = pd.DataFrame([summary])
        summary_df.to_csv('performance_summary.csv', index=False, encoding='utf-8-sig')
        print(f"  性能摘要已保存到: performance_summary.csv")
        
    except Exception as e:
        print(f"保存结果失败: {e}")


if __name__ == "__main__":
    main()
