"""
回测性能指标计算模块
包含各种量化策略评估指标
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PerformanceMetrics:
    """回测性能指标计算器"""
    
    @staticmethod
    def calculate_annualized_return(daily_returns: pd.Series, trading_days_per_year: int = 252) -> float:
        """
        计算年化收益率
        
        Args:
            daily_returns: 日收益率序列
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            年化收益率（百分比）
        """
        if len(daily_returns) == 0:
            return 0.0
        
        # 计算累计收益率
        cumulative_return = (1 + daily_returns).prod() - 1
        
        # 计算年化收益率
        n_days = len(daily_returns)
        annualized_return = (1 + cumulative_return) ** (trading_days_per_year / n_days) - 1
        
        return annualized_return * 100  # 转换为百分比
    
    @staticmethod
    def calculate_annualized_volatility(daily_returns: pd.Series, trading_days_per_year: int = 252) -> float:
        """
        计算年化波动率
        
        Args:
            daily_returns: 日收益率序列
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            年化波动率（百分比）
        """
        if len(daily_returns) == 0:
            return 0.0
        
        # 计算日波动率并年化
        daily_volatility = daily_returns.std()
        annualized_volatility = daily_volatility * np.sqrt(trading_days_per_year)
        
        return annualized_volatility * 100  # 转换为百分比
    
    @staticmethod
    def calculate_sharpe_ratio(daily_returns: pd.Series, risk_free_rate: float = 0.02,
                              trading_days_per_year: int = 252) -> float:
        """
        计算夏普比率
        
        Args:
            daily_returns: 日收益率序列
            risk_free_rate: 年化无风险利率，默认为2%
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            夏普比率
        """
        if len(daily_returns) == 0:
            return 0.0
        
        # 计算年化收益率和波动率
        annualized_return = PerformanceMetrics.calculate_annualized_return(daily_returns, trading_days_per_year) / 100
        annualized_volatility = PerformanceMetrics.calculate_annualized_volatility(daily_returns, trading_days_per_year) / 100
        
        # 计算超额收益率
        excess_return = annualized_return - risk_free_rate
        
        # 计算夏普比率
        if annualized_volatility > 0:
            sharpe_ratio = excess_return / annualized_volatility
        else:
            sharpe_ratio = 0.0
        
        return sharpe_ratio
    
    @staticmethod
    def calculate_sortino_ratio(daily_returns: pd.Series, risk_free_rate: float = 0.02,
                               trading_days_per_year: int = 252) -> float:
        """
        计算索提诺比率（只考虑下行风险）
        
        Args:
            daily_returns: 日收益率序列
            risk_free_rate: 年化无风险利率，默认为2%
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            索提诺比率
        """
        if len(daily_returns) == 0:
            return 0.0
        
        # 计算年化收益率
        annualized_return = PerformanceMetrics.calculate_annualized_return(daily_returns, trading_days_per_year) / 100
        
        # 计算下行偏差（只考虑负收益）
        downside_returns = daily_returns[daily_returns < 0]
        if len(downside_returns) > 0:
            downside_deviation = downside_returns.std() * np.sqrt(trading_days_per_year)
        else:
            downside_deviation = 0.0
        
        # 计算索提诺比率
        excess_return = annualized_return - risk_free_rate
        
        if downside_deviation > 0:
            sortino_ratio = excess_return / downside_deviation
        else:
            sortino_ratio = 0.0
        
        return sortino_ratio
    
    @staticmethod
    def calculate_max_drawdown(portfolio_values: pd.Series) -> Tuple[float, pd.Timestamp, pd.Timestamp]:
        """
        计算最大回撤
        
        Args:
            portfolio_values: 投资组合价值序列
            
        Returns:
            (最大回撤百分比, 回撤开始时间, 回撤结束时间)
        """
        if len(portfolio_values) == 0:
            return 0.0, None, None
        
        # 计算累积最大值
        cumulative_max = portfolio_values.expanding().max()
        
        # 计算回撤
        drawdown = (portfolio_values - cumulative_max) / cumulative_max * 100
        
        # 找到最大回撤
        max_drawdown = drawdown.min()
        max_drawdown_end_idx = drawdown.idxmin()
        
        # 找到回撤开始时间（回撤开始前的峰值）
        if max_drawdown_end_idx is not None:
            # 找到回撤结束时间之前的峰值
            pre_drawdown_data = portfolio_values.loc[:max_drawdown_end_idx]
            if len(pre_drawdown_data) > 0:
                max_drawdown_start_idx = pre_drawdown_data.idxmax()
            else:
                max_drawdown_start_idx = None
        else:
            max_drawdown_start_idx = None
        
        return max_drawdown, max_drawdown_start_idx, max_drawdown_end_idx
    
    @staticmethod
    def calculate_calmar_ratio(portfolio_values: pd.Series, trading_days_per_year: int = 252) -> float:
        """
        计算卡尔马比率（年化收益率 / 最大回撤）
        
        Args:
            portfolio_values: 投资组合价值序列
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            卡尔马比率
        """
        if len(portfolio_values) < 2:
            return 0.0
        
        # 计算收益率序列
        returns = portfolio_values.pct_change().dropna()
        
        if len(returns) == 0:
            return 0.0
        
        # 计算年化收益率
        annualized_return = PerformanceMetrics.calculate_annualized_return(returns, trading_days_per_year) / 100
        
        # 计算最大回撤
        max_drawdown, _, _ = PerformanceMetrics.calculate_max_drawdown(portfolio_values)
        max_drawdown_abs = abs(max_drawdown) / 100  # 转换为小数
        
        # 计算卡尔马比率
        if max_drawdown_abs > 0:
            calmar_ratio = annualized_return / max_drawdown_abs
        else:
            calmar_ratio = 0.0
        
        return calmar_ratio
    
    @staticmethod
    def calculate_win_rate(trade_results: List[Dict]) -> Tuple[float, int, int]:
        """
        计算胜率
        
        Args:
            trade_results: 交易结果列表，每个元素包含'profit'字段
            
        Returns:
            (胜率百分比, 盈利交易数, 亏损交易数)
        """
        if not trade_results:
            return 0.0, 0, 0
        
        winning_trades = [t for t in trade_results if t.get('profit', 0) > 0]
        losing_trades = [t for t in trade_results if t.get('profit', 0) <= 0]
        
        win_rate = len(winning_trades) / len(trade_results) * 100
        
        return win_rate, len(winning_trades), len(losing_trades)
    
    @staticmethod
    def calculate_profit_factor(trade_results: List[Dict]) -> float:
        """
        计算盈利因子（总盈利 / 总亏损）
        
        Args:
            trade_results: 交易结果列表，每个元素包含'profit'字段
            
        Returns:
            盈利因子
        """
        if not trade_results:
            return 0.0
        
        total_profit = sum(max(t.get('profit', 0), 0) for t in trade_results)
        total_loss = sum(abs(min(t.get('profit', 0), 0)) for t in trade_results)
        
        if total_loss > 0:
            profit_factor = total_profit / total_loss
        else:
            profit_factor = float('inf') if total_profit > 0 else 0.0
        
        return profit_factor
    
    @staticmethod
    def calculate_average_trade_return(trade_results: List[Dict]) -> float:
        """
        计算平均每笔交易收益率
        
        Args:
            trade_results: 交易结果列表，每个元素包含'return_rate'字段
            
        Returns:
            平均收益率（百分比）
        """
        if not trade_results:
            return 0.0
        
        returns = [t.get('return_rate', 0) for t in trade_results]
        return np.mean(returns)
    
    @staticmethod
    def calculate_holding_period_stats(trade_results: List[Dict]) -> Dict:
        """
        计算持仓周期统计
        
        Args:
            trade_results: 交易结果列表，每个元素包含'holding_days'字段
            
        Returns:
            持仓周期统计字典
        """
        if not trade_results:
            return {
                'avg_holding_days': 0.0,
                'min_holding_days': 0,
                'max_holding_days': 0,
                'median_holding_days': 0.0
            }
        
        holding_days = [t.get('holding_days', 0) for t in trade_results]
        
        return {
            'avg_holding_days': np.mean(holding_days),
            'min_holding_days': int(np.min(holding_days)),
            'max_holding_days': int(np.max(holding_days)),
            'median_holding_days': np.median(holding_days)
        }
    
    @staticmethod
    def calculate_risk_adjusted_metrics(portfolio_values: pd.Series, 
                                       trading_days_per_year: int = 252) -> Dict:
        """
        计算风险调整后指标
        
        Args:
            portfolio_values: 投资组合价值序列
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            风险调整后指标字典
        """
        if len(portfolio_values) < 2:
            return {}
        
        # 计算收益率序列
        returns = portfolio_values.pct_change().dropna()
        
        if len(returns) == 0:
            return {}
        
        # 计算各种指标
        metrics = {
            'annualized_return_pct': PerformanceMetrics.calculate_annualized_return(returns, trading_days_per_year),
            'annualized_volatility_pct': PerformanceMetrics.calculate_annualized_volatility(returns, trading_days_per_year),
            'sharpe_ratio': PerformanceMetrics.calculate_sharpe_ratio(returns),
            'sortino_ratio': PerformanceMetrics.calculate_sortino_ratio(returns),
            'calmar_ratio': PerformanceMetrics.calculate_calmar_ratio(portfolio_values, trading_days_per_year),
        }
        
        return metrics
    
    @staticmethod
    def generate_performance_report(portfolio_values: pd.Series, 
                                  trade_results: List[Dict],
                                  initial_capital: float,
                                  final_value: float,
                                  trading_days_per_year: int = 252) -> Dict:
        """
        生成完整的性能报告
        
        Args:
            portfolio_values: 投资组合价值序列
            trade_results: 交易结果列表
            initial_capital: 初始资金
            final_value: 最终价值
            trading_days_per_year: 年交易天数，默认为252
            
        Returns:
            完整的性能报告字典
        """
        report = {}
        
        # 基本统计
        report['initial_capital'] = initial_capital
        report['final_value'] = final_value
        report['total_return_abs'] = final_value - initial_capital
        report['total_return_pct'] = ((final_value - initial_capital) / initial_capital) * 100
        
        # 风险调整后指标
        risk_metrics = PerformanceMetrics.calculate_risk_adjusted_metrics(portfolio_values, trading_days_per_year)
        report.update(risk_metrics)
        
        # 最大回撤
        max_drawdown, drawdown_start, drawdown_end = PerformanceMetrics.calculate_max_drawdown(portfolio_values)
        report['max_drawdown_pct'] = max_drawdown
        report['max_drawdown_start'] = drawdown_start
        report['max_drawdown_end'] = drawdown_end
        
        # 交易统计
        report['total_trades'] = len(trade_results) * 2  # 买入和卖出各算一次
        report['completed_trades'] = len(trade_results)
        
        if trade_results:
            # 胜率
            win_rate, winning_trades, losing_trades = PerformanceMetrics.calculate_win_rate(trade_results)
            report['win_rate_pct'] = win_rate
            report['winning_trades'] = winning_trades
            report['losing_trades'] = losing_trades
            
            # 盈利因子
            report['profit_factor'] = PerformanceMetrics.calculate_profit_factor(trade_results)
            
            # 平均收益率
            report['avg_trade_return_pct'] = PerformanceMetrics.calculate_average_trade_return(trade_results)
            
            # 持仓周期统计
            holding_stats = PerformanceMetrics.calculate_holding_period_stats(trade_results)
            report.update(holding_stats)
            
            # 交易收益率统计
            trade_returns = [t.get('return_rate', 0) for t in trade_results]
            report['max_trade_return_pct'] = np.max(trade_returns) if trade_returns else 0
            report['min_trade_return_pct'] = np.min(trade_returns) if trade_returns else 0
            report['std_trade_return_pct'] = np.std(trade_returns) if trade_returns else 0
        else:
            report['win_rate_pct'] = 0.0
            report['winning_trades'] = 0
            report['losing_trades'] = 0
            report['profit_factor'] = 0.0
            report['avg_trade_return_pct'] = 0.0
            report['avg_holding_days'] = 0.0
            report['min_holding_days'] = 0
            report['max_holding_days'] = 0
            report['median_holding_days'] = 0.0
            report['max_trade_return_pct'] = 0.0
            report['min_trade_return_pct'] = 0.0
            report['std_trade_return_pct'] = 0.0
        
        # 计算信息比率（相对于买入持有的超额收益）
        if len(portfolio_values) > 0 and 'Close' in portfolio_values.index:
            # 这里需要价格数据来计算基准收益
            pass
        
        return report
    
    @staticmethod
    def print_performance_report(report: Dict, title: str = "回测性能报告") -> None:
        """
        打印性能报告
        
        Args:
            report: 性能报告字典
            title: 报告标题
        """
        print(f"\n{title}")
        print("=" * 60)
        
        # 基本统计
        print("\n📊 基本统计:")
        print(f"   初始资金: ${report.get('initial_capital', 0):,.2f}")
        print(f"   最终价值: ${report.get('final_value', 0):,.2f}")
        print(f"   总收益率: {report.get('total_return_pct', 0):.2f}%")
        print(f"   绝对收益: ${report.get('total_return_abs', 0):,.2f}")
        
        # 风险调整后指标
        print("\n📈 风险调整后指标:")
        print(f"   年化收益率: {report.get('annualized_return_pct', 0):.2f}%")
        print(f"   年化波动率: {report.get('annualized_volatility_pct', 0):.2f}%")
        print(f"   夏普比率: {report.get('sharpe_ratio', 0):.3f}")
        print(f"   索提诺比率: {report.get('sortino_ratio', 0):.3f}")
        print(f"   卡尔马比率: {report.get('calmar_ratio', 0):.3f}")
        
        # 回撤统计
        print("\n📉 回撤统计:")
        print(f"   最大回撤: {report.get('max_drawdown_pct', 0):.2f}%")
        if report.get('max_drawdown_start') and report.get('max_drawdown_end'):
            start_str = report['max_drawdown_start'].strftime('%Y-%m-%d')
            end_str = report['max_drawdown_end'].strftime('%Y-%m-%d')
            print(f"   回撤期间: {start_str} → {end_str}")
        
        # 交易统计
        print("\n💹 交易统计:")
        print(f"   总交易次数: {report.get('total_trades', 0