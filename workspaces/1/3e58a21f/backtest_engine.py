"""
回测引擎模块
实现基于RSI信号的交易策略回测
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum


class TradeAction(Enum):
    """交易动作枚举"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class TradeRecord:
    """交易记录"""
    timestamp: pd.Timestamp
    action: TradeAction
    price: float
    quantity: float
    cash: float
    position: float
    portfolio_value: float
    rsi: Optional[float] = None
    reason: Optional[str] = None


class BacktestEngine:
    """回测引擎类"""
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        transaction_fee: float = 0.001,  # 0.1% 交易手续费
        slippage: float = 0.0005,  # 0.05% 滑点
        rsi_buy_threshold: float = 20.0,
        rsi_sell_threshold: float = 60.0,
        position_size: float = 1.0  # 每次买入的仓位比例（0-1）
    ):
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金
            transaction_fee: 交易手续费率
            slippage: 滑点率
            rsi_buy_threshold: RSI买入阈值
            rsi_sell_threshold: RSI卖出阈值
            position_size: 每次买入的仓位比例
        """
        self.initial_capital = initial_capital
        self.transaction_fee = transaction_fee
        self.slippage = slippage
        self.rsi_buy_threshold = rsi_buy_threshold
        self.rsi_sell_threshold = rsi_sell_threshold
        self.position_size = position_size
        
        # 回测状态
        self.cash = initial_capital
        self.position = 0.0  # 持仓数量
        self.trades: List[TradeRecord] = []
        self.portfolio_values: List[float] = []
        self.dates: List[pd.Timestamp] = []
        
    def generate_signals(self, data: pd.DataFrame, rsi_column: str = 'RSI_14') -> pd.DataFrame:
        """
        根据RSI生成交易信号
        
        策略逻辑：
        1. 当RSI < 20时，买入信号
        2. 买入后，当RSI > 60时，卖出信号
        3. 其他情况，持有
        
        Args:
            data: 包含价格和RSI的数据
            rsi_column: RSI列名
            
        Returns:
            pd.DataFrame: 添加了信号列的数据
        """
        if rsi_column not in data.columns:
            raise ValueError(f"数据中缺少RSI列: {rsi_column}")
        
        # 创建数据副本
        data_with_signals = data.copy()
        
        # 初始化信号列
        data_with_signals['signal'] = TradeAction.HOLD.value
        data_with_signals['position'] = 0.0  # 持仓状态：0表示空仓，1表示持仓
        
        # 生成信号
        in_position = False  # 是否持仓
        
        for i in range(len(data_with_signals)):
            current_rsi = data_with_signals.iloc[i][rsi_column]
            
            # 跳过NaN值
            if pd.isna(current_rsi):
                continue
            
            if not in_position:
                # 空仓状态：RSI < 20时买入
                if current_rsi < self.rsi_buy_threshold:
                    data_with_signals.iloc[i, data_with_signals.columns.get_loc('signal')] = TradeAction.BUY.value
                    data_with_signals.iloc[i, data_with_signals.columns.get_loc('position')] = 1.0
                    in_position = True
            else:
                # 持仓状态：RSI > 60时卖出
                if current_rsi > self.rsi_sell_threshold:
                    data_with_signals.iloc[i, data_with_signals.columns.get_loc('signal')] = TradeAction.SELL.value
                    data_with_signals.iloc[i, data_with_signals.columns.get_loc('position')] = 0.0
                    in_position = False
                else:
                    # 继续持仓
                    data_with_signals.iloc[i, data_with_signals.columns.get_loc('position')] = 1.0
        
        return data_with_signals
    
    def execute_trade(
        self,
        action: TradeAction,
        price: float,
        timestamp: pd.Timestamp,
        rsi: Optional[float] = None
    ) -> None:
        """
        执行交易
        
        Args:
            action: 交易动作
            price: 交易价格
            timestamp: 交易时间
            rsi: 当前的RSI值
        """
        # 考虑滑点
        if action == TradeAction.BUY:
            execution_price = price * (1 + self.slippage)
        else:  # SELL
            execution_price = price * (1 - self.slippage)
        
        if action == TradeAction.BUY:
            # 计算可买入的数量
            max_position_value = self.cash * self.position_size
            quantity = max_position_value / execution_price
            
            # 计算手续费
            fee = max_position_value * self.transaction_fee
            
            # 检查资金是否足够
            if self.cash >= (max_position_value + fee):
                # 更新持仓和资金
                self.position += quantity
                self.cash -= (max_position_value + fee)
                
                # 记录交易
                trade = TradeRecord(
                    timestamp=timestamp,
                    action=action,
                    price=execution_price,
                    quantity=quantity,
                    cash=self.cash,
                    position=self.position,
                    portfolio_value=self.cash + self.position * execution_price,
                    rsi=rsi,
                    reason=f"RSI={rsi:.2f} < {self.rsi_buy_threshold}"
                )
                self.trades.append(trade)
                
        elif action == TradeAction.SELL:
            if self.position > 0:
                # 计算卖出金额
                sell_value = self.position * execution_price
                fee = sell_value * self.transaction_fee
                
                # 更新持仓和资金
                self.cash += (sell_value - fee)
                self.position = 0.0
                
                # 记录交易
                trade = TradeRecord(
                    timestamp=timestamp,
                    action=action,
                    price=execution_price,
                    quantity=self.position,
                    cash=self.cash,
                    position=0.0,
                    portfolio_value=self.cash,
                    rsi=rsi,
                    reason=f"RSI={rsi:.2f} > {self.rsi_sell_threshold}"
                )
                self.trades.append(trade)
    
    def run_backtest(self, data: pd.DataFrame, rsi_column: str = 'RSI_14') -> pd.DataFrame:
        """
        运行回测
        
        Args:
            data: 包含价格和RSI的数据
            rsi_column: RSI列名
            
        Returns:
            pd.DataFrame: 包含回测结果的数据
        """
        # 重置回测状态
        self.cash = self.initial_capital
        self.position = 0.0
        self.trades = []
        self.portfolio_values = []
        self.dates = []
        
        # 生成信号
        data_with_signals = self.generate_signals(data, rsi_column)
        
        # 执行回测
        in_position = False
        
        for i in range(len(data_with_signals)):
            timestamp = data_with_signals.index[i]
            price = data_with_signals.iloc[i]['Close']
            signal = data_with_signals.iloc[i]['signal']
            rsi = data_with_signals.iloc[i][rsi_column]
            
            # 记录日期和投资组合价值
            self.dates.append(timestamp)
            portfolio_value = self.cash + self.position * price
            self.portfolio_values.append(portfolio_value)
            
            # 执行交易信号
            if signal == TradeAction.BUY.value and not in_position:
                self.execute_trade(TradeAction.BUY, price, timestamp, rsi)
                in_position = True
            elif signal == TradeAction.SELL.value and in_position:
                self.execute_trade(TradeAction.SELL, price, timestamp, rsi)
                in_position = False
        
        # 最后一天如果还有持仓，按收盘价计算最终价值
        if self.position > 0:
            final_price = data_with_signals.iloc[-1]['Close']
            portfolio_value = self.cash + self.position * final_price
            self.portfolio_values[-1] = portfolio_value
        
        # 创建回测结果DataFrame
        backtest_results = pd.DataFrame({
            'date': self.dates,
            'portfolio_value': self.portfolio_values,
            'price': data_with_signals['Close'].values,
            'rsi': data_with_signals[rsi_column].values,
            'signal': data_with_signals['signal'].values,
            'position': data_with_signals['position'].values
        })
        backtest_results.set_index('date', inplace=True)
        
        return backtest_results
    
    def get_trade_summary(self) -> pd.DataFrame:
        """
        获取交易摘要
        
        Returns:
            pd.DataFrame: 交易摘要
        """
        if not self.trades:
            return pd.DataFrame()
        
        trades_data = []
        for trade in self.trades:
            trades_data.append({
                'timestamp': trade.timestamp,
                'action': trade.action.value,
                'price': trade.price,
                'quantity': trade.quantity,
                'cash': trade.cash,
                'position': trade.position,
                'portfolio_value': trade.portfolio_value,
                'rsi': trade.rsi,
                'reason': trade.reason
            })
        
        return pd.DataFrame(trades_data)
    
    def get_performance_metrics(self, backtest_results: pd.DataFrame) -> Dict:
        """
        计算回测性能指标
        
        Args:
            backtest_results: 回测结果数据
            
        Returns:
            Dict: 性能指标字典
        """
        if backtest_results.empty:
            return {}
        
        # 计算收益率
        portfolio_values = backtest_results['portfolio_value'].values
        returns = np.diff(portfolio_values) / portfolio_values[:-1]
        
        # 总收益率
        total_return = (portfolio_values[-1] - self.initial_capital) / self.initial_capital
        
        # 年化收益率（假设一年有252个交易日）
        num_days = len(portfolio_values)
        annualized_return = (1 + total_return) ** (252 / num_days) - 1 if num_days > 0 else 0
        
        # 波动率（年化）
        volatility = np.std(returns) * np.sqrt(252) if len(returns) > 0 else 0
        
        # 夏普比率（假设无风险利率为0）
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
        
        # 最大回撤
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (portfolio_values - peak) / peak
        max_drawdown = np.min(drawdown)
        
        # 交易统计
        trades_df = self.get_trade_summary()
        num_trades = len(trades_df)
        num_buys = len(trades_df[trades_df['action'] == 'BUY'])
        num_sells = len(trades_df[trades_df['action'] == 'SELL'])
        
        # 胜率（如果有卖出交易）
        win_rate = 0.0
        if num_sells > 0:
            # 这里简化计算，实际需要计算每笔交易的盈亏
            win_rate = num_sells / (num_buys + num_sells) * 100
        
        metrics = {
            'initial_capital': self.initial_capital,
            'final_portfolio_value': portfolio_values[-1],
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'annualized_return': annualized_return,
            'annualized_return_pct': annualized_return * 100,
            'volatility': volatility,
            'volatility_pct': volatility * 100,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown * 100,
            'num_trades': num_trades,
            'num_buys': num_buys,
            'num_sells': num_sells,
            'win_rate_pct': win_rate,
            'rsi_buy_threshold': self.rsi_buy_threshold,
            'rsi_sell_threshold': self.rsi_sell_threshold
        }
        
        return metrics
    
    def save_results(self, backtest_results: pd.DataFrame, output_dir: str = ".") -> None:
        """
        保存回测结果
        
        Args:
            backtest_results: 回测结果数据
            output_dir: 输出目录
        """
        import os
        
        # 确保目录存在
        os.makedirs(output_dir, exist_ok=True)
        
        # 保存回测结果
        backtest_results.to_csv(os.path.join(output_dir, "backtest_results.csv"))
        
        # 保存交易记录
        trades_df = self.get_trade_summary()
        if not trades_df.empty:
            trades_df.to_csv(os.path.join(output_dir, "trade_records.csv"), index=False)
        
        # 保存性能指标
        metrics = self.get_performance_metrics(backtest_results)
        if metrics:
            metrics_df = pd.DataFrame([metrics])
            metrics_df.to_csv(os.path.join(output_dir, "performance_metrics.csv"), index=False)
        
        print(f"回测结果已保存到目录: {output_dir}")


def run_rsi_strategy_backtest(
    data: pd.DataFrame,
    initial_capital: float = 10000.0,
    rsi_buy_threshold: float = 20.0,
    rsi_sell_threshold: float = 60.0,
    position_size: float = 1.0
) -> Tuple[pd.DataFrame, Dict]:
    """
    运行RSI策略回测的便捷函数
    
    Args:
        data: 包含价格和RSI的数据
        initial_capital: 初始资金
        rsi_buy_threshold: RSI买入阈值
        rsi_sell_threshold: RSI卖出阈值
        position_size: 仓位比例
        
    Returns:
        Tuple[pd.DataFrame, Dict]: 回测结果和性能指标
    """
    # 创建回测引擎
    engine = BacktestEngine(
        initial_capital=initial_capital,
        rsi_buy_threshold=rsi_buy_threshold,
        rsi_sell_threshold=rsi_sell_threshold,
        position_size=position_size
    )
    
    # 运行回测
    backtest_results = engine.run_backtest(data)
    
    # 计算性能指标
    metrics = engine.get_performance_metrics(backtest_results)
    
    return backtest_results, metrics


if __name__ == "__main__":
    # 测试回测引擎
    print("测试回测引擎...")
    
    # 创建测试数据
    dates = pd.date_range('2023-01-01', periods=100, freq='D')
    np.random.seed(42)
    
    # 生成模拟价格数据
    prices = np.cumprod(1 + np.random.randn(100) * 0.01) * 100
    
    # 生成模拟RSI数据（在0-100之间波动）
    rsi_values = 50 + 50 * np.sin(np.linspace(0, 4*np.pi, 100)) + np.random.randn(100) * 10
    rsi_values = np.clip(rsi_values, 0, 100)
    
    test_data = pd.DataFrame({
        'Open': prices * 0.99,
        'High': prices * 1.02,
        'Low': prices * 0.98,
        'Close': prices,
        'Volume': np.random.uniform(1000, 5000, 100),
        'RSI_14': rsi_values
    }, index=dates)
    
    print(f"测试数据形状: {test_data.shape}")
    print(f"测试数据时间范围: {test_data.index[0]} 到 {test_data.index[-1]}")
    
    # 运行回测
    engine = BacktestEngine(
        initial_capital=10000.0,
        rsi_buy_threshold=20.0,
        rsi_sell_threshold=60.0
    )
    
    results = engine.run_backtest(test_data)
    
    print(f"\n回测结果形状: {results.shape}")
    print(f"回测时间范围: {results.index[0]} 到 {results.index[-1]}")
    
    # 显示交易记录
    trades = engine.get_trade_summary()
    if not trades.empty:
        print(f"\n交易记录 ({len(trades)} 笔):")
        print(trades[['timestamp', 'action', 'price', 'quantity', 'portfolio_value', 'rsi']])
    else:
        print("\n没有交易记录")
    
    # 显示性能指标
    metrics = engine.get_performance_metrics(results)
    if metrics:
        print(f"\n性能指标:")
        print(f"初始资金: ${metrics['initial_capital']:.2f}")
        print(f"最终组合价值: ${metrics['final_portfolio_value']:.2f}")
        print(f"总收益率: {metrics['total_return_pct']:.2f}%")
        print(f"年化收益率: {metrics['annualized_return_pct']:.2f}%")
        print(f"夏普比率: {metrics['sharpe_ratio']:.2f}")
        print(f"最大回撤: {metrics['max_drawdown_pct']:.2f}%")
        print(f"交易次数: {metrics['num_trades']} (买入: {metrics['num_buys']}, 卖出: {metrics['num_sells']})")
        print(f"胜率: {metrics['win_rate_pct']:.2f}%")