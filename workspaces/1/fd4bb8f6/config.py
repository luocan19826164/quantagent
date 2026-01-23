"""
回测系统配置文件
"""

# 数据配置
DATA_CONFIG = {
    'symbol': 'BTCUSDT',  # 交易对
    'interval': '1d',     # 时间间隔：1d=日线
    'lookback_years': 1,  # 回看年数
    'data_source': 'binance',  # 数据源
}

# 策略配置
STRATEGY_CONFIG = {
    'rsi_period': 14,     # RSI周期
    'buy_threshold': 20,  # 买入阈值
    'sell_threshold': 60, # 卖出阈值
    'position_size': 1.0, # 仓位大小（1.0=全仓）
}

# 回测配置
BACKTEST_CONFIG = {
    'initial_capital': 10000.0,  # 初始资金（USDT）
    'commission_rate': 0.001,    # 手续费率（0.1%）
    'slippage': 0.0005,          # 滑点（0.05%）
    'start_date': None,          # 回测开始日期（None=自动计算）
    'end_date': None,            # 回测结束日期（None=最近日期）
}

# 输出配置
OUTPUT_CONFIG = {
    'save_results': True,        # 是否保存结果
    'output_dir': 'results',     # 输出目录
    'plot_results': True,        # 是否绘制图表
    'verbose': True,             # 是否输出详细信息
}