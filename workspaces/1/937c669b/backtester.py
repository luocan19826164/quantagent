"""
回测引擎模块
实现基于RSI策略的回测功能，包括资金管理、交易执行和绩效计算
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime
import matplotlib.pyplot as plt
from enum import Enum
import warnings

warnings.filterwarnings('ignore')


class TradeAction(Enum):
    """交易动作枚举"""
    BUY = "BUY"
    SELL = "SELL"


class Trade:
    """交易记录类"""
    
    def __init__(self, 
                 timestamp: pd.Timestamp,
                 action: TradeAction,
                 price: float,
                 quantity: float,
                 commission: float = 0.0):
        """
        初始化交易记录
        
        Args:
            timestamp: 交易时间戳
            action: 交易动作（买入/卖出）
            price: 交易价格
            quantity: 交易数量
            commission: 交易手续费
        """
        self.timestamp = timestamp
        self.action = action
        self.price = price
        self.quantity = quantity
        self.commission = commission
        self.value = price * quantity
        
    def __repr__(self) -> str:
        """交易记录字符串表示"""
        return (f"Trade(timestamp={self.timestamp}, action={self.action.value}, "
                f"price={self.price:.2f}, quantity={self.quantity:.6f}, "
                f"value={self.value:.2f}, commission={self.commission:.2f})")


class Backtester:
    """
    回测引擎类
    
    功能：
    1. 资金管理：初始资金、现金余额、持仓管理
    2. 交易执行：根据信号执行买入卖出操作
    3. 绩效计算：收益率、夏普比率、最大回撤等
    4. 交易记录：记录所有交易详情
    """
    
    def __init__(self, 
                 initial_capital: float = 10000.0,
                 commission_rate: float = 0.001,  # 0.1%手续费
                 slippage_rate: float = 0.0005):  # 0.05%滑点
        """
        初始化回测引擎
        
        Args:
            initial_capital: 初始资金（美元）
            commission_rate: 交易手续费率（百分比）
            slippage_rate: 交易滑点率（百分比）
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_rate = slippage_rate
        
        # 状态变量
        self.cash = initial_capital
        self.position = 0.0  # BTC持仓数量
        self.position_value = 0.0  # 持仓市值
        self.total_value = initial_capital  # 总资产（现金+持仓）
        
        # 记录
        self.trades: List[Trade] = []
        self.portfolio_history: List[Dict[str, Any]] = []
        self.signals_history: List[Dict[str, Any]] = []
        
        # 绩效指标
        self.returns: List[float] = []
        self.dates: List[pd.Timestamp] = []
        
    def reset(self) -> None:
        """重置回测引擎状态"""
        self.cash = self.initial_capital
        self.position = 0.0
        self.position_value = 0.0
        self.total_value = self.initial_capital
        
        self.trades.clear()
        self.portfolio_history.clear()
        self.signals_history.clear()
        self.returns.clear()
        self.dates.clear()
    
    def execute_trade(self, 
                     timestamp: pd.Timestamp,
                     action: TradeAction,
                     price: float,
                     signal_type: str) -> Optional[Trade]:
        """
        执行交易
        
        Args:
            timestamp: 交易时间
            action: 交易动作
            price: 信号价格
            signal_type: 信号类型
            
        Returns:
            交易记录对象，如果交易失败返回None
        """
        # 应用滑点
        if action == TradeAction.BUY:
            execution_price = price * (1 + self.slippage_rate)
        else:  # SELL
            execution_price = price * (1 - self.slippage_rate)
        
        # 计算手续费
        commission_rate = self.commission_rate
        
        if action == TradeAction.BUY:
            # 买入逻辑
            if self.cash <= 0:
                return None
            
            # 计算可买入数量（考虑手续费）
            max_quantity = self.cash / (execution_price * (1 + commission_rate))
            quantity = max_quantity
            
            # 计算交易金额和手续费
            trade_value = execution_price * quantity
            commission = trade_value * commission_rate
            
            # 检查资金是否足够
            if trade_value + commission > self.cash:
                # 调整数量使交易可行
                quantity = self.cash / (execution_price * (1 + commission_rate))
                trade_value = execution_price * quantity
                commission = trade_value * commission_rate
            
            # 更新状态
            self.cash -= (trade_value + commission)
            self.position += quantity
            self.position_value = self.position * execution_price
            self.total_value = self.cash + self.position_value
            
            # 创建交易记录
            trade = Trade(timestamp, action, execution_price, quantity, commission)
            self.trades.append(trade)
            
            return trade
            
        else:  # SELL
            # 卖出逻辑
            if self.position <= 0:
                return None
            
            # 卖出全部持仓
            quantity = self.position
            trade_value = execution_price * quantity
            commission = trade_value * commission_rate
            
            # 更新状态
            self.cash += (trade_value - commission)
            self.position = 0.0
            self.position_value = 0.0
            self.total_value = self.cash
            
            # 创建交易记录
            trade = Trade(timestamp, action, execution_price, quantity, commission)
            self.trades.append(trade)
            
            return trade
    
    def update_portfolio_value(self, 
                              timestamp: pd.Timestamp,
                              price: float) -> None:
        """
        更新投资组合价值
        
        Args:
            timestamp: 当前时间
            price: 当前价格
        """
        # 更新持仓市值
        self.position_value = self.position * price
        self.total_value = self.cash + self.position_value
        
        # 记录投资组合状态
        portfolio_record = {
            'timestamp': timestamp,
            'price': price,
            'cash': self.cash,
            'position': self.position,
            'position_value': self.position_value,
            'total_value': self.total_value
        }
        self.portfolio_history.append(portfolio_record)
        
        # 记录日期和总价值用于计算收益率
        self.dates.append(timestamp)
        
        if len(self.portfolio_history) > 1:
            prev_value = self.portfolio_history[-2]['total_value']
            current_value = self.total_value
            daily_return = (current_value - prev_value) / prev_value
            self.returns.append(daily_return)
    
    def run_backtest(self,
                    data: pd.DataFrame,
                    signals: pd.Series,
                    strategy_name: str = "RSI Strategy") -> Dict[str, Any]:
        """
        运行回测
        
        Args:
            data: 价格数据DataFrame，必须包含'Date'和'Close'列
            signals: 交易信号序列，与数据长度相同
            strategy_name: 策略名称
            
        Returns:
            回测结果字典
        """
        print(f"开始回测: {strategy_name}")
        print(f"数据范围: {data['Date'].min()} 到 {data['Date'].max()}")
        print(f"数据点数: {len(data)}")
        print(f"初始资金: ${self.initial_capital:,.2f}")
        print("-" * 50)
        
        # 重置状态
        self.reset()
        
        # 确保数据按日期排序
        data = data.sort_values('Date').reset_index(drop=True)
        
        # 运行回测
        for i in range(len(data)):
            current_date = data.loc[i, 'Date']
            current_price = data.loc[i, 'Close']
            current_signal = signals.iloc[i] if i < len(signals) else 'HOLD'
            
            # 执行交易信号
            trade = None
            if current_signal == 'BUY' and self.position == 0:
                trade = self.execute_trade(current_date, TradeAction.BUY, 
                                          current_price, 'RSI_BUY')
            elif current_signal == 'SELL' and self.position > 0:
                trade = self.execute_trade(current_date, TradeAction.SELL, 
                                          current_price, 'RSI_SELL')
            
            # 记录信号
            signal_record = {
                'timestamp': current_date,
                'price': current_price,
                'signal': current_signal,
                'trade_executed': trade is not None
            }
            self.signals_history.append(signal_record)
            
            # 更新投资组合价值
            self.update_portfolio_value(current_date, current_price)
        
        # 最后一天强制平仓（如果有持仓）
        if self.position > 0:
            last_date = data['Date'].iloc[-1]
            last_price = data['Close'].iloc[-1]
            self.execute_trade(last_date, TradeAction.SELL, last_price, 'FORCE_CLOSE')
            self.update_portfolio_value(last_date, last_price)
        
        # 计算绩效指标
        performance = self.calculate_performance(data)
        
        # 打印回测结果
        self.print_backtest_results(performance)
        
        return performance
    
    def calculate_performance(self, data: pd.DataFrame) -> Dict[str, Any]:
        """
        计算绩效指标
        
        Args:
            data: 价格数据
            
        Returns:
            绩效指标字典
        """
        if len(self.portfolio_history) == 0:
            return {}
        
        # 提取时间序列数据
        dates = [record['timestamp'] for record in self.portfolio_history]
        portfolio_values = [record['total_value'] for record in self.portfolio_history]
        prices = [record['price'] for record in self.portfolio_history]
        
        # 转换为pandas Series以便计算
        portfolio_series = pd.Series(portfolio_values, index=dates)
        price_series = pd.Series(prices, index=dates)
        
        # 计算总收益率
        initial_value = portfolio_series.iloc[0]
        final_value = portfolio_series.iloc[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # 计算年化收益率
        days = (dates[-1] - dates[0]).days
        years = days / 365.25
        annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
        
        # 计算日收益率序列
        daily_returns = portfolio_series.pct_change().dropna()
        
        # 计算夏普比率（假设无风险利率为0）
        if len(daily_returns) > 0:
            sharpe_ratio = np.sqrt(252) * daily_returns.mean() / daily_returns.std() if daily_returns.std() > 0 else 0
        else:
            sharpe_ratio = 0
        
        # 计算最大回撤
        cumulative_returns = (1 + daily_returns).cumprod()
        running_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - running_max) / running_max
        max_drawdown = drawdown.min()
        
        # 计算胜率
        winning_trades = 0
        total_trades = len(self.trades)
        
        if total_trades >= 2:
            # 分析每笔交易的盈亏
            for i in range(0, total_trades - 1, 2):
                if i + 1 < total_trades:
                    buy_trade = self.trades[i]
                    sell_trade = self.trades[i + 1]
                    
                    if sell_trade.action == TradeAction.SELL and buy_trade.action == TradeAction.BUY:
                        buy_cost = buy_trade.value + buy_trade.commission
                        sell_proceeds = sell_trade.value - sell_trade.commission
                        profit = sell_proceeds - buy_cost
                        
                        if profit > 0:
                            winning_trades += 1
            
            win_rate = winning_trades / (total_trades // 2) if total_trades >= 2 else 0
        else:
            win_rate = 0
        
        # 计算交易统计
        total_commission = sum(trade.commission for trade in self.trades)
        total_trade_value = sum(trade.value for trade in self.trades)
        
        # 计算持仓时间统计
        holding_periods = []
        if len(self.trades) >= 2:
            for i in range(0, len(self.trades) - 1, 2):
                if i + 1 < len(self.trades):
                    buy_time = self.trades[i].timestamp
                    sell_time = self.trades[i + 1].timestamp
                    holding_days = (sell_time - buy_time).days
                    holding_periods.append(holding_days)
        
        avg_holding_days = np.mean(holding_periods) if holding_periods else 0
        
        # 与买入持有策略比较
        buy_hold_return = (price_series.iloc[-1] - price_series.iloc[0]) / price_series.iloc[0]
        buy_hold_final_value = self.initial_capital * (1 + buy_hold_return)
        
        # 超额收益
        excess_return = total_return - buy_hold_return
        
        performance = {
            'strategy_name': 'RSI Strategy',
            'initial_capital': self.initial_capital,
            'final_value': final_value,
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'total_commission': total_commission,
            'total_trade_value': total_trade_value,
            'avg_holding_days': avg_holding_days,
            'buy_hold_return': buy_hold_return,
            'buy_hold_final_value': buy_hold_final_value,
            'excess_return': excess_return,
            'portfolio_values': portfolio_values,
            'dates': dates,
            'prices': prices,
            'trades': self.trades,
            'signals_history': self.signals_history
        }
        
        return performance
    
    def print_backtest_results(self, performance: Dict[str, Any]) -> None:
        """打印回测结果"""
        print("\n" + "=" * 60)
        print("回测结果汇总")
        print("=" * 60)
        
        print(f"\n📊 绩效指标:")
        print(f"   初始资金: ${performance.get('initial_capital', 0):,.2f}")
        print(f"   最终价值: ${performance.get('final_value', 0):,.2f}")
        print(f"   总收益率: {performance.get('total_return', 0) * 100:.2f}%")
        print(f"   年化收益率: {performance.get('annualized_return', 0) * 100:.2f}%")
        print(f"   夏普比率: {performance.get('sharpe_ratio', 0):.3f}")
        print(f"   最大回撤: {performance.get('max_drawdown', 0) * 100:.2f}%")
        
        print(f"\n📈 交易统计:")
        print(f"   总交易次数: {performance.get('total_trades', 0)}")
        print(f"   盈利交易: {performance.get('winning_trades', 0)}")
        print(f"   胜率: {performance.get('win_rate', 0) * 100:.1f}%")
        print(f"   总手续费: ${performance.get('total_commission', 0):,.2f}")
        print(f"   平均持仓天数: {performance.get('avg_holding_days', 0):.1f}天")
        
        print(f"\n📊 基准比较:")
        print(f"   买入持有收益率: {performance.get('buy_hold_return', 0) * 100:.2f}%")
        print(f"   买入持有最终价值: ${performance.get('buy_hold_final_value', 0):,.2f}")
        print(f"   超额收益: {performance.get('excess_return', 0) * 100:.2f}%")
        
        print(f"\n📋 交易记录:")
        if performance.get('trades'):
            for i, trade in enumerate(performance['trades']):
                print(f"   {i+1}. {trade}")
        else:
            print("   无交易记录")
        
        print("\n" + "=" * 60)
    
    def plot_results(self, performance: Dict[str, Any]) -> None:
        """
        绘制回测结果图表
        
        Args:
            performance: 回测结果字典
        """
        if not performance:
            print("无绩效数据可绘制")
            return
        
        # 创建图表
        fig, axes = plt.subplots(3, 1, figsize=(12, 10))
        
        # 提取数据
        dates = performance['dates']
        portfolio_values = performance['portfolio_values']
        prices = performance['prices']
        
        # 1. 价格和信号图
        ax1 = axes[0]
        ax1.plot(dates, prices, 'b-', label='BTC Price', linewidth=1)
        ax1.set_ylabel('Price (USD)', color='b')
        ax1.tick_params(axis='y', labelcolor='b')
        ax1.set_title('BTC Price and Trading Signals')
        ax1.grid(True, alpha=0.3)
        
        # 标记买入卖出信号
        buy_signals = [record for record in performance['signals_history'] 
                      if record['signal'] == 'BUY' and record['trade_executed']]
        sell_signals = [record for record in performance['signals_history'] 
                       if record['signal'] == 'SELL' and record['trade_executed']]
        
        if buy_signals:
            buy_dates = [record['timestamp'] for record in buy_signals]
            buy_prices = [record['price'] for record in buy_signals]
            ax1.scatter(buy_dates, buy_prices, color='green', marker='^', 
                       s=100, label='Buy Signal', zorder=5)
        
        if sell_signals:
            sell_dates = [record['timestamp'] for record in sell_signals]
            sell_prices = [record['price'] for record in sell_signals]
            ax1.scatter(sell_dates, sell_prices, color='red', marker='v', 
                       s=100, label='Sell Signal', zorder=5)
        
        ax1.legend(loc='upper left')
        
        # 2. 投资组合价值图
        ax2 = axes[1]
        ax2.plot(dates, portfolio_values, 'g-', label='Portfolio Value', linewidth=2)
        ax2.axhline(y=self.initial_capital, color='r', linestyle='--', 
                   label=f'Initial Capital (${self.initial_capital:,.0f})')
        ax2.set_ylabel('Portfolio Value (USD)', color='g')
        ax2.tick_params(axis='y', labelcolor='g')
        ax2.set_title('Portfolio Value Over Time')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left')
        
        # 3. 收益率图
        ax3 = axes[2]
        if len(performance.get('returns', [])) > 0:
            returns_dates = dates[1:]  # 收益率从第二天开始
            cumulative_returns = np.cumprod(1 + np.array(performance['returns'])) - 1
            ax3.plot(returns_dates, cumulative_returns * 100, 'purple', 
                    label='Cumulative Return', linewidth=2)
            ax3.set_ylabel('Cumulative Return (%)', color='purple')
            ax3.tick_params(axis='y', labelcolor='purple')
            ax3.set_title('Cumulative Returns')
            ax3.grid(True, alpha=0.3)
            ax3.legend(loc='upper left')
        
        # 设置x轴标签
        for ax in axes:
            ax.set_xlabel('Date')
        
        plt.tight_layout()
        plt.show()
        
        # 打印交易统计
        self.print_trade_statistics(performance)
    
    def print_trade_statistics(self, performance: Dict[str, Any]) -> None:
        """打印详细交易统计"""
        trades = performance.get('trades', [])
        if not trades:
            print("\n无交易记录")
            return
        
        print("\n" + "=" * 60)
        print("详细交易分析")
        print("=" * 60)
        
        # 分析每笔交易的盈亏
        trade_results = []
        for i in range(0, len(trades) - 1, 2):
            if i + 1 < len(trades):
                buy_trade = trades[i]
                sell_trade = trades[i + 1]
                
                if buy_trade.action == TradeAction.BUY and sell_trade.action == TradeAction.SELL:
                    buy_cost = buy_trade.value + buy_trade.commission
                    sell_proceeds = sell_trade.value - sell_trade.commission
                    profit = sell_proceeds - buy_cost
                    profit_pct = (profit / buy_cost) * 100
                    
                    holding_days = (sell_trade.timestamp - buy_trade.timestamp).days
                    
                    trade_result = {
                        'trade_num': len(trade_results) + 1,
                        'buy_date': buy_trade.timestamp,
                        'buy_price': buy_trade.price,
                        'sell_date': sell_trade.timestamp,
                        'sell_price': sell_trade.timestamp,
                        'quantity': buy_trade.quantity,
                        'profit': profit,
                        'profit_pct': profit_pct,
                        'holding_days': holding_days,
                        'is_winning': profit > 0
                    }
                    trade_results.append(trade_result)
        
        if trade_results:
            print(f"\n总交易对: {len(trade_results)}")
            
            # 计算统计指标
            profits = [tr['profit'] for tr in trade_results]
            profit_pcts = [tr['profit_pct'] for tr in trade_results]
            holding_days = [tr['holding_days'] for tr in trade_results]
            
            winning_trades = [tr for tr in trade_results if tr['is_winning']]
            losing_trades = [tr for tr in trade_results if not tr['is_winning']]
            
            print(f"\n📈 盈利交易 ({len(winning_trades)}笔):")
            if winning_trades:
                avg_win_profit = np.mean([tr['profit'] for tr in winning_trades])
                avg_win_pct = np.mean([tr['profit_pct'] for tr in winning_trades])
                max_win = max([tr['profit'] for tr in winning_trades])
                max_win_pct = max([tr['profit_pct'] for tr in winning_trades])
                
                print(f"   平均盈利: ${avg_win_profit:,.2f} ({avg_win_pct:.2f}%)")
                print(f"   最大盈利: ${max_win:,.2f} ({max_win_pct:.2f}%)")
            
            print(f"\n📉 亏损交易 ({len(losing_trades)}笔):")
            if losing_trades:
                avg_loss = np.mean([tr['profit'] for tr in losing_trades])
                avg_loss_pct = np.mean([tr['profit_pct'] for tr in losing_trades])
                max_loss = min([tr['profit'] for tr in losing_trades])
                max_loss_pct = min([tr['profit_pct'] for tr in losing_trades])
                
                print(f"   平均亏损: ${avg_loss:,.2f} ({avg_loss_pct:.2f}%)")
                print(f"   最大亏损: ${max_loss:,.2f} ({max_loss_pct:.2f}%)")
            
            print(f"\n📊 整体统计:")
            print(f"   平均持仓天数: {np.mean(holding_days):.1f}天")
            print(f"   最短持仓: {min(holding_days)}天")
            print(f"   最长持仓: {max(holding_days)}天")
            print(f"   平均单笔收益: ${np.mean(profits):,.2f} ({np.mean(profit_pcts):.2f}%)")
            print(f"   收益标准差: ${np.std(profits):,.2f} ({np.std(profit_pcts):.2f}%)")
            
            # 显示前5笔交易详情
            print(f"\n📋 前5笔交易详情:")
            for i, tr in enumerate(trade_results[:5]):
                print(f"   {i+1}. 买入: {tr['buy_date'].strftime('%Y-%m-%d')} @ ${tr['buy_price']:.2f}")
                print(f"      卖出: {tr['sell_date'].strftime('%Y-%m-%d')} @ ${tr['sell_price']:.2f}")
                print(f"      持仓: {tr['holding_days']}天, 盈亏: ${tr['profit']:,.2f} ({tr['profit_pct']:.2f}%)")
                print(f"      结果: {'盈利' if tr['is_winning'] else '亏损'}")
                print()
        
        print("=" * 60)


def test_backtester():
    """测试回测引擎"""
    print("=" * 60)
    print("回测引擎测试")
    print("=" * 60)
    
    # 创建测试数据
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    base_price = 40000
    
    # 生成价格数据（模拟BTC价格走势）
    returns = np.random.randn(100) * 0.02  # 2%日波动率
    prices = base_price * np.exp(np.cumsum(returns))
    
    # 创建DataFrame
    data = pd.DataFrame({
        'Date': dates,
        'Open': prices * 0.99,  # 开盘价略低于收盘价
        'High': prices * 1.01,  # 最高价
        'Low': prices * 0.98,   # 最低价
        'Close': prices,        # 收盘价
        'Volume': np.random.randint(10000, 50000, 100)
    })
    
    # 创建测试信号（模拟RSI策略信号）
    signals = pd.Series(['HOLD'] * 100, index=dates)
    
    # 模拟一些买入卖出信号
    signals.iloc[20] = 'BUY'   # 第20天买入
    signals.iloc[40] = 'SELL'  # 第40天卖出
    signals.iloc[60] = 'BUY'   # 第60天买入
    signals.iloc[80] = 'SELL'  # 第80天卖出
    
    print(f"\n测试数据信息:")
    print(f"数据范围: {data['Date'].min()} 到 {data['Date'].max()}")
    print(f"数据点数: {len(data)}")
    print(f"价格范围: ${data['Close'].min():,.0f} - ${data['Close'].max():,.0f}")
    print(f"信号数量: {(signals == 'BUY').sum()}买入, {(signals == 'SELL').sum()}卖出")
    
    # 创建回测引擎
    backtester = Backtester(
        initial_capital=10000.0,
        commission_rate=0.001,  # 0.1%手续费
        slippage_rate=0.0005    # 0.05%滑点
    )
    
    # 运行回测
    print("\n运行回测...")
    performance = backtester.run_backtest(data, signals, "Test RSI Strategy")
    
    # 绘制结果
    print("\n绘制图表...")
    backtester.plot_results(performance)
    
    return backtester, performance


if __name__ == "__main__":
    backtester, performance = test_backtester()
    print("\n测试完成！")