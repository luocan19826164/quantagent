"""
回测引擎模块
处理交易逻辑、资金管理和性能计算
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime


@dataclass
class Trade:
    """交易记录"""
    timestamp: pd.Timestamp
    type: str  # 'buy' 或 'sell'
    price: float
    quantity: float
    value: float
    fee: float
    cash_after: float
    position_after: float
    total_value_after: float


@dataclass
class BacktestResult:
    """回测结果"""
    initial_capital: float
    final_capital: float
    total_return: float
    annual_return: float
    max_drawdown: float
    sharpe_ratio: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_profit_per_trade: float
    trades: List[Trade]
    equity_curve: pd.Series
    drawdown_curve: pd.Series


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 10000.0, fee_rate: float = 0.001):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金（美元）
            fee_rate: 手续费率（每笔交易）
        """
        self.initial_capital = initial_capital
        self.fee_rate = fee_rate
        
        # 状态变量
        self.cash = initial_capital
        self.position = 0.0  # BTC数量
        self.trades: List[Trade] = []
        self.equity_values: List[float] = []
        self.dates: List[pd.Timestamp] = []
        
    def execute_buy(self, timestamp: pd.Timestamp, price: float) -> bool:
        """
        执行买入操作
        
        Args:
            timestamp: 交易时间
            price: 买入价格
            
        Returns:
            是否成功执行
        """
        if self.cash <= 0:
            return False
        
        # 计算可买入数量（全仓买入）
        quantity = self.cash / price
        value = quantity * price
        fee = value * self.fee_rate
        
        # 检查是否有足够资金支付手续费
        if value + fee > self.cash:
            # 调整数量以确保有足够资金支付手续费
            quantity = self.cash / (price * (1 + self.fee_rate))
            value = quantity * price
            fee = value * self.fee_rate
        
        # 更新状态
        self.position += quantity
        self.cash -= (value + fee)
        
        # 记录交易
        total_value = self.cash + self.position * price
        trade = Trade(
            timestamp=timestamp,
            type='buy',
            price=price,
            quantity=quantity,
            value=value,
            fee=fee,
            cash_after=self.cash,
            position_after=self.position,
            total_value_after=total_value
        )
        self.trades.append(trade)
        
        return True
    
    def execute_sell(self, timestamp: pd.Timestamp, price: float) -> bool:
        """
        执行卖出操作
        
        Args:
            timestamp: 交易时间
            price: 卖出价格
            
        Returns:
            是否成功执行
        """
        if self.position <= 0:
            return False
        
        # 计算卖出价值
        value = self.position * price
        fee = value * self.fee_rate
        
        # 更新状态
        self.cash += (value - fee)
        self.position = 0.0
        
        # 记录交易
        total_value = self.cash
        trade = Trade(
            timestamp=timestamp,
            type='sell',
            price=price,
            quantity=self.position,
            value=value,
            fee=fee,
            cash_after=self.cash,
            position_after=self.position,
            total_value_after=total_value
        )
        self.trades.append(trade)
        
        return True
    
    def record_equity(self, timestamp: pd.Timestamp, price: float):
        """
        记录当前权益价值
        
        Args:
            timestamp: 时间戳
            price: 当前价格
        """
        equity = self.cash + self.position * price
        self.equity_values.append(equity)
        self.dates.append(timestamp)
    
    def calculate_performance(self) -> BacktestResult:
        """
        计算回测性能指标
        
        Returns:
            回测结果对象
        """
        if not self.equity_values:
            raise ValueError("没有权益数据，请先运行回测")
        
        # 创建权益曲线
        equity_series = pd.Series(self.equity_values, index=self.dates)
        
        # 计算总收益率
        final_capital = self.equity_values[-1]
        total_return = (final_capital - self.initial_capital) / self.initial_capital
        
        # 计算年化收益率
        days = (self.dates[-1] - self.dates[0]).days
        if days > 0:
            annual_return = (1 + total_return) ** (365 / days) - 1
        else:
            annual_return = 0.0
        
        # 计算最大回撤
        rolling_max = equity_series.expanding().max()
        drawdown = (equity_series - rolling_max) / rolling_max
        max_drawdown = drawdown.min()
        
        # 计算夏普比率（假设无风险利率为0）
        daily_returns = equity_series.pct_change().dropna()
        if len(daily_returns) > 0 and daily_returns.std() > 0:
            sharpe_ratio = (daily_returns.mean() / daily_returns.std()) * np.sqrt(252)
        else:
            sharpe_ratio = 0.0
        
        # 计算交易统计
        total_trades = len(self.trades)
        winning_trades = 0
        losing_trades = 0
        total_profit = 0.0
        
        # 分析每笔交易的盈亏
        for i in range(0, len(self.trades) - 1, 2):
            if i + 1 < len(self.trades):
                buy_trade = self.trades[i]
                sell_trade = self.trades[i + 1]
                if buy_trade.type == 'buy' and sell_trade.type == 'sell':
                    profit = sell_trade.value - buy_trade.value - buy_trade.fee - sell_trade.fee
                    total_profit += profit
                    if profit > 0:
                        winning_trades += 1
                    else:
                        losing_trades += 1
        
        win_rate = winning_trades / (winning_trades + losing_trades) if (winning_trades + losing_trades) > 0 else 0.0
        avg_profit_per_trade = total_profit / total_trades if total_trades > 0 else 0.0
        
        return BacktestResult(
            initial_capital=self.initial_capital,
            final_capital=final_capital,
            total_return=total_return,
            annual_return=annual_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_profit_per_trade=avg_profit_per_trade,
            trades=self.trades,
            equity_curve=equity_series,
            drawdown_curve=drawdown
        )
    
    def print_results(self, result: BacktestResult):
        """打印回测结果"""
        print("\n" + "="*60)
        print("回测结果")
        print("="*60)
        
        print(f"初始资金: ${result.initial_capital:,.2f}")
        print(f"最终资金: ${result.final_capital:,.2f}")
        print(f"总收益率: {result.total_return:.2%}")
        print(f"年化收益率: {result.annual_return:.2%}")
        print(f"最大回撤: {result.max_drawdown:.2%}")
        print(f"夏普比率: {result.sharpe_ratio:.2f}")
        print(f"总交易次数: {result.total_trades}")
        print(f"盈利交易: {result.winning_trades}")
        print(f"亏损交易: {result.losing_trades}")
        print(f"胜率: {result.win_rate:.2%}")
        print(f"平均每笔交易利润: ${result.avg_profit_per_trade:.2f}")
        
        print("\n" + "-"*60)
        print("交易记录")
        print("-"*60)
        
        for i, trade in enumerate(result.trades):
            print(f"{i+1:3d}. {trade.timestamp.date()} {trade.type.upper():4s} "
                  f"价格: ${trade.price:,.2f} 数量: {trade.quantity:.6f} "
                  f"价值: ${trade.value:,.2f} 手续费: ${trade.fee:.2f}")
        
        print("="*60)


if __name__ == "__main__":
    # 测试回测引擎
    print("测试回测引擎...")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    prices = pd.Series(np.linspace(100, 200, 100), index=dates)
    
    # 创建回测引擎
    engine = BacktestEngine(initial_capital=10000.0, fee_rate=0.001)
    
    # 模拟一些交易
    engine.execute_buy(dates[10], prices.iloc[10])
    engine.record_equity(dates[10], prices.iloc[10])
    
    engine.execute_sell(dates[50], prices.iloc[50])
    engine.record_equity(dates[50], prices.iloc[50])
    
    engine.execute_buy(dates[60], prices.iloc[60])
    engine.record_equity(dates[60], prices.iloc[60])
    
    engine.execute_sell(dates[90], prices.iloc[90])
    engine.record_equity(dates[90], prices.iloc[90])
    
    # 计算性能
    result = engine.calculate_performance()
    engine.print_results(result)