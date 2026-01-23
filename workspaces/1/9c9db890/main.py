"""
BTC RSI策略回测系统主程序

策略规则：
1. 当RSI(14) < 20时买入
2. 买入后当RSI(14) > 60时卖出
"""

import sys
import logging
from datetime import datetime

from config.settings import settings
from modules.data_fetcher import DataFetcher
from modules.indicators import IndicatorCalculator
from strategies.rsi_strategy import RSIStrategy
from backtest.engine import BacktestEngine
from backtest.analyzer import ResultAnalyzer


def setup_logging() -> None:
    """设置日志配置"""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(f"logs/backtest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"),
            logging.StreamHandler()
        ]
    )


def main() -> None:
    """主函数"""
    print("=== BTC RSI策略回测系统 ===")
    print(f"策略: {settings.STRATEGY_CONFIG['name']}")
    print(f"数据范围: {settings.DATA_CONFIG['start_date']} 到 {settings.DATA_CONFIG['end_date']}")
    print(f"初始资金: ${settings.STRATEGY_CONFIG['initial_capital']:,.2f}")
    print()
    
    try:
        # 1. 获取数据
        print("步骤1: 获取BTC价格数据...")
        fetcher = DataFetcher()
        data = fetcher.fetch_data()
        print(f"获取到 {len(data)} 条数据")
        
        # 2. 计算技术指标
        print("步骤2: 计算技术指标...")
        calculator = IndicatorCalculator(data)
        data_with_indicators = calculator.calculate_all()
        
        # 3. 创建策略
        print("步骤3: 初始化RSI策略...")
        strategy = RSIStrategy()
        
        # 4. 执行回测
        print("步骤4: 执行回测...")
        engine = BacktestEngine(strategy)
        results = engine.run(data_with_indicators)
        
        # 5. 分析结果
        print("步骤5: 分析回测结果...")
        analyzer = ResultAnalyzer(results)
        analyzer.analyze()
        
        print("\n回测完成！")
        
    except Exception as e:
        logging.error(f"回测过程中发生错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    setup_logging()
    main()
