"""
回测系统配置
"""

import os
from datetime import datetime, timedelta
from typing import Dict, Any


class Settings:
    """回测系统配置类"""
    
    # 数据配置
    DATA_CONFIG: Dict[str, Any] = {
        'symbol': 'BTC-USD',  # 交易对
        'start_date': (datetime.now() - timedelta(days=365)).strftime('%Y-%m-%d'),  # 一年前
        'end_date': datetime.now().strftime('%Y-%m-%d'),  # 今天
        'interval': '1d',  # 日线数据
        'data_source': 'yfinance',  # 数据源
        'columns': ['open', 'high', 'low', 'close', 'volume']  # 数据列
    }
    
    # 策略配置
    STRATEGY_CONFIG: Dict[str, Any] = {
        'name': 'RSI_Strategy',
        'rsi_period': 14,  # RSI计算周期
        'buy_threshold': 20,  # 买入阈值
        'sell_threshold': 60,  # 卖出阈值
        'initial_capital': 10000.0,  # 初始资金
        'position_size': 1.0,  # 仓位大小（1.0表示全仓）
        'commission': 0.001,  # 手续费率（0.1%）
        'slippage': 0.0005  # 滑点（0.05%）
    }
    
    # 回测配置
    BACKTEST_CONFIG: Dict[str, Any] = {
        'enable_stop_loss': False,  # 是否启用止损
        'stop_loss_pct': 0.10,  # 止损比例
        'enable_take_profit': False,  # 是否启用止盈
        'take_profit_pct': 0.20,  # 止盈比例
        'allow_short': False,  # 是否允许做空
        'max_position': 1.0  # 最大仓位限制
    }
    
    # 输出配置
    OUTPUT_CONFIG: Dict[str, Any] = {
        'save_results': True,
        'results_dir': 'results',
        'generate_charts': True,
        'chart_format': 'png',
        'verbose': True  # 是否输出详细日志
    }
    
    # 路径配置
    @property
    def DATA_DIR(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data')
    
    @property
    def RESULTS_DIR(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')
    
    @property
    def LOG_DIR(self) -> str:
        return os.path.join(os.path.dirname(os.path.dirname(__file__)), 'logs')


# 全局配置实例
settings = Settings()