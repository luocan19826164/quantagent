"""
量化策略主程序
"""

import pandas as pd
import numpy as np
from data_fetcher import fetch_bitcoin_data
from indicators import add_rsi_to_dataframe, TechnicalIndicators
from backtest import run_rsi_backtest


def main():
    print("比特币RSI策略回测系统")
    print("=" * 50)
    
    # 步骤1: 获取比特币数据
    print("\n步骤1: 获取比特币最近一年的历史数据...")
    
    try:
        # 获取最近一年的日线数据
        data, info = fetch_bitcoin_data(period="1y", interval="1d")
        
        print(f"✓ 数据获取成功!")
        print(f"   时间范围: {info['start_date']} 到 {info['end_date']}")
        print(f"   总数据点: {len(data)} 个")
        print(f"   价格范围: ${info['price_range']['min']:,.2f} - ${info['price_range']['max']:,.2f}")
        print(f"   当前价格: ${info['price_range']['current']:,.2f}")
        print(f"   总收益率: {info['return_stats']['total_return']:.2f}%")
        
        # 显示数据基本信息
        print(f"\n数据列名: {list(data.columns)}")
        print(f"数据形状: {data.shape}")
        
        # 检查是否有缺失值
        missing_values = data.isnull().sum()
        if missing_values.any():
            print(f"\n警告: 数据中存在缺失值:")
            print(missing_values[missing_values > 0])
        else:
            print(f"\n✓ 数据完整，无缺失值")
        
        # 步骤2: 计算RSI指标
        print("\n步骤2: 计算RSI(14)指标...")
        
        try:
            # 计算RSI并添加到数据中
            data_with_rsi = add_rsi_to_dataframe(data, period=14)
            
            # 获取RSI统计信息
            rsi_stats = TechnicalIndicators.get_rsi_statistics(data_with_rsi['RSI'])
            
            print(f"✓ RSI计算成功!")
            print(f"   有效RSI数据点: {data_with_rsi['RSI'].notna().sum()} 个")
            print(f"   RSI均值: {rsi_stats.get('mean', 'N/A'):.2f}")
            print(f"   RSI范围: {rsi_stats.get('min', 'N/A'):.2f} - {rsi_stats.get('max', 'N/A'):.2f}")
            print(f"   超卖区域(<20): {rsi_stats.get('oversold_count', 'N/A')} 次 ({rsi_stats.get('oversold_percentage', 'N/A'):.1f}%)")
            print(f"   超买区域(>80): {rsi_stats.get('overbought_count', 'N/A')} 次 ({rsi_stats.get('overbought_percentage', 'N/A'):.1f}%)")
            
            # 显示RSI信号分布
            if 'RSI_signal' in data_with_rsi.columns:
                signal_counts = data_with_rsi['RSI_signal'].value_counts(dropna=False)
                print(f"\nRSI信号分布:")
                for signal, count in signal_counts.items():
                    percentage = count / len(data_with_rsi) * 100
                    print(f"   {signal}: {count} 次 ({percentage:.1f}%)")
            
            # 显示前几个RSI值
            print(f"\n前5个RSI值:")
            for i in range(min(5, len(data_with_rsi))):
                date = data_with_rsi.index[i].strftime('%Y-%m-%d')
                close_price = data_with_rsi['Close'].iloc[i]
                rsi_value = data_with_rsi['RSI'].iloc[i]
                signal = data_with_rsi['RSI_signal'].iloc[i] if 'RSI_signal' in data_with_rsi.columns else 'N/A'
                
                if pd.notna(rsi_value):
                    print(f"   {date}: 收盘价=${close_price:,.2f}, RSI={rsi_value:.2f}, 信号={signal}")
                else:
                    print(f"   {date}: 收盘价=${close_price:,.2f}, RSI=NaN (前{14-1}个数据点)")
            
            # 保存数据到变量供后续使用
            print("\n✓ 数据已准备好，可以用于后续的回测")
            
            # 步骤3: 运行回测
            print("\n步骤3: 运行RSI策略回测...")
            print("策略规则: RSI<20时买入，买入后RSI>60时卖出")
            
            try:
                # 运行回测
                result_data, stats, engine = run_rsi_backtest(
                    data=data_with_rsi,
                    initial_capital=10000.0,
                    rsi_column='RSI',
                    price_column='Close',
                    oversold_threshold=20.0,
                    overbought_threshold=60.0,
                    commission_rate=0.001
                )
                
                print(f"✓ 回测完成!")
                print(f"初始资金: ${stats['initial_capital']:,.2f}")
                print(f"最终价值: ${stats['final_value']:,.2f}")
                print(f"总收益率: {stats['total_return_pct']:.2f}%")
                print(f"交易次数: {stats['total_trades']} 次 ({stats['buy_trades']}买/{stats['sell_trades']}卖)")
                print(f"胜率: {stats['win_rate_pct']:.1f}% ({stats['winning_trades']}胜/{stats['losing_trades']}负)")
                print(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
                
                # 显示交易记录
                trades_df = engine.get_trade_summary()
                if not trades_df.empty:
                    print(f"\n交易记录摘要:")
                    print(f"=" * 60)
                    for idx, trade in enumerate(engine.trades, 1):
                        date_str = trade.timestamp.strftime('%Y-%m-%d')
                        rsi_str = f"RSI={trade.rsi_value:.2f}" if trade.rsi_value else "RSI=N/A"
                        print(f"{idx:2d}. {date_str}: {trade.trade_type.upper():4s} "
                              f"@ ${trade.price:,.2f}, 数量={trade.quantity:.4f}, "
                              f"金额=${trade.amount:,.2f}, {rsi_str}")
                else:
                    print("\n⚠️ 没有交易记录")
                
                # 保存回测结果
                result_data.to_csv("data/backtest_results.csv")
                print(f"\n✓ 回测结果已保存到: data/backtest_results.csv")
                
            except Exception as e:
                print(f"✗ 回测失败: {e}")
                import traceback
                traceback.print_exc()
            
            # 返回包含RSI的数据
            data = data_with_rsi
            
        except Exception as e:
            print(f"✗ RSI计算失败: {e}")
            return
        
    except Exception as e:
        print(f"✗ 数据获取失败: {e}")
        return


if __name__ == "__main__":
    main()
