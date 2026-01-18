"""
回测绩效分析模块
提供全面的回测结果分析和可视化功能
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
import seaborn as sns
from datetime import datetime, timedelta


@dataclass
class PerformanceMetrics:
    """绩效指标数据类"""
    # 基本指标
    initial_capital: float
    final_portfolio_value: float
    total_return_pct: float
    annualized_return_pct: float
    
    # 风险指标
    volatility_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown_pct: float
    calmar_ratio: float
    
    # 交易统计
    num_trades: int
    num_buy_trades: int
    num_sell_trades: int
    win_rate_pct: float
    profit_factor: float
    avg_trade_return_pct: float
    
    # 持仓统计
    avg_holding_period_days: float
    max_holding_period_days: int
    min_holding_period_days: int
    
    # 策略参数
    rsi_buy_threshold: float
    rsi_sell_threshold: float
    position_size: float
    
    # 时间信息
    start_date: pd.Timestamp
    end_date: pd.Timestamp
    total_days: int


class PerformanceAnalyzer:
    """绩效分析器类"""
    
    def __init__(self, style: str = "seaborn"):
        """
        初始化绩效分析器
        
        Args:
            style: 图表样式，可选 'seaborn', 'matplotlib'
        """
        self.style = style
        self._setup_plotting_style()
    
    def _setup_plotting_style(self) -> None:
        """设置绘图样式"""
        if self.style == "seaborn":
            sns.set_style("whitegrid")
            sns.set_palette("husl")
            plt.rcParams['figure.figsize'] = [12, 8]
            plt.rcParams['font.size'] = 10
        else:
            plt.style.use('default')
    
    def calculate_comprehensive_metrics(
        self,
        backtest_results: pd.DataFrame,
        trades_df: pd.DataFrame,
        initial_capital: float,
        rsi_buy_threshold: float = 20.0,
        rsi_sell_threshold: float = 60.0,
        position_size: float = 1.0
    ) -> PerformanceMetrics:
        """
        计算全面的绩效指标
        
        Args:
            backtest_results: 回测结果数据
            trades_df: 交易记录数据
            initial_capital: 初始资金
            rsi_buy_threshold: RSI买入阈值
            rsi_sell_threshold: RSI卖出阈值
            position_size: 仓位比例
            
        Returns:
            PerformanceMetrics: 绩效指标对象
        """
        if backtest_results.empty:
            raise ValueError("回测结果数据为空")
        
        # 基本数据
        portfolio_values = backtest_results['portfolio_value'].values
        prices = backtest_results['price'].values
        dates = backtest_results.index
        
        # 计算日收益率
        daily_returns = np.diff(portfolio_values) / portfolio_values[:-1]
        
        # 1. 基本收益指标
        total_return = (portfolio_values[-1] - initial_capital) / initial_capital
        total_return_pct = total_return * 100
        
        # 年化收益率
        num_days = len(portfolio_values)
        trading_days_per_year = 252
        annualized_return = (1 + total_return) ** (trading_days_per_year / num_days) - 1
        annualized_return_pct = annualized_return * 100
        
        # 2. 风险指标
        # 波动率（年化）
        volatility = np.std(daily_returns) * np.sqrt(trading_days_per_year) if len(daily_returns) > 0 else 0
        volatility_pct = volatility * 100
        
        # 夏普比率（假设无风险利率为0）
        sharpe_ratio = annualized_return / volatility if volatility > 0 else 0
        
        # 索提诺比率（只考虑下行风险）
        negative_returns = daily_returns[daily_returns < 0]
        downside_std = np.std(negative_returns) * np.sqrt(trading_days_per_year) if len(negative_returns) > 0 else 0
        sortino_ratio = annualized_return / downside_std if downside_std > 0 else 0
        
        # 最大回撤
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (portfolio_values - peak) / peak
        max_drawdown = np.min(drawdown)
        max_drawdown_pct = max_drawdown * 100
        
        # 卡玛比率（年化收益率/最大回撤）
        calmar_ratio = annualized_return / abs(max_drawdown) if max_drawdown != 0 else 0
        
        # 3. 交易统计
        num_trades = len(trades_df) if not trades_df.empty else 0
        num_buy_trades = len(trades_df[trades_df['action'] == 'BUY']) if not trades_df.empty else 0
        num_sell_trades = len(trades_df[trades_df['action'] == 'SELL']) if not trades_df.empty else 0
        
        # 胜率和盈亏比
        win_rate_pct = 0.0
        profit_factor = 0.0
        avg_trade_return_pct = 0.0
        
        if not trades_df.empty and num_sell_trades > 0:
            # 计算每笔交易的盈亏
            trade_returns = []
            buy_trades = trades_df[trades_df['action'] == 'BUY']
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            
            # 假设买入后下一次卖出就是对应的平仓
            for i in range(min(len(buy_trades), len(sell_trades))):
                buy_price = buy_trades.iloc[i]['price']
                sell_price = sell_trades.iloc[i]['price']
                trade_return = (sell_price - buy_price) / buy_price
                trade_returns.append(trade_return)
            
            if trade_returns:
                winning_trades = sum(1 for r in trade_returns if r > 0)
                win_rate_pct = (winning_trades / len(trade_returns)) * 100
                
                # 盈亏比（平均盈利/平均亏损）
                profits = [r for r in trade_returns if r > 0]
                losses = [r for r in trade_returns if r < 0]
                
                avg_profit = np.mean(profits) if profits else 0
                avg_loss = abs(np.mean(losses)) if losses else 0
                profit_factor = avg_profit / avg_loss if avg_loss > 0 else float('inf')
                
                avg_trade_return_pct = np.mean(trade_returns) * 100
        
        # 4. 持仓统计
        avg_holding_period_days = 0
        max_holding_period_days = 0
        min_holding_period_days = 0
        
        if not trades_df.empty and num_buy_trades > 0 and num_sell_trades > 0:
            holding_periods = []
            buy_dates = trades_df[trades_df['action'] == 'BUY']['timestamp']
            sell_dates = trades_df[trades_df['action'] == 'SELL']['timestamp']
            
            for i in range(min(len(buy_dates), len(sell_dates))):
                holding_days = (sell_dates.iloc[i] - buy_dates.iloc[i]).days
                holding_periods.append(holding_days)
            
            if holding_periods:
                avg_holding_period_days = np.mean(holding_periods)
                max_holding_period_days = max(holding_periods)
                min_holding_period_days = min(holding_periods)
        
        # 创建绩效指标对象
        metrics = PerformanceMetrics(
            initial_capital=initial_capital,
            final_portfolio_value=portfolio_values[-1],
            total_return_pct=total_return_pct,
            annualized_return_pct=annualized_return_pct,
            volatility_pct=volatility_pct,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown_pct=max_drawdown_pct,
            calmar_ratio=calmar_ratio,
            num_trades=num_trades,
            num_buy_trades=num_buy_trades,
            num_sell_trades=num_sell_trades,
            win_rate_pct=win_rate_pct,
            profit_factor=profit_factor,
            avg_trade_return_pct=avg_trade_return_pct,
            avg_holding_period_days=avg_holding_period_days,
            max_holding_period_days=max_holding_period_days,
            min_holding_period_days=min_holding_period_days,
            rsi_buy_threshold=rsi_buy_threshold,
            rsi_sell_threshold=rsi_sell_threshold,
            position_size=position_size,
            start_date=dates[0],
            end_date=dates[-1],
            total_days=num_days
        )
        
        return metrics
    
    def generate_performance_report(
        self,
        metrics: PerformanceMetrics,
        output_format: str = "text"
    ) -> str:
        """
        生成绩效报告
        
        Args:
            metrics: 绩效指标
            output_format: 输出格式，'text' 或 'markdown'
            
        Returns:
            str: 绩效报告
        """
        if output_format == "markdown":
            return self._generate_markdown_report(metrics)
        else:
            return self._generate_text_report(metrics)
    
    def _generate_text_report(self, metrics: PerformanceMetrics) -> str:
        """生成文本格式的绩效报告"""
        report = []
        report.append("=" * 60)
        report.append("              RSI策略回测绩效报告")
        report.append("=" * 60)
        report.append("")
        
        # 基本信息
        report.append("【基本信息】")
        report.append(f"回测期间: {metrics.start_date.date()} 到 {metrics.end_date.date()} ({metrics.total_days} 天)")
        report.append(f"初始资金: ${metrics.initial_capital:,.2f}")
        report.append(f"最终组合价值: ${metrics.final_portfolio_value:,.2f}")
        report.append(f"策略参数: RSI买入阈值={metrics.rsi_buy_threshold}, RSI卖出阈值={metrics.rsi_sell_threshold}")
        report.append("")
        
        # 收益指标
        report.append("【收益指标】")
        report.append(f"总收益率: {metrics.total_return_pct:+.2f}%")
        report.append(f"年化收益率: {metrics.annualized_return_pct:+.2f}%")
        report.append("")
        
        # 风险指标
        report.append("【风险指标】")
        report.append(f"年化波动率: {metrics.volatility_pct:.2f}%")
        report.append(f"夏普比率: {metrics.sharpe_ratio:.2f}")
        report.append(f"索提诺比率: {metrics.sortino_ratio:.2f}")
        report.append(f"最大回撤: {metrics.max_drawdown_pct:.2f}%")
        report.append(f"卡玛比率: {metrics.calmar_ratio:.2f}")
        report.append("")
        
        # 交易统计
        report.append("【交易统计】")
        report.append(f"总交易次数: {metrics.num_trades}")
        report.append(f"买入次数: {metrics.num_buy_trades}")
        report.append(f"卖出次数: {metrics.num_sell_trades}")
        report.append(f"胜率: {metrics.win_rate_pct:.2f}%")
        report.append(f"盈亏比: {metrics.profit_factor:.2f}")
        report.append(f"平均交易收益率: {metrics.avg_trade_return_pct:+.2f}%")
        report.append("")
        
        # 持仓统计
        report.append("【持仓统计】")
        report.append(f"平均持仓天数: {metrics.avg_holding_period_days:.1f} 天")
        report.append(f"最长持仓天数: {metrics.max_holding_period_days} 天")
        report.append(f"最短持仓天数: {metrics.min_holding_period_days} 天")
        report.append("")
        
        # 绩效评估
        report.append("【绩效评估】")
        if metrics.sharpe_ratio > 1.0:
            report.append("✓ 夏普比率 > 1.0，风险调整后收益良好")
        else:
            report.append("⚠ 夏普比率 < 1.0，风险调整后收益一般")
        
        if metrics.max_drawdown_pct > -20:
            report.append("✓ 最大回撤 < 20%，风险控制良好")
        else:
            report.append("⚠ 最大回撤 > 20%，风险较高")
        
        if metrics.win_rate_pct > 50:
            report.append("✓ 胜率 > 50%，策略稳定性较好")
        else:
            report.append("⚠ 胜率 < 50%，策略稳定性一般")
        
        report.append("")
        report.append("=" * 60)
        
        return "\n".join(report)
    
    def _generate_markdown_report(self, metrics: PerformanceMetrics) -> str:
        """生成Markdown格式的绩效报告"""
        report = []
        report.append("# RSI策略回测绩效报告")
        report.append("")
        
        # 基本信息
        report.append("## 基本信息")
        report.append(f"- **回测期间**: {metrics.start_date.date()} 到 {metrics.end_date.date()} ({metrics.total_days} 天)")
        report.append(f"- **初始资金**: ${metrics.initial_capital:,.2f}")
        report.append(f"- **最终组合价值**: ${metrics.final_portfolio_value:,.2f}")
        report.append(f"- **策略参数**: RSI买入阈值={metrics.rsi_buy_threshold}, RSI卖出阈值={metrics.rsi_sell_threshold}")
        report.append("")
        
        # 收益指标
        report.append("## 收益指标")
        report.append(f"- **总收益率**: {metrics.total_return_pct:+.2f}%")
        report.append(f"- **年化收益率**: {metrics.annualized_return_pct:+.2f}%")
        report.append("")
        
        # 风险指标
        report.append("## 风险指标")
        report.append(f"- **年化波动率**: {metrics.volatility_pct:.2f}%")
        report.append(f"- **夏普比率**: {metrics.sharpe_ratio:.2f}")
        report.append(f"- **索提诺比率**: {metrics.sortino_ratio:.2f}")
        report.append(f"- **最大回撤**: {metrics.max_drawdown_pct:.2f}%")
        report.append(f"- **卡玛比率**: {metrics.calmar_ratio:.2f}")
        report.append("")
        
        # 交易统计
        report.append("## 交易统计")
        report.append(f"- **总交易次数**: {metrics.num_trades}")
        report.append(f"- **买入次数**: {metrics.num_buy_trades}")
        report.append(f"- **卖出次数**: {metrics.num_sell_trades}")
        report.append(f"- **胜率**: {metrics.win_rate_pct:.2f}%")
        report.append(f"- **盈亏比**: {metrics.profit_factor:.2f}")
        report.append(f"- **平均交易收益率**: {metrics.avg_trade_return_pct:+.2f}%")
        report.append("")
        
        # 持仓统计
        report.append("## 持仓统计")
        report.append(f"- **平均持仓天数**: {metrics.avg_holding_period_days:.1f} 天")
        report.append(f"- **最长持仓天数**: {metrics.max_holding_period_days} 天")
        report.append(f"- **最短持仓天数**: {metrics.min_holding_period_days} 天")
        report.append("")
        
        # 绩效评估
        report.append("## 绩效评估")
        if metrics.sharpe_ratio > 1.0:
            report.append("✅ **夏普比率 > 1.0**，风险调整后收益良好")
        else:
            report.append("⚠️ **夏普比率 < 1.0**，风险调整后收益一般")
        
        if metrics.max_drawdown_pct > -20:
            report.append("✅ **最大回撤 < 20%**，风险控制良好")
        else:
            report.append("⚠️ **最大回撤 > 20%**，风险较高")
        
        if metrics.win_rate_pct > 50:
            report.append("✅ **胜率 > 50%**，策略稳定性较好")
        else:
            report.append("⚠️ **胜率 < 50%**，策略稳定性一般")
        
        return "\n".join(report)
    
    def plot_performance_charts(
        self,
        backtest_results: pd.DataFrame,
        trades_df: pd.DataFrame,
        metrics: PerformanceMetrics,
        save_path: Optional[str] = None
    ) -> None:
        """
        绘制绩效图表
        
        Args:
            backtest_results: 回测结果数据
            trades_df: 交易记录数据
            metrics: 绩效指标
            save_path: 保存路径（可选）
        """
        fig, axes = plt.subplots(3, 2, figsize=(15, 12))
        
        # 1. 投资组合价值曲线
        ax1 = axes[0, 0]
        ax1.plot(backtest_results.index, backtest_results['portfolio_value'], 
                label='投资组合价值', linewidth=2, color='blue')
        ax1.set_title('投资组合价值曲线', fontsize=12, fontweight='bold')
        ax1.set_xlabel('日期')
        ax1.set_ylabel('组合价值 ($)')
        ax1.grid(True, alpha=0.3)
        ax1.legend()
        
        # 在买入点标记
        if not trades_df.empty:
            buy_trades = trades_df[trades_df['action'] == 'BUY']
            if not buy_trades.empty:
                ax1.scatter(buy_trades['timestamp'], 
                          backtest_results.loc[buy_trades['timestamp'], 'portfolio_value'], 
                          color='green', s=100, marker='^', label='买入点', zorder=5)
            
            # 在卖出点标记
            sell_trades = trades_df[trades_df['action'] == 'SELL']
            if not sell_trades.empty:
                ax1.scatter(sell_trades['timestamp'], 
                          backtest_results.loc[sell_trades['timestamp'], 'portfolio_value'], 
                          color='red', s=100, marker='v', label='卖出点', zorder=5)
        
        # 2. 价格和RSI曲线
        ax2 = axes[0, 1]
        ax2.plot(backtest_results.index, backtest_results['price'], 
                label='价格', linewidth=2, color='orange')
        ax2.set_title('价格走势', fontsize=12, fontweight='bold')
        ax2.set_xlabel('日期')
        ax2.set_ylabel('价格 ($)')
        ax2.grid(True, alpha=0.3)
        ax2.legend(loc='upper left')
        
        # 添加RSI子图
        ax2_rsi = ax2.twinx()
        ax2_rsi.plot(backtest_results.index, backtest_results['rsi'], 
                    label='RSI(14)', linewidth=1.5, color='purple', alpha=0.7)
        ax2_rsi.set_ylabel('RSI')
        ax2_rsi.axhline(y=metrics.rsi_buy_threshold, color='green', 
                       linestyle='--', alpha=0.5, label=f'买入阈值({metrics.rsi_buy_threshold})')
        ax2_rsi.axhline(y=metrics.rsi_sell_threshold, color='red', 
                       linestyle='--', alpha=0.5, label=f'卖出阈值({metrics.rsi_sell_threshold})')
        ax2_rsi.set_ylim(0, 100)
        ax2_rsi.legend(loc='upper right')
        
        # 3. 收益率分布
        ax3 = axes[1, 0]
        daily_returns = np.diff(backtest_results['portfolio_value']) / backtest_results['portfolio_value'].values[:-1]
        ax3.hist(daily_returns * 100, bins=30, edgecolor='black', alpha=0.7)
        ax3.set_title('日收益率分布', fontsize=12, fontweight='bold')
        ax3.set_xlabel('日收益率 (%)')
        ax3.set_ylabel('频次')
        ax3.grid(True, alpha=0.3)
        
        # 添加统计信息
        mean_return = np.mean(daily_returns) * 100
        std_return = np.std(daily_returns) * 100
        ax3.axvline(mean_return, color='red', linestyle='--', 
                   label=f'均值: {mean_return:.2f}%')
        ax3.axvline(mean_return + std_return, color='orange', linestyle=':', 
                   label=f'±1σ: {std_return:.2f}%')
        ax3.axvline(mean_return - std_return, color='orange', linestyle=':')
        ax3.legend()
        
        # 4. 回撤曲线
        ax4 = axes[1, 1]
        portfolio_values = backtest_results['portfolio_value'].values
        peak = np.maximum.accumulate(portfolio_values)
        drawdown = (portfolio_values - peak) / peak * 100
        
        ax4.fill_between(backtest_results.index, drawdown, 0, 
                        where=drawdown < 0, color='red', alpha=0.3)
        ax4.plot(backtest_results.index, drawdown, color='red', linewidth=1.5)
        ax4.set_title('回撤曲线', fontsize=12, fontweight='bold')
        ax4.set_xlabel('日期')
        ax4.set_ylabel('回撤 (%)')
        ax4.grid(True, alpha=0.3)
        
        # 标记最大回撤
        max_dd_idx = np.argmin(drawdown)
        max_dd_value = drawdown[max_dd_idx]
        max_dd_date = backtest_results.index[max_dd_idx]
        
        ax4.scatter(max_dd_date, max_dd_value, color='darkred', s=100, 
                   zorder=5, label=f'最大回撤: {max_dd_value:.2f}%')
        ax4.legend()
        
        # 5. 月度收益率热力图
        ax5 = axes[2, 0]
        
        # 计算月度收益率
        backtest_results['month'] = backtest_results.index.strftime('%Y-%m')
        monthly_returns = backtest_results.groupby('month')['portfolio_value'].apply(
            lambda x: (x.iloc[-1] - x.iloc[0]) / x.iloc[0] * 100
        )
        
        # 创建月度收益率矩阵
        monthly_matrix = []
        months = sorted(monthly_returns.index.unique())
        years = sorted(set(m[:4] for m in months))
        
        for year in years:
            year_returns = []
            for month in range(1, 13):
                month_str = f'{year}-{month:02d}'
                if month_str in monthly_returns.index:
                    year_returns.append(monthly_returns[month_str])
                else:
                    year_returns.append(np.nan)
            monthly_matrix.append(year_returns)
        
        # 绘制热力图
        if monthly_matrix:
            im = ax5.imshow(monthly_matrix, cmap='RdYlGn', aspect='auto')
            ax5.set_title('月度收益率热力图 (%)', fontsize=12, fontweight='bold')
            ax5.set_xlabel('月份')
            ax5.set_ylabel('年份')
            
            # 设置坐标轴标签
            ax5.set_xticks(range(12))
            ax5.set_xticklabels(['1月', '2月', '3月', '4月', '5月', '6月', 
                               '7月', '8月', '9月', '10月', '11月', '12月'])
            ax5.set_yticks(range(len(years)))
            ax5.set_yticklabels(years)
            
            # 添加颜色条
            plt.colorbar(im, ax=ax5)
        else:
            ax5.text(0.5, 0.5, '数据不足\n无法生成月度热力图', 
                    ha='center', va='center', transform=ax5.transAxes)
            ax5.set_title('月度收益率热力图', fontsize=12, fontweight='bold')
        
        # 6. 关键指标展示
        ax6 = axes[2, 1]
        ax6.axis('off')
        
        # 创建指标文本
        metrics_text = (
            f'关键绩效指标\n'
            f'\n'
            f'总收益率: {metrics.total_return_pct:+.2f}%\n'
            f'年化收益率: {metrics.annualized_return_pct:+.2f}%\n'
            f'夏普比率: {metrics.sharpe_ratio:.2f}\n'
            f'最大回撤: {metrics.max_drawdown_pct:.2f}%\n'
            f'年化波动率: {metrics.volatility_pct:.2f}%\n'
            f'胜率: {metrics.win_rate_pct:.2f}%\n'
            f'交易次数: {metrics.num_trades}\n'
            f'平均持仓天数: {metrics.avg_holding_period_days:.1f}'
        )
        
        ax6.text(0.1, 0.95, metrics_text, transform=ax6.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))
        
        # 调整布局
        plt.tight_layout()
        
        if save_path:
            plt.savefig(save_path, dpi=300, bbox_inches='tight')
            print(f'图表已保存到: {save_path}')
        
        plt.show()
    
    def export_results_to_excel(
        self,
        backtest_results: pd.DataFrame,
        trades_df: pd.DataFrame,
        metrics: PerformanceMetrics,
        output_path: str = 'backtest_results.xlsx'
    ) -> None:
        """
        将回测结果导出到Excel文件
        
        Args:
            backtest_results: 回测结果数据
            trades_df: 交易记录数据
            metrics: 绩效指标
            output_path: 输出文件路径
        """
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # 1. 回测结果明细
            backtest_results.to_excel(writer, sheet_name='回测明细')
            
            # 2. 交易记录
            if not trades_df.empty:
                trades_df.to_excel(writer, sheet_name='交易记录', index=False)
            
            # 3. 绩效指标
            metrics_dict = {
                '指标名称': [
                    '初始资金', '最终组合价值', '总收益率(%)', '年化收益率(%)',
                    '年化波动率(%)', '夏普比率', '索提诺比率', '最大回撤(%)',
                    '卡玛比率', '总交易次数', '买入次数', '卖出次数',
                    '胜率(%)', '盈亏比', '平均交易收益率(%)',
                    '平均持仓天数', '最长持仓天数', '最短持仓天数',
                    'RSI买入阈值', 'RSI卖出阈值', '仓位比例',
                    '开始日期', '结束日期', '总天数'
                ],
                '指标值': [
                    metrics.initial_capital,
                    metrics.final_portfolio_value,
                    metrics.total_return_pct,
                    metrics.annualized_return_pct,
                    metrics.volatility_pct,
                    metrics.sharpe_ratio,
                    metrics.sortino_ratio,
                    metrics.max_drawdown_pct,
                    metrics.calmar_ratio,
                    metrics.num_trades,
                    metrics.num_buy_trades,
                    metrics.num_sell_trades,
                    metrics.win_rate_pct,
                    metrics.profit_factor,
                    metrics.avg_trade_return_pct,
                    metrics.avg_holding_period_days,
                    metrics.max_holding_period_days,
                    metrics.min_holding_period_days,
                    metrics.rsi_buy_threshold,
                    metrics.rsi_sell_threshold,
                    metrics.position_size,
                    metrics.start_date.strftime('%Y-%m-%d'),
                    metrics.end_date.strftime('%Y-%m-%d'),
                    metrics.total_days
                ]
            }
            
            metrics_df = pd.DataFrame(metrics_dict)
            metrics_df.to_excel(writer, sheet_name='绩效指标', index=False)
            
            # 4. 策略说明
            strategy_desc = pd.DataFrame({
                '项目': ['策略名称', '策略逻辑', '数据源', '回测周期', '注意事项'],
                '说明': [
                    'RSI超买超卖策略',
                    '当RSI(14) < 20时买入，买入后当RSI(14) > 60时卖出',
                    'yfinance BTC-USD数据',
                    f'{metrics.start_date.date()} 到 {metrics.end_date.date()}',
                    '假设无风险利率为0，未考虑税收和流动性风险'
                ]
            })
            strategy_desc.to_excel(writer, sheet_name='策略说明', index=False)
        
        print(f'回测结果已导出到: {output_path}')


def analyze_backtest_performance(
    backtest_results: pd.DataFrame,
    trades_df: pd.DataFrame,
    initial_capital: float = 10000.0,
    rsi_buy_threshold: float = 20.0,
    rsi_sell_threshold: float = 60.0,
    position_size: float = 1.0,
    generate_report: bool = True,
    generate_charts: bool = True,
    export_excel: bool = True
) -> PerformanceMetrics:
    """
    分析回测绩效的便捷函数
    
    Args:
        backtest_results: 回测结果数据
        trades_df: 交易记录数据
        initial_capital: 初始资金
        rsi_buy_threshold: RSI买入阈值
        rsi_sell_threshold: RSI卖出阈值
        position_size: 仓位比例
        generate_report: 是否生成报告
        generate_charts: 是否生成图表
        export_excel: 是否导出Excel
        
    Returns:
        PerformanceMetrics: 绩效指标
    """
    # 创建分析器
    analyzer = PerformanceAnalyzer()
    
    # 计算绩效指标
    metrics = analyzer.calculate_comprehensive_metrics(
        backtest_results=backtest_results,
        trades_df=trades_df,
        initial_capital=initial_capital,
        rsi_buy_threshold=rsi_buy_threshold,
        rsi_sell_threshold=rsi_sell_threshold,
        position_size=position_size
    )
    
    # 生成报告
    if generate_report:
        report = analyzer.generate_performance_report(metrics, output_format='text')
        print(report)
    
    # 生成图表
    if generate_charts:
        analyzer.plot_performance_charts(backtest_results, trades_df, metrics)
    
    # 导出Excel
    if export_excel:
        analyzer.export_results_to_excel(backtest_results, trades_df, metrics)
    
    return metrics


if __name__ == "__main__":
    # 测试绩效分析器
    print("测试绩效分析器...")
    
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
    
    # 运行绩效分析
    print("运行绩效分析...")
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
    
    print(f"\n绩效分析完成！关键指标:")
    print(f"总收益率: {metrics.total_return_pct:.2f}%")
    print(f"夏普比率: {metrics.sharpe_ratio:.2f}")
    print(f"最大回撤: {metrics.max_drawdown_pct:.2f}%")
    print(f"胜率: {metrics.win_rate_pct:.2f}%")
       