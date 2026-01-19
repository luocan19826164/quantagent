"""
回测结果可视化模块
绘制资产曲线、RSI指标图、买卖点标记等
"""

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from typing import Dict, List, Optional, Tuple
import logging
from datetime import datetime

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 设置中文字体支持
plt.rcParams['font.sans-serif'] = ['Arial Unicode MS', 'DejaVu Sans', 'SimHei']  # 支持中文的字体
plt.rcParams['axes.unicode_minus'] = False  # 正确显示负号


class BacktestVisualizer:
    """回测结果可视化器"""
    
    def __init__(self, figsize: Tuple[int, int] = (12, 10)):
        """
        初始化可视化器
        
        Args:
            figsize: 图形大小，默认为(12, 10)
        """
        self.figsize = figsize
        self.colors = {
            'buy': 'green',
            'sell': 'red',
            'price': 'blue',
            'rsi': 'purple',
            'portfolio': 'darkorange',
            'oversold': 'lightcoral',
            'overbought': 'lightgreen',
            'neutral': 'lightgray'
        }
    
    def plot_backtest_results(self, result_data: pd.DataFrame, trades: List, 
                             title: str = "RSI策略回测结果") -> plt.Figure:
        """
        绘制完整的回测结果图表
        
        Args:
            result_data: 包含回测结果的DataFrame
            trades: 交易记录列表
            title: 图表标题
            
        Returns:
            matplotlib图形对象
        """
        # 创建子图布局
        fig = plt.figure(figsize=self.figsize)
        
        # 创建3个子图：价格+买卖点、RSI、资产曲线
        gs = fig.add_gridspec(3, 1, height_ratios=[2, 1, 1], hspace=0.3)
        
        # 子图1: 价格和买卖点
        ax1 = fig.add_subplot(gs[0])
        self._plot_price_with_trades(ax1, result_data, trades)
        
        # 子图2: RSI指标
        ax2 = fig.add_subplot(gs[1])
        self._plot_rsi_indicator(ax2, result_data)
        
        # 子图3: 资产曲线
        ax3 = fig.add_subplot(gs[2])
        self._plot_portfolio_value(ax3, result_data)
        
        # 设置总标题
        fig.suptitle(title, fontsize=16, fontweight='bold')
        
        plt.tight_layout()
        return fig
    
    def _plot_price_with_trades(self, ax: plt.Axes, data: pd.DataFrame, trades: List) -> None:
        """
        绘制价格曲线和买卖点
        
        Args:
            ax: matplotlib坐标轴
            data: 包含价格数据的DataFrame
            trades: 交易记录列表
        """
        # 绘制价格曲线
        if 'Close' in data.columns:
            ax.plot(data.index, data['Close'], color=self.colors['price'], 
                   linewidth=1.5, label='收盘价')
        
        # 标记买卖点
        buy_dates = []
        buy_prices = []
        sell_dates = []
        sell_prices = []
        
        for trade in trades:
            if trade.trade_type == 'buy':
                buy_dates.append(trade.timestamp)
                buy_prices.append(trade.price)
            elif trade.trade_type == 'sell':
                sell_dates.append(trade.timestamp)
                sell_prices.append(trade.price)
        
        # 绘制买入点
        if buy_dates:
            ax.scatter(buy_dates, buy_prices, color=self.colors['buy'], 
                      s=100, marker='^', label='买入点', zorder=5)
        
        # 绘制卖出点
        if sell_dates:
            ax.scatter(sell_dates, sell_prices, color=self.colors['sell'], 
                      s=100, marker='v', label='卖出点', zorder=5)
        
        # 设置坐标轴格式
        ax.set_ylabel('价格 (USD)', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
        
        # 添加网格
        ax.grid(True, alpha=0.3)
    
    def _plot_rsi_indicator(self, ax: plt.Axes, data: pd.DataFrame) -> None:
        """
        绘制RSI指标
        
        Args:
            ax: matplotlib坐标轴
            data: 包含RSI数据的DataFrame
        """
        if 'RSI' not in data.columns:
            logger.warning("数据中未找到RSI列")
            return
        
        # 绘制RSI曲线
        ax.plot(data.index, data['RSI'], color=self.colors['rsi'], 
               linewidth=1.5, label='RSI(14)')
        
        # 添加超买超卖区域
        ax.axhline(y=20, color=self.colors['oversold'], linestyle='--', 
                  alpha=0.7, label='超卖线 (20)')
        ax.axhline(y=60, color=self.colors['overbought'], linestyle='--', 
                  alpha=0.7, label='卖出线 (60)')
        ax.axhline(y=80, color=self.colors['overbought'], linestyle=':', 
                  alpha=0.5, label='超买线 (80)')
        
        # 填充超卖区域
        ax.fill_between(data.index, 0, 20, color=self.colors['oversold'], 
                       alpha=0.1, label='超卖区域')
        
        # 填充超买区域
        ax.fill_between(data.index, 80, 100, color=self.colors['overbought'], 
                       alpha=0.1, label='超买区域')
        
        # 设置坐标轴
        ax.set_ylabel('RSI', fontsize=12)
        ax.set_ylim(0, 100)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best', fontsize='small')
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    def _plot_portfolio_value(self, ax: plt.Axes, data: pd.DataFrame) -> None:
        """
        绘制资产曲线
        
        Args:
            ax: matplotlib坐标轴
            data: 包含资产价值数据的DataFrame
        """
        if 'Portfolio_Value' not in data.columns:
            logger.warning("数据中未找到Portfolio_Value列")
            return
        
        # 绘制资产曲线
        ax.plot(data.index, data['Portfolio_Value'], color=self.colors['portfolio'], 
               linewidth=2, label='投资组合价值')
        
        # 绘制初始资金参考线
        if 'Portfolio_Value' in data.columns and len(data) > 0:
            initial_value = data['Portfolio_Value'].iloc[0]
            ax.axhline(y=initial_value, color='gray', linestyle='--', 
                      alpha=0.5, label=f'初始资金: ${initial_value:,.0f}')
        
        # 设置坐标轴
        ax.set_ylabel('资产价值 (USD)', fontsize=12)
        ax.set_xlabel('日期', fontsize=12)
        ax.grid(True, alpha=0.3)
        ax.legend(loc='best')
        
        # 格式化x轴日期
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45)
    
    def plot_trade_analysis(self, trades: List, initial_capital: float = 10000.0) -> plt.Figure:
        """
        绘制交易分析图表
        
        Args:
            trades: 交易记录列表
            initial_capital: 初始资金
            
        Returns:
            matplotlib图形对象
        """
        if not trades:
            logger.warning("没有交易记录可分析")
            return None
        
        # 提取交易信息
        trade_data = []
        for trade in trades:
            trade_data.append({
                'date': trade.timestamp,
                'type': trade.trade_type,
                'price': trade.price,
                'quantity': trade.quantity,
                'amount': trade.amount,
                'rsi': trade.rsi_value
            })
        
        trades_df = pd.DataFrame(trade_data)
        
        # 创建图形
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        
        # 子图1: 交易金额分布
        ax1 = axes[0, 0]
        buy_amounts = trades_df[trades_df['type'] == 'buy']['amount'].abs()
        sell_amounts = trades_df[trades_df['type'] == 'sell']['amount']
        
        if not buy_amounts.empty:
            ax1.hist(buy_amounts, bins=10, alpha=0.7, color=self.colors['buy'], 
                    label='买入金额')
        if not sell_amounts.empty:
            ax1.hist(sell_amounts, bins=10, alpha=0.7, color=self.colors['sell'], 
                    label='卖出金额')
        
        ax1.set_xlabel('交易金额 (USD)')
        ax1.set_ylabel('频次')
        ax1.set_title('交易金额分布')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # 子图2: 交易RSI值分布
        ax2 = axes[0, 1]
        buy_rsi = trades_df[trades_df['type'] == 'buy']['rsi'].dropna()
        sell_rsi = trades_df[trades_df['type'] == 'sell']['rsi'].dropna()
        
        if not buy_rsi.empty:
            ax2.hist(buy_rsi, bins=10, alpha=0.7, color=self.colors['buy'], 
                    label='买入RSI')
        if not sell_rsi.empty:
            ax2.hist(sell_rsi, bins=10, alpha=0.7, color=self.colors['sell'], 
                    label='卖出RSI')
        
        ax2.set_xlabel('RSI值')
        ax2.set_ylabel('频次')
        ax2.set_title('交易RSI值分布')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # 子图3: 交易时间分布
        ax3 = axes[1, 0]
        trades_df['month'] = trades_df['date'].dt.to_period('M')
        monthly_trades = trades_df.groupby(['month', 'type']).size().unstack(fill_value=0)
        
        if not monthly_trades.empty:
            monthly_trades.plot(kind='bar', ax=ax3, color=[self.colors['buy'], self.colors['sell']])
        
        ax3.set_xlabel('月份')
        ax3.set_ylabel('交易次数')
        ax3.set_title('月度交易分布')
        ax3.legend(['买入', '卖出'])
        ax3.grid(True, alpha=0.3)
        plt.setp(ax3.xaxis.get_majorticklabels(), rotation=45)
        
        # 子图4: 累计收益曲线
        ax4 = axes[1, 1]
        # 计算每次交易后的累计收益
        cumulative_cash = [initial_capital]
        for trade in trades:
            if trade.trade_type == 'buy':
                cumulative_cash.append(cumulative_cash[-1] + trade.amount)
            elif trade.trade_type == 'sell':
                cumulative_cash.append(cumulative_cash[-1] + trade.amount)
        
        trade_dates = [trade.timestamp for trade in trades]
        if cumulative_cash:
            ax4.plot(trade_dates, cumulative_cash[1:], marker='o', 
                    color=self.colors['portfolio'], linewidth=2)
            ax4.axhline(y=initial_capital, color='gray', linestyle='--', 
                       alpha=0.5, label='初始资金')
        
        ax4.set_xlabel('日期')
        ax4.set_ylabel('现金余额 (USD)')
        ax4.set_title('交易现金余额变化')
        ax4.legend()
        ax4.grid(True, alpha=0.3)
        plt.setp(ax4.xaxis.get_majorticklabels(), rotation=45)
        
        fig.suptitle('交易分析', fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        return fig
    
    def plot_performance_metrics(self, stats: Dict, title: str = "回测性能指标") -> plt.Figure:
        """
        绘制性能指标图表
        
        Args:
            stats: 性能指标字典
            title: 图表标题
            
        Returns:
            matplotlib图形对象
        """
        # 提取关键指标
        key_metrics = {
            '总收益率 (%)': stats.get('total_return_pct', 0),
            '年化收益率 (%)': stats.get('annualized_return_pct', 0),
            '夏普比率': stats.get('sharpe_ratio', 0),
            '最大回撤 (%)': stats.get('max_drawdown_pct', 0),
            '胜率 (%)': stats.get('win_rate_pct', 0),
            '交易次数': stats.get('total_trades', 0)
        }
        
        # 创建图形
        fig, axes = plt.subplots(1, 2, figsize=(14, 6))
        
        # 子图1: 关键指标条形图
        ax1 = axes[0]
        metrics_names = list(key_metrics.keys())
        metrics_values = list(key_metrics.values())
        
        # 设置颜色（正收益为绿色，负收益为红色）
        colors = []
        for name, value in zip(metrics_names, metrics_values):
            if '收益率' in name or '胜率' in name or '夏普' in name:
                colors.append('green' if value >= 0 else 'red')
            elif '回撤' in name:
                colors.append('red' if value < 0 else 'lightgray')
            else:
                colors.append('steelblue')
        
        bars = ax1.bar(metrics_names, metrics_values, color=colors, alpha=0.7)
        
        # 添加数值标签
        for bar, value in zip(bars, metrics_values):
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 0.01 * max(metrics_values),
                    f'{value:.2f}', ha='center', va='bottom', fontsize=10)
        
        ax1.set_ylabel('数值')
        ax1.set_title('关键性能指标')
        ax1.grid(True, alpha=0.3, axis='y')
        plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
        
        # 子图2: 交易统计饼图
        ax2 = axes[1]
        trade_stats = {
            '买入交易': stats.get('buy_trades', 0),
            '卖出交易': stats.get('sell_trades', 0),
            '盈利交易': stats.get('winning_trades', 0),
            '亏损交易': stats.get('losing_trades', 0)
        }
        
        # 过滤掉值为0的项
        trade_stats = {k: v for k, v in trade_stats.items() if v > 0}
        
        if trade_stats:
            colors_pie = [self.colors['buy'], self.colors['sell'], 'lightgreen', 'lightcoral']
            wedges, texts, autotexts = ax2.pie(
                list(trade_stats.values()), 
                labels=list(trade_stats.keys()),
                autopct='%1.1f%%',
                colors=colors_pie[:len(trade_stats)],
                startangle=90
            )
            
            # 美化百分比文本
            for autotext in autotexts:
                autotext.set_color('white')
                autotext.set_fontweight('bold')
            
            ax2.set_title('交易统计')
        else:
            ax2.text(0.5, 0.5, '无交易数据', ha='center', va='center', 
                    transform=ax2.transAxes, fontsize=12)
            ax2.set_title('交易统计 (无数据)')
        
        fig.suptitle(title, fontsize=16, fontweight='bold')
        plt.tight_layout()
        
        return fig
    
    def save_plots(self, fig: plt.Figure, filename: str, dpi: int = 300) -> None:
        """
        保存图表到文件
        
        Args:
            fig: matplotlib图形对象
            filename: 保存的文件名
            dpi: 图像分辨率，默认为300
        """
        fig.savefig(filename, dpi=dpi, bbox_inches='tight')
        logger.info(f"图表已保存到: {filename}")


def create_visualization_report(result_data: pd.DataFrame, trades: List, 
                               stats: Dict, output_dir: str = "reports") -> None:
    """
    创建完整的可视化报告
    
    Args:
        result_data: 回测结果数据
        trades: 交易记录列表
        stats: 性能统计信息
        output_dir: 输出目录
    """
    import os
    
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 创建可视化器
    visualizer = BacktestVisualizer()
    
    # 1. 绘制完整的回测结果图表
    print("生成回测结果图表...")
    fig1 = visualizer.plot_backtest_results(result_data, trades, 
                                          title="比特币RSI策略回测结果")
    visualizer.save_plots(fig1, os.path.join(output_dir, "backtest_results.png"))
    
    # 2. 绘制交易分析图表
    if trades:
        print("生成交易分析图表...")
        fig2 = visualizer.plot_trade_analysis(trades, stats.get('initial_capital', 10000.0))
        if fig2:
            visualizer.save_plots(fig2, os.path.join(output_dir, "trade_analysis.png"))
    
    # 3. 绘制性能指标图表
    print("生成性能指标图表...")
    fig3 = visualizer.plot_performance_metrics(stats, title="回测性能指标总结")
    visualizer.save_plots(fig3, os.path.join(output_dir, "performance_metrics.png"))
    
    # 4. 创建汇总报告
    print("生成汇总报告...")
    create_summary_report(stats, trades, output_dir)
    
    print(f"✓ 可视化报告已保存到目录: {output_dir}")


def create_summary_report(stats: Dict, trades: List, output_dir: str) -> None:
    """
    创建文本格式的汇总报告
    
    Args:
        stats: 性能统计信息
        trades: 交易记录列表
        output_dir: 输出目录
    """
    import os
    
    report_path = os.path.join(output_dir, "summary_report.txt")
    
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write("=" * 60 + "\n")
        f.write("比特币RSI策略回测汇总报告\n")
        f.write("=" * 60 + "\n\n")
        
        # 基本统计信息
        f.write("【基本统计信息】\n")
        f.write("-" * 40 + "\n")
        f.write(f"初始资金: ${stats.get('initial_capital', 0):,.2f}\n")
        f.write(f"最终价值: ${stats.get('final_value', 0):,.2f}\n")
        f.write(f"总收益率: {stats.get('total_return_pct', 0):.2f}%\n")
        f.write(f"年化收益率: {stats.get('annualized_return_pct', 0):.2f}%\n")
        f.write(f"夏普比率: {stats.get('sharpe_ratio', 0):.2f}\n")
        f.write(f"最大回撤: {stats.get('max_drawdown_pct', 0):.2f}%\n")
        f.write(f"胜率: {stats.get('win_rate_pct', 0):.1f}%\n")
        f.write(f"交易次数: {stats.get('total_trades', 0)} 次\n")
        f.write(f"买入交易: {stats.get('buy_trades', 0)} 次\n")
        f.write(f"卖出交易: {stats.get('sell_trades', 0)} 次\n")
        f.write(f"盈利交易: {stats.get('winning_trades', 0)} 次\n")
        f.write(f"亏损交易: {stats.get('losing_trades', 0)} 次\n\n")
        
        # 交易记录
        if trades:
            f.write("【交易记录】\n")
            f.write("-" * 40 + "\n")
            
            for i, trade in enumerate(trades, 1):
                date_str = trade.timestamp.strftime('%Y-%m-%d')
                rsi_str = f"RSI={trade.rsi_value:.2f}" if trade.rsi_value else "RSI=N/A"
                
                f.write(f"{i:2d}. {date_str}: {trade.trade_type.upper():4s} ")
                f.write(f"@ ${trade.price:,.2f}, 数量={trade.quantity:.4f}, ")
                f.write(f"金额=${trade.amount:,.2f}, {rsi_str}\n")
            
            f.write("\n")
        
        # 策略规则
        f.write("【策略规则】\n")
        f.write("-" * 40 + "\n")
        f.write("1. 买入条件: RSI < 20 (超卖区域)\n")
        f.write("2. 卖出条件: 买入后RSI > 60\n")
        f.write("3. 交易佣金: 0.1% (默认)\n")
        f.write("4. 初始资金: $10,000 (默认)\n\n")
        
        # 性能评估
        f.write("【性能评估】\n")
        f.write("-" * 40 + "\n")
        
        total_return = stats.get('total_return_pct', 0)
        if total_return > 0:
            f.write("✓ 策略实现正收益\n")
        else:
            f.write("✗ 策略收益为负\n")
            
        win_rate = stats.get('win_rate_pct', 0)
        if win_rate > 50:
            f.write("✓ 胜率超过50%\n")
        else:
            f.write("✗ 胜率低于50%\n")
            
        max_drawdown = stats.get('max_drawdown_pct', 0)
        if abs(max_drawdown) < 20:
            f.write("✓ 最大回撤控制在20%以内\n")
        else:
            f.write("✗ 最大回撤超过20%\n")
            
        sharpe_ratio = stats.get('sharpe_ratio', 0)
        if sharpe_ratio > 1:
            f.write("✓ 夏普比率大于1 (风险调整后收益良好)\n")
        elif sharpe_ratio > 0:
            f.write("⚠ 夏普比率为正但小于1\n")
        else:
            f.write("✗ 夏普比率为负\n")
        
        f.write("\n" + "=" * 60 + "\n")
        f.write("报告生成时间: " + pd.Timestamp.now().strftime('%Y-%m-%d %H:%M:%S') + "\n")
        f.write("=" * 60 + "\n")
    
    print(f"✓ 汇总报告已保存到: {report_path}")


# 测试函数
if __name__ == "__main__":
    print("可视化模块测试")
    print("=" * 50)
    
    # 创建测试数据
    np.random.seed(42)
    n = 100
    dates = pd.date_range('2024-01-01', periods=n, freq='D')
    
    # 创建测试价格数据
    prices = 100 * (1 + np.cumsum(np.random.normal(0.001, 0.02, n)))
    rsi_values = 50 + 30 * np.sin(2 * np.pi * np.arange(n) / 20)
    
    # 创建测试DataFrame
    test_data = pd.DataFrame({
        'Close': prices,
        'RSI': rsi_values,
        'Portfolio_Value': 10000 * (1 + np.cumsum(np.random.normal(0.0005, 0.01, n)))
    }, index=dates)
    
    # 创建测试交易记录
    test_trades = []
    for i in range(5):
        trade_type = 'buy' if i % 2 == 0 else 'sell'
        trade = type('Trade', (), {
            'trade_type': trade_type,
            'timestamp': dates[i*20],
            'price': prices[i*20],
            'quantity': 1.0,
            'amount': prices[i*20] * (1 if trade_type == 'sell' else -1),
            'rsi_value': rsi_values[i*20]
        })()
        test_trades.append(trade)
    
    # 创建测试统计信息
    test_stats = {
        'initial_capital': 10000.0,
        'final_value': 11500.0,
        'total_return_pct': 15.0,
        'annualized_return_pct': 18.5,
        'sharpe_ratio': 1.2,
        'max_drawdown_pct': -8.5,
        'win_rate_pct': 60.0,
        'total_trades': 10,
        'buy_trades': 5,
        'sell_trades': 5,
        'winning_trades': 6,
        'losing_trades': 4
    }
    
    # 测试可视化功能
    visualizer = BacktestVisualizer()
    
    # 测试回测结果图表
    print("测试回测结果图表...")
    fig1 = visualizer.plot_backtest_results(test_data, test_trades)
    plt.show()
    
    # 测试交易分析图表
    print("测试交易分析图表...")
    fig2 = visualizer.plot_trade_analysis(test_trades, 10000.0)
    plt.show()
    
    # 测试性能指标图表
    print("测试性能指标图表...")
    fig3 = visualizer.plot_performance_metrics(test_stats)
    plt.show()
    
    print("\n✓ 可视化模块测试完成!")