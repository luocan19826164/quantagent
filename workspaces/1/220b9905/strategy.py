"""
策略模块
实现RSI策略逻辑
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, Optional
from dataclasses import dataclass
from backtest import BacktestEngine


@dataclass
class StrategyConfig:
    """策略配置"""
    rsi_period: int = 14
    rsi_buy_threshold: float = 20.0
    rsi_sell_threshold: float = 60.0
    initial_capital: float = 10000.0
    fee_rate: float = 0.001


class RSIStrategy:
    """RSI策略"""
    
    def __init__(self, config: Optional[StrategyConfig] = None):
        """
        初始化RSI策略
        
        Args:
            config: 策略配置，如果为None则使用默认配置
        """
        self.config = config or StrategyConfig()
        self.engine = BacktestEngine(
            initial_capital=self.config.initial_capital,
            fee_rate=self.config.fee_rate
        )
        
        # 策略状态
        self.in_position = False  # 是否持有仓位
        self.buy_price = 0.0  # 买入价格
        
    def run_backtest(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            data: 价格数据DataFrame，必须包含'Close'和'RSI'列
            
        Returns:
            包含回测结果的字典
        """
        if 'Close' not in data.columns:
            raise ValueError("数据必须包含'Close'列")
        
        if 'RSI' not in data.columns:
            raise ValueError("数据必须包含'RSI'列，请先计算RSI指标")
        
        print(f"开始运行RSI策略回测...")
        print(f"策略配置:")
        print(f"  RSI周期: {self.config.rsi_period}")
        print(f"  买入阈值: RSI < {self.config.rsi_buy_threshold}")
        print(f"  卖出阈值: RSI > {self.config.rsi_sell_threshold}")
        print(f"  初始资金: ${self.config.initial_capital:,.2f}")
        print(f"  手续费率: {self.config.fee_rate:.3%}")
        
        # 重置策略状态
        self.in_position = False
        self.buy_price = 0.0
        
        # 遍历每一天的数据
        for i in range(len(data)):
            date = data.index[i]
            price = data['Close'].iloc[i]
            rsi = data['RSI'].iloc[i]
            
            # 跳过RSI为NaN的日期（前period-1天）
            if pd.isna(rsi):
                self.engine.record_equity(date, price)
                continue
            
            # 记录当前权益
            self.engine.record_equity(date, price)
            
            # 策略逻辑
            if not self.in_position:
                # 未持仓：检查买入条件
                if rsi < self.config.rsi_buy_threshold:
                    if self.engine.execute_buy(date, price):
                        self.in_position = True
                        self.buy_price = price
                        print(f"{date.date()}: RSI={rsi:.2f} < {self.config.rsi_buy_threshold}, 买入 @ ${price:,.2f}")
            
            else:
                # 已持仓：检查卖出条件
                if rsi > self.config.rsi_sell_threshold:
                    if self.engine.execute_sell(date, price):
                        self.in_position = False
                        profit = price - self.buy_price
                        profit_pct = (profit / self.buy_price) * 100
                        print(f"{date.date()}: RSI={rsi:.2f} > {self.config.rsi_sell_threshold}, 卖出 @ ${price:,.2f}")
                        print(f"  本次交易利润: ${profit:,.2f} ({profit_pct:.2f}%)")
                        self.buy_price = 0.0
        
        # 如果回测结束时仍持有仓位，强制平仓
        if self.in_position:
            last_date = data.index[-1]
            last_price = data['Close'].iloc[-1]
            if self.engine.execute_sell(last_date, last_price):
                profit = last_price - self.buy_price
                profit_pct = (profit / self.buy_price) * 100
                print(f"{last_date.date()}: 回测结束，强制平仓 @ ${last_price:,.2f}")
                print(f"  本次交易利润: ${profit:,.2f} ({profit_pct:.2f}%)")
        
        # 计算性能指标
        result = self.engine.calculate_performance()
        
        return {
            'result': result,
            'config': self.config,
            'engine': self.engine
        }
    
    def print_detailed_results(self, backtest_result: Dict[str, Any]):
        """打印详细回测结果"""
        result = backtest_result['result']
        config = backtest_result['config']
        
        print("\n" + "="*80)
        print("RSI策略详细回测结果")
        print("="*80)
        
        # 基本配置
        print("策略配置:")
        print(f"  RSI周期: {config.rsi_period}")
        print(f"  买入阈值: RSI < {config.rsi_buy_threshold}")
        print(f"  卖出阈值: RSI > {config.rsi_sell_threshold}")
        print(f"  初始资金: ${config.initial_capital:,.2f}")
        print(f"  手续费率: {config.fee_rate:.3%}")
        
        # 性能指标
        print("\n性能指标:")
        print(f"  初始资金: ${result.initial_capital:,.2f}")
        print(f"  最终资金: ${result.final_capital:,.2f}")
        print(f"  总收益率: {result.total_return:.2%}")
        print(f"  年化收益率: {result.annual_return:.2%}")
        print(f"  最大回撤: {result.max_drawdown:.2%}")
        print(f"  夏普比率: {result.sharpe_ratio:.2f}")
        print(f"  总交易次数: {result.total_trades}")
        print(f"  盈利交易: {result.winning_trades}")
        print(f"  亏损交易: {result.losing_trades}")
        print(f"  胜率: {result.win_rate:.2%}")
        print(f"  平均每笔交易利润: ${result.avg_profit_per_trade:.2f}")
        
        # 交易统计
        if result.trades:
            print("\n交易统计:")
            buy_trades = [t for t in result.trades if t.type == 'buy']
            sell_trades = [t for t in result.trades if t.type == 'sell']
            
            if buy_trades and sell_trades:
                avg_buy_price = np.mean([t.price for t in buy_trades])
                avg_sell_price = np.mean([t.price for t in sell_trades])
                avg_hold_days = []
                
                for i in range(0, len(result.trades) - 1, 2):
                    if i + 1 < len(result.trades):
                        buy_trade = result.trades[i]
                        sell_trade = result.trades[i + 1]
                        if buy_trade.type == 'buy' and sell_trade.type == 'sell':
                            hold_days = (sell_trade.timestamp - buy_trade.timestamp).days
                            avg_hold_days.append(hold_days)
                
                if avg_hold_days:
                    avg_hold_days_val = np.mean(avg_hold_days)
                    print(f"  平均买入价格: ${avg_buy_price:,.2f}")
                    print(f"  平均卖出价格: ${avg_sell_price:,.2f}")
                    print(f"  平均持仓天数: {avg_hold_days_val:.1f}天")
        
        # 交易记录
        print("\n" + "-"*80)
        print("交易记录")
        print("-"*80)
        
        if not result.trades:
            print("  无交易记录")
        else:
            for i, trade in enumerate(result.trades):
                trade_type = "买入" if trade.type == 'buy' else "卖出"
                print(f"{i+1:3d}. {trade.timestamp.date()} {trade_type:4s} "
                      f"价格: ${trade.price:,.2f} 数量: {trade.quantity:.6f} "
                      f"价值: ${trade.value:,.2f} 手续费: ${trade.fee:.2f}")
        
        print("="*80)


def run_rsi_strategy(
    data: pd.DataFrame,
    rsi_period: int = 14,
    rsi_buy_threshold: float = 20.0,
    rsi_sell_threshold: float = 60.0,
    initial_capital: float = 10000.0,
    fee_rate: float = 0.001
) -> Dict[str, Any]:
    """
    运行RSI策略的便捷函数
    
    Args:
        data: 价格数据DataFrame，必须包含'Close'和'RSI'列
        rsi_period: RSI计算周期
        rsi_buy_threshold: RSI买入阈值
        rsi_sell_threshold: RSI卖出阈值
        initial_capital: 初始资金
        fee_rate: 手续费率
        
    Returns:
        包含回测结果的字典
    """
    config = StrategyConfig(
        rsi_period=rsi_period,
        rsi_buy_threshold=rsi_buy_threshold,
        rsi_sell_threshold=rsi_sell_threshold,
        initial_capital=initial_capital,
        fee_rate=fee_rate
    )
    
    strategy = RSIStrategy(config)
    return strategy.run_backtest(data)


if __name__ == "__main__":
    # 测试策略
    print("测试RSI策略...")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=200, freq='D')
    np.random.seed(42)
    prices = pd.Series(np.random.randn(200).cumsum() * 100 + 30000, index=dates)
    
    # 计算RSI（模拟）
    from indicators import calculate_rsi
    rsi = calculate_rsi(prices, period=14)
    
    # 创建测试数据
    test_data = pd.DataFrame({
        'Close': prices,
        'RSI': rsi
    })
    
    # 运行策略
    result = run_rsi_strategy(
        data=test_data,
        rsi_period=14,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0,
        initial_capital=10000.0,
        fee_rate=0.001
    )
    
    # 打印结果
    strategy = RSIStrategy()
    strategy.print_detailed_results(result)