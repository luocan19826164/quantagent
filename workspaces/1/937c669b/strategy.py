"""
交易策略模块
实现基于RSI指标的交易信号生成逻辑
"""

import pandas as pd
import numpy as np
from typing import Tuple, Optional, Dict, Any
from enum import Enum


class Signal(Enum):
    """交易信号枚举"""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PositionStatus(Enum):
    """持仓状态枚举"""
    NO_POSITION = "NO_POSITION"  # 空仓
    IN_POSITION = "IN_POSITION"  # 持仓中


class RSIStrategy:
    """
    RSI交易策略类
    
    策略规则：
    1. 当RSI(14) < 20时，产生买入信号
    2. 买入后，当RSI(14) > 60时，产生卖出信号
    3. 其他情况保持持仓状态不变
    """
    
    def __init__(self, rsi_period: int = 14, 
                 buy_threshold: float = 20.0, 
                 sell_threshold: float = 60.0):
        """
        初始化RSI策略
        
        Args:
            rsi_period: RSI计算周期，默认为14
            buy_threshold: 买入阈值，RSI低于此值时买入，默认为20
            sell_threshold: 卖出阈值，RSI高于此值时卖出，默认为60
        """
        self.rsi_period = rsi_period
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.position_status = PositionStatus.NO_POSITION
        
    def generate_signals(self, prices: pd.Series, 
                         rsi_values: Optional[pd.Series] = None) -> pd.Series:
        """
        生成交易信号序列
        
        Args:
            prices: 价格序列
            rsi_values: RSI值序列，如果为None则自动计算
            
        Returns:
            交易信号序列，与输入价格序列长度相同
        """
        if rsi_values is None:
            # 导入indicators模块中的RSI计算函数
            from indicators import calculate_rsi
            rsi_values = calculate_rsi(prices, period=self.rsi_period)
        
        # 初始化信号序列
        signals = pd.Series(Signal.HOLD.value, index=prices.index)
        
        # 重置持仓状态
        self.position_status = PositionStatus.NO_POSITION
        
        # 遍历数据生成信号
        for i in range(len(prices)):
            # 跳过RSI值为NaN的数据点
            if pd.isna(rsi_values.iloc[i]):
                signals.iloc[i] = Signal.HOLD.value
                continue
            
            current_rsi = rsi_values.iloc[i]
            
            if self.position_status == PositionStatus.NO_POSITION:
                # 空仓状态：检查是否满足买入条件
                if current_rsi < self.buy_threshold:
                    signals.iloc[i] = Signal.BUY.value
                    self.position_status = PositionStatus.IN_POSITION
                else:
                    signals.iloc[i] = Signal.HOLD.value
            else:
                # 持仓状态：检查是否满足卖出条件
                if current_rsi > self.sell_threshold:
                    signals.iloc[i] = Signal.SELL.value
                    self.position_status = PositionStatus.NO_POSITION
                else:
                    signals.iloc[i] = Signal.HOLD.value
        
        return signals
    
    def generate_signals_vectorized(self, prices: pd.Series,
                                   rsi_values: Optional[pd.Series] = None) -> pd.Series:
        """
        使用向量化方法生成交易信号序列（更高效）
        
        Args:
            prices: 价格序列
            rsi_values: RSI值序列，如果为None则自动计算
            
        Returns:
            交易信号序列
        """
        if rsi_values is None:
            from indicators import calculate_rsi
            rsi_values = calculate_rsi(prices, period=self.rsi_period)
        
        # 初始化信号序列
        signals = pd.Series(Signal.HOLD.value, index=prices.index)
        
        # 创建布尔掩码
        buy_condition = rsi_values < self.buy_threshold
        sell_condition = rsi_values > self.sell_threshold
        
        # 使用状态机逻辑处理信号
        in_position = False
        position_changes = []
        
        for i in range(len(prices)):
            if pd.isna(rsi_values.iloc[i]):
                position_changes.append(False)
                continue
            
            if not in_position and buy_condition.iloc[i]:
                # 从空仓变为持仓
                in_position = True
                position_changes.append(True)
            elif in_position and sell_condition.iloc[i]:
                # 从持仓变为空仓
                in_position = False
                position_changes.append(True)
            else:
                position_changes.append(False)
        
        # 根据状态变化生成信号
        in_position = False
        for i in range(len(prices)):
            if position_changes[i]:
                if not in_position:
                    # 买入信号
                    signals.iloc[i] = Signal.BUY.value
                    in_position = True
                else:
                    # 卖出信号
                    signals.iloc[i] = Signal.SELL.value
                    in_position = False
            else:
                signals.iloc[i] = Signal.HOLD.value
        
        return signals
    
    def get_strategy_info(self) -> Dict[str, Any]:
        """获取策略信息"""
        return {
            "strategy_name": "RSI Threshold Strategy",
            "rsi_period": self.rsi_period,
            "buy_threshold": self.buy_threshold,
            "sell_threshold": self.sell_threshold,
            "description": f"Buy when RSI({self.rsi_period}) < {self.buy_threshold}, "
                          f"Sell when RSI({self.rsi_period}) > {self.sell_threshold}"
        }


def test_strategy():
    """测试策略信号生成"""
    print("=" * 50)
    print("RSI策略测试")
    print("=" * 50)
    
    # 创建测试数据
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    base_price = 40000
    prices = pd.Series(
        base_price + np.random.randn(100).cumsum() * 1000,
        index=dates
    )
    
    # 创建策略实例
    strategy = RSIStrategy(rsi_period=14, buy_threshold=20, sell_threshold=60)
    
    # 获取策略信息
    info = strategy.get_strategy_info()
    print("策略信息:")
    for key, value in info.items():
        print(f"  {key}: {value}")
    print()
    
    # 生成信号
    signals = strategy.generate_signals(prices)
    
    # 统计信号数量
    buy_count = (signals == Signal.BUY.value).sum()
    sell_count = (signals == Signal.SELL.value).sum()
    hold_count = (signals == Signal.HOLD.value).sum()
    
    print("信号统计:")
    print(f"  买入信号: {buy_count}")
    print(f"  卖出信号: {sell_count}")
    print(f"  持有信号: {hold_count}")
    print(f"  总数据点: {len(prices)}")
    print()
    
    # 显示前20个信号
    print("前20个交易信号:")
    for i in range(min(20, len(prices))):
        date_str = prices.index[i].strftime('%Y-%m-%d')
        price = prices.iloc[i]
        signal = signals.iloc[i]
        print(f"  {date_str}: 价格={price:.2f}, 信号={signal}")
    
    # 测试向量化版本
    print("\n" + "=" * 30)
    print("测试向量化版本")
    print("=" * 30)
    
    signals_vec = strategy.generate_signals_vectorized(prices)
    
    # 验证两个版本结果一致
    if signals.equals(signals_vec):
        print("✓ 向量化版本与循环版本结果一致")
    else:
        print("✗ 两个版本结果不一致")
        differences = (signals != signals_vec).sum()
        print(f"  差异数量: {differences}")
    
    return strategy, prices, signals


if __name__ == "__main__":
    strategy, prices, signals = test_strategy()
    
    print("\n测试完成！")