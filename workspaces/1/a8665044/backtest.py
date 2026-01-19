"""
回测引擎模块
实现基于RSI策略的回测系统
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Optional, Tuple
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Trade:
    """交易记录类"""
    
    def __init__(self, trade_type: str, timestamp: pd.Timestamp, price: float, 
                 quantity: float = 1.0, cash_balance: float = 0.0, 
                 position: float = 0.0, rsi_value: Optional[float] = None):
        """
        初始化交易记录
        
        Args:
            trade_type: 交易类型 ('buy' 或 'sell')
            timestamp: 交易时间
            price: 交易价格
            quantity: 交易数量
            cash_balance: 交易后的现金余额
            position: 交易后的持仓数量
            rsi_value: 交易时的RSI值
        """
        self.trade_type = trade_type
        self.timestamp = timestamp
        self.price = price
        self.quantity = quantity
        self.cash_balance = cash_balance
        self.position = position
        self.rsi_value = rsi_value
        
        # 计算交易金额
        self.amount = price * quantity
        if trade_type == 'buy':
            self.amount = -self.amount  # 买入为负支出
        
    def __repr__(self) -> str:
        rsi_str = f"{self.rsi_value:.2f}" if self.rsi_value is not None else "N/A"
        return (f"Trade(type={self.trade_type}, time={self.timestamp.strftime('%Y-%m-%d')}, "
                f"price=${self.price:,.2f}, quantity={self.quantity:.4f}, "
                f"amount=${self.amount:,.2f}, cash=${self.cash_balance:,.2f}, "
                f"position={self.position:.4f}, RSI={rsi_str})")


class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, initial_capital: float = 10000.0, commission_rate: float = 0.001):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            commission_rate: 交易佣金率（默认0.1%）
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        
        # 回测状态
        self.cash = initial_capital
        self.position = 0.0  # 持仓数量
        self.trades: List[Trade] = []  # 交易记录
        self.equity_curve = []  # 权益曲线
        self.timestamps = []  # 时间戳
        
        # 状态标志
        self.in_position = False  # 是否持仓
        self.buy_price = 0.0  # 买入价格
        
    def reset(self) -> None:
        """重置回测状态"""
        self.cash = self.initial_capital
        self.position = 0.0
        self.trades = []
        self.equity_curve = []
        self.timestamps = []
        self.in_position = False
        self.buy_price = 0.0
        
    def calculate_commission(self, amount: float) -> float:
        """
        计算交易佣金
        
        Args:
            amount: 交易金额（绝对值）
            
        Returns:
            佣金金额
        """
        return abs(amount) * self.commission_rate
    
    def buy(self, timestamp: pd.Timestamp, price: float, rsi_value: Optional[float] = None) -> bool:
        """
        执行买入操作
        
        Args:
            timestamp: 买入时间
            price: 买入价格
            rsi_value: 买入时的RSI值
            
        Returns:
            是否成功买入
        """
        if self.in_position:
            logger.warning(f"已在持仓中，无法买入 (时间: {timestamp})")
            return False
        
        # 计算可买入的最大数量（考虑佣金）
        max_quantity = self.cash / (price * (1 + self.commission_rate))
        
        if max_quantity <= 0:
            logger.warning(f"资金不足，无法买入 (现金: ${self.cash:,.2f}, 价格: ${price:,.2f})")
            return False
        
        # 使用全部资金买入
        quantity = max_quantity
        amount = price * quantity
        commission = self.calculate_commission(amount)
        
        # 更新状态
        self.position = quantity
        self.cash -= (amount + commission)
        self.in_position = True
        self.buy_price = price
        
        # 记录交易
        trade = Trade(
            trade_type='buy',
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            cash_balance=self.cash,
            position=self.position,
            rsi_value=rsi_value
        )
        self.trades.append(trade)
        
        logger.info(f"买入: {trade}")
        return True
    
    def sell(self, timestamp: pd.Timestamp, price: float, rsi_value: Optional[float] = None) -> bool:
        """
        执行卖出操作
        
        Args:
            timestamp: 卖出时间
            price: 卖出价格
            rsi_value: 卖出时的RSI值
            
        Returns:
            是否成功卖出
        """
        if not self.in_position or self.position <= 0:
            logger.warning(f"未持仓，无法卖出 (时间: {timestamp})")
            return False
        
        # 计算卖出金额
        amount = price * self.position
        commission = self.calculate_commission(amount)
        
        # 更新状态
        self.cash += (amount - commission)
        quantity = self.position  # 记录卖出的数量
        self.position = 0.0
        self.in_position = False
        
        # 记录交易
        trade = Trade(
            trade_type='sell',
            timestamp=timestamp,
            price=price,
            quantity=quantity,
            cash_balance=self.cash,
            position=self.position,
            rsi_value=rsi_value
        )
        self.trades.append(trade)
        
        logger.info(f"卖出: {trade}")
        return True
    
    def calculate_portfolio_value(self, current_price: float) -> float:
        """
        计算当前投资组合价值
        
        Args:
            current_price: 当前价格
            
        Returns:
            投资组合总价值
        """
        position_value = self.position * current_price
        return self.cash + position_value
    
    def run_rsi_strategy(self, data: pd.DataFrame, rsi_column: str = 'RSI', 
                        price_column: str = 'Close', oversold_threshold: float = 20.0,
                        overbought_threshold: float = 60.0) -> pd.DataFrame:
        """
        运行RSI策略回测
        
        策略规则:
        1. 当RSI < oversold_threshold 且未持仓时买入
        2. 买入后，当RSI > overbought_threshold 时卖出
        
        Args:
            data: 包含价格和RSI数据的DataFrame
            rsi_column: RSI列名
            price_column: 价格列名
            oversold_threshold: 超卖阈值（买入信号）
            overbought_threshold: 超买阈值（卖出信号）
            
        Returns:
            添加了回测结果的DataFrame
        """
        logger.info(f"开始RSI策略回测")
        logger.info(f"策略参数: RSI<{oversold_threshold}买入, RSI>{overbought_threshold}卖出")
        logger.info(f"初始资金: ${self.initial_capital:,.2f}")
        
        # 重置回测状态
        self.reset()
        
        # 确保数据按时间排序
        data = data.sort_index()
        
        # 添加回测结果列
        result_data = data.copy()
        result_data['Position'] = 0.0
        result_data['Cash'] = self.initial_capital
        result_data['Portfolio_Value'] = self.initial_capital
        result_data['Trade_Signal'] = 'hold'
        
        # 遍历数据
        for i in range(len(data)):
            timestamp = data.index[i]
            price = data[price_column].iloc[i]
            rsi_value = data[rsi_column].iloc[i] if rsi_column in data.columns else None
            
            # 跳过RSI为NaN的数据点
            if pd.isna(rsi_value):
                # 更新权益曲线
                portfolio_value = self.calculate_portfolio_value(price)
                self.equity_curve.append(portfolio_value)
                self.timestamps.append(timestamp)
                
                # 更新结果数据
                result_data.loc[timestamp, 'Position'] = self.position
                result_data.loc[timestamp, 'Cash'] = self.cash
                result_data.loc[timestamp, 'Portfolio_Value'] = portfolio_value
                continue
            
            # 策略逻辑
            trade_signal = 'hold'
            
            if not self.in_position:
                # 未持仓：检查买入信号
                if rsi_value < oversold_threshold:
                    if self.buy(timestamp, price, rsi_value):
                        trade_signal = 'buy'
            else:
                # 已持仓：检查卖出信号
                if rsi_value > overbought_threshold:
                    if self.sell(timestamp, price, rsi_value):
                        trade_signal = 'sell'
            
            # 更新权益曲线
            portfolio_value = self.calculate_portfolio_value(price)
            self.equity_curve.append(portfolio_value)
            self.timestamps.append(timestamp)
            
            # 更新结果数据
            result_data.loc[timestamp, 'Position'] = self.position
            result_data.loc[timestamp, 'Cash'] = self.cash
            result_data.loc[timestamp, 'Portfolio_Value'] = portfolio_value
            result_data.loc[timestamp, 'Trade_Signal'] = trade_signal
        
        # 处理回测结束时的持仓
        if self.in_position:
            last_timestamp = data.index[-1]
            last_price = data[price_column].iloc[-1]
            last_rsi = data[rsi_column].iloc[-1] if rsi_column in data.columns else None
            
            logger.info(f"回测结束，强制平仓")
            self.sell(last_timestamp, last_price, last_rsi)
        
        # 计算回测统计
        self.calculate_backtest_statistics(result_data)
        
        return result_data
    
    def calculate_backtest_statistics(self, data: pd.DataFrame) -> Dict:
        """
        计算回测统计信息
        
        Args:
            data: 回测结果数据
            
        Returns:
            回测统计信息字典
        """
        # 计算总收益率
        final_value = self.cash
        total_return = ((final_value - self.initial_capital) / self.initial_capital) * 100
        
        if len(self.trades) == 0:
            logger.warning("没有交易记录，无法计算详细统计信息")
            # 返回基本统计信息
            portfolio_values = data['Portfolio_Value'].dropna()
            if len(portfolio_values) > 0:
                peak = portfolio_values.expanding().max()
                drawdown = (portfolio_values - peak) / peak * 100
                max_drawdown = drawdown.min()
            else:
                max_drawdown = 0
            
            stats = {
                'initial_capital': self.initial_capital,
                'final_value': final_value,
                'total_return_pct': total_return,
                'total_return_abs': final_value - self.initial_capital,
                'total_trades': 0,
                'buy_trades': 0,
                'sell_trades': 0,
                'win_rate_pct': 0.0,
                'winning_trades': 0,
                'losing_trades': 0,
                'avg_trade_return_pct': 0.0,
                'max_drawdown_pct': max_drawdown,
                'sharpe_ratio': 0.0,
                'trade_results': []
            }
            
            # 打印基本统计信息
            logger.info(f"\n回测统计结果:")
            logger.info(f"=" * 50)
            logger.info(f"初始资金: ${stats['initial_capital']:,.2f}")
            logger.info(f"最终价值: ${stats['final_value']:,.2f}")
            logger.info(f"总收益率: {stats['total_return_pct']:.2f}%")
            logger.info(f"总交易次数: {stats['total_trades']} 次")
            logger.info(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
            
            return stats
        
        # 计算交易统计
        buy_trades = [t for t in self.trades if t.trade_type == 'buy']
        sell_trades = [t for t in self.trades if t.trade_type == 'sell']
        
        # 计算每笔交易的收益
        trade_results = []
        for i in range(min(len(buy_trades), len(sell_trades))):
            buy_trade = buy_trades[i]
            sell_trade = sell_trades[i]
            
            buy_amount = buy_trade.price * buy_trade.quantity
            sell_amount = sell_trade.price * sell_trade.quantity
            
            # 计算收益率（考虑佣金）
            commission = self.calculate_commission(buy_amount) + self.calculate_commission(sell_amount)
            profit = sell_amount - buy_amount - commission
            return_rate = (profit / buy_amount) * 100
            
            trade_results.append({
                'buy_date': buy_trade.timestamp,
                'sell_date': sell_trade.timestamp,
                'buy_price': buy_trade.price,
                'sell_price': sell_trade.price,
                'quantity': buy_trade.quantity,
                'profit': profit,
                'return_rate': return_rate,
                'holding_days': (sell_trade.timestamp - buy_trade.timestamp).days
            })
        
        # 计算胜率
        winning_trades = [t for t in trade_results if t['profit'] > 0]
        win_rate = (len(winning_trades) / len(trade_results) * 100) if trade_results else 0
        
        # 计算最大回撤
        portfolio_values = data['Portfolio_Value'].dropna()
        if len(portfolio_values) > 0:
            peak = portfolio_values.expanding().max()
            drawdown = (portfolio_values - peak) / peak * 100
            max_drawdown = drawdown.min()
        else:
            max_drawdown = 0
        
        # 计算夏普比率（简化版，假设无风险利率为0）
        returns = portfolio_values.pct_change().dropna()
        if len(returns) > 0:
            sharpe_ratio = returns.mean() / returns.std() * np.sqrt(252) if returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        stats = {
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return_pct': total_return,
            'total_return_abs': final_value - self.initial_capital,
            'total_trades': len(self.trades),
            'buy_trades': len(buy_trades),
            'sell_trades': len(sell_trades),
            'win_rate_pct': win_rate,
            'winning_trades': len(winning_trades),
            'losing_trades': len(trade_results) - len(winning_trades),
            'avg_trade_return_pct': np.mean([t['return_rate'] for t in trade_results]) if trade_results else 0,
            'max_drawdown_pct': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'trade_results': trade_results
        }
        
        # 打印统计信息
        logger.info(f"\n回测统计结果:")
        logger.info(f"=" * 50)
        logger.info(f"初始资金: ${stats['initial_capital']:,.2f}")
        logger.info(f"最终价值: ${stats['final_value']:,.2f}")
        logger.info(f"总收益率: {stats['total_return_pct']:.2f}%")
        logger.info(f"总交易次数: {stats['total_trades']} 次")
        logger.info(f"胜率: {stats['win_rate_pct']:.1f}% ({stats['winning_trades']}胜/{stats['losing_trades']}负)")
        logger.info(f"平均每笔交易收益率: {stats['avg_trade_return_pct']:.2f}%")
        logger.info(f"最大回撤: {stats['max_drawdown_pct']:.2f}%")
        logger.info(f"夏普比率: {stats['sharpe_ratio']:.2f}")
        
        return stats
    
    def get_trade_summary(self) -> pd.DataFrame:
        """
        获取交易摘要
        
        Returns:
            交易摘要DataFrame
        """
        if not self.trades:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.trades:
            trades_data.append({
                'timestamp': trade.timestamp,
                'type': trade.trade_type,
                'price': trade.price,
                'quantity': trade.quantity,
                'amount': trade.amount,
                'cash_balance': trade.cash_balance,
                'position': trade.position,
                'rsi_value': trade.rsi_value
            })
        
        return pd.DataFrame(trades_data)


def run_rsi_backtest(data: pd.DataFrame, initial_capital: float = 10000.0,
                    rsi_column: str = 'RSI', price_column: str = 'Close',
                    oversold_threshold: float = 20.0, overbought_threshold: float = 60.0,
                    commission_rate: float = 0.001) -> Tuple[pd.DataFrame, Dict, BacktestEngine]:
    """
    运行RSI策略回测的便捷函数
    
    Args:
        data: 包含价格和RSI数据的DataFrame
        initial_capital: 初始资金
        rsi_column: RSI列名
        price_column: 价格列名
        oversold_threshold: 超卖阈值
        overbought_threshold: 超买阈值
        commission_rate: 交易佣金率
        
    Returns:
        (回测结果DataFrame, 统计信息字典, 回测引擎实例)
    """
    # 创建回测引擎
    engine = BacktestEngine(initial_capital=initial_capital, commission_rate=commission_rate)
    
    # 运行策略
    result_data = engine.run_rsi_strategy(
        data=data,
        rsi_column=rsi_column,
        price_column=price_column,
        oversold_threshold=oversold_threshold,
        overbought_threshold=overbought_threshold
    )
    
    # 获取统计信息
    stats = engine.calculate_backtest_statistics(result_data)
    
    return result_data, stats, engine


if __name__ == "__main__":
    # 测试回测引擎
    print("测试回测引擎")
    print("=" * 50)
    
    # 创建示例数据
    np.random.seed(42)
    n = 100
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 创建价格数据
    prices = []
    current_price = 100
    for i in range(n):
        # 模拟价格波动
        change = np.random.normal(0, 0.02)
        current_price *= (1 + change)
        prices.append(current_price)
    
    # 创建RSI数据（模拟）
    rsi_values = []
    for i in range(n):
        # 模拟RSI在30-70之间波动，偶尔出现超买超卖
        base_rsi = 50 + np.random.normal(0, 15)
        # 确保在0-100范围内
        rsi = max(0, min(100, base_rsi))
        rsi_values.append(rsi)
    
    # 创建DataFrame
    data = pd.DataFrame({
        'Close': prices,
        'RSI': rsi_values
    }, index=dates)
    
    print(f"测试数据形状: {data.shape}")
    print(f"价格范围: ${data['Close'].min():.2f} - ${data['Close'].max():.2f}")
    print(f"RSI范围: {data['RSI'].min():.2f} - {data['RSI'].max():.2f}")
    
    # 运行回测
    print("\n运行RSI策略回测...")
    result_data, stats, engine = run_rsi_backtest(
        data=data,
        initial_capital=10000.0,
        oversold_threshold=20.0,
        overbought_threshold=60.0
    )
    
    # 显示结果
    print(f"\n回测完成!")
    print(f"最终投资组合价值: ${stats['final_value']:,.2f}")
    print(f"总收益率: {stats['total_return_pct']:.2f}%")
    print(f"交易次数: {stats['total_trades']} 次")
    
    # 显示交易记录
    trades_df = engine.get_trade_summary()
    if not trades_df.empty:
        print(f"\n交易记录:")
        print(trades_df.to_string())
    
    # 显示权益曲线
    print(f"\n权益曲线前5个值:")
    print(result_data[['Close', 'RSI', 'Portfolio_Value', 'Trade_Signal']].head())
    
    print(f"\n✓ 回测引擎测试完成!")