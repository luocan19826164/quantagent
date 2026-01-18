"""
配置文件
包含所有可配置的回测参数和策略参数
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class StrategyConfig:
    """策略配置"""
    
    # RSI策略参数
    rsi_period: int = 14
    rsi_buy_threshold: float = 20.0
    rsi_sell_threshold: float = 60.0
    
    # 仓位管理
    position_size: float = 1.0  # 仓位比例 (0.0-1.0)
    max_position_size: float = 1.0  # 最大仓位限制
    
    # 交易参数
    transaction_fee: float = 0.001  # 交易手续费 (0.1%)
    slippage: float = 0.0005  # 滑点 (0.05%)
    
    # 风险管理
    stop_loss_pct: Optional[float] = None  # 止损比例 (可选)
    take_profit_pct: Optional[float] = None  # 止盈比例 (可选)


@dataclass
class BacktestConfig:
    """回测配置"""
    
    # 资金配置
    initial_capital: float = 10000.0  # 初始资金
    
    # 数据配置
    symbol: str = "BTC-USD"  # 交易对
    period: str = "1y"  # 数据周期
    interval: str = "1d"  # 数据间隔
    
    # 回测时间范围
    start_date: Optional[str] = None  # 开始日期 (格式: YYYY-MM-DD)
    end_date: Optional[str] = None  # 结束日期 (格式: YYYY-MM-DD)
    
    # 输出配置
    output_dir: str = "results"  # 输出目录
    save_results: bool = True  # 是否保存结果
    generate_charts: bool = True  # 是否生成图表
    export_excel: bool = True  # 是否导出Excel


@dataclass
class PerformanceConfig:
    """绩效分析配置"""
    
    # 基准配置
    benchmark_symbol: str = "BTC-USD"  # 基准交易对
    risk_free_rate: float = 0.02  # 无风险利率 (年化)
    
    # 分析参数
    rolling_window: int = 30  # 滚动窗口大小
    confidence_level: float = 0.95  # 置信水平
    
    # 报告配置
    report_format: str = "text"  # 报告格式: text, html, markdown
    include_charts: bool = True  # 是否包含图表


# 默认配置实例
DEFAULT_STRATEGY_CONFIG = StrategyConfig()
DEFAULT_BACKTEST_CONFIG = BacktestConfig()
DEFAULT_PERFORMANCE_CONFIG = PerformanceConfig()


def create_config_from_dict(config_dict: dict) -> tuple:
    """
    从字典创建配置对象
    
    Args:
        config_dict: 配置字典
        
    Returns:
        tuple: (strategy_config, backtest_config, performance_config)
    """
    strategy_dict = config_dict.get('strategy', {})
    backtest_dict = config_dict.get('backtest', {})
    performance_dict = config_dict.get('performance', {})
    
    strategy_config = StrategyConfig(**strategy_dict)
    backtest_config = BacktestConfig(**backtest_dict)
    performance_config = PerformanceConfig(**performance_dict)
    
    return strategy_config, backtest_config, performance_config


def save_config_to_file(config_dict: dict, filepath: str = "config.json") -> None:
    """
    保存配置到JSON文件
    
    Args:
        config_dict: 配置字典
        filepath: 文件路径
    """
    import json
    
    with open(filepath, 'w') as f:
        json.dump(config_dict, f, indent=2, default=str)
    
    print(f"配置已保存到: {filepath}")


def load_config_from_file(filepath: str = "config.json") -> dict:
    """
    从JSON文件加载配置
    
    Args:
        filepath: 文件路径
        
    Returns:
        dict: 配置字典
    """
    import json
    
    with open(filepath, 'r') as f:
        config_dict = json.load(f)
    
    return config_dict


if __name__ == "__main__":
    # 测试配置功能
    print("测试配置功能...")
    
    # 创建默认配置
    strategy_config = DEFAULT_STRATEGY_CONFIG
    backtest_config = DEFAULT_BACKTEST_CONFIG
    performance_config = DEFAULT_PERFORMANCE_CONFIG
    
    print(f"策略配置: RSI周期={strategy_config.rsi_period}, "
          f"买入阈值={strategy_config.rsi_buy_threshold}, "
          f"卖出阈值={strategy_config.rsi_sell_threshold}")
    
    print(f"回测配置: 初始资金=${backtest_config.initial_capital:,.2f}, "
          f"交易对={backtest_config.symbol}, "
          f"周期={backtest_config.period}")
    
    print(f"绩效配置: 无风险利率={performance_config.risk_free_rate:.2%}, "
          f"基准={performance_config.benchmark_symbol}")
    
    # 创建配置字典
    config_dict = {
        'strategy': {
            'rsi_period': 10,
            'rsi_buy_threshold': 25.0,
            'rsi_sell_threshold': 75.0,
            'position_size': 0.5
        },
        'backtest': {
            'initial_capital': 5000.0,
            'symbol': 'ETH-USD',
            'period': '6mo'
        }
    }
    
    # 从字典创建配置
    strategy_config, backtest_config, performance_config = create_config_from_dict(config_dict)
    
    print(f"\n自定义配置:")
    print(f"策略配置: RSI周期={strategy_config.rsi_period}, "
          f"买入阈值={strategy_config.rsi_buy_threshold}, "
          f"卖出阈值={strategy_config.rsi_sell_threshold}")
    print(f"回测配置: 初始资金=${backtest_config.initial_capital:,.2f}, "
          f"交易对={backtest_config.symbol}, "
          f"周期={backtest_config.period}")
    
    print("\n✓ 配置功能测试完成")