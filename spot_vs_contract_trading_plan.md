# 现货 vs 合约交易逻辑改进方案

## 问题分析

当前代码存在的问题：
- 买入时检查 `not is_holding`（正确，避免重复买入）
- 卖出时检查 `is_holding`（**只适用于现货，合约可以做空**）

## 现货 vs 合约的区别

### 现货交易（spot）
- **买入（buy）**：需要先有资金，买入后持有资产
  - 条件：`not is_holding`（不能重复买入）
- **卖出（sell）**：必须先持有资产才能卖出
  - 条件：`is_holding == True`（必须先买入）

### 合约交易（contract）
- **买入（buy）**：开多仓或平空仓
  - **开多仓**：`not is_holding`（没有持仓时，买入就是开多仓）
  - **平空仓**：`is_holding == True and position_side == 'short'`（已有空仓时，买入是平空仓）
  
- **卖出（sell）**：开空仓或平多仓
  - **开空仓**：`not is_holding`（没有持仓时，卖出就是开空仓）
  - **平多仓**：`is_holding == True and position_side == 'long'`（已有多仓时，卖出是平多仓）

**关键理解：**
- 合约可以做多（买入）也可以做空（卖出），不需要先持有
- 如果已有空仓，买入操作会平掉空仓（平空）
- 如果已有多仓，卖出操作会平掉多仓（平多）

## 改进方案

### 1. 扩展 runtime_status 结构

当前结构：
```python
runtime_status = {
    "is_holding": False,  # 是否持仓
    "entry_price": None,  # 开仓价格
    "last_update": None   # 最后更新时间
}
```

改进后结构：
```python
runtime_status = {
    "is_holding": False,      # 是否持仓
    "entry_price": None,      # 开仓价格
    "position_side": None,    # 持仓方向：'long'（多头）或 'short'（空头），仅合约使用
    "position_size": 0.0,     # 持仓数量（可选，用于精确平仓）
    "last_update": None       # 最后更新时间
}
```

### 2. 交易逻辑判断函数

```python
def _can_execute_buy(self, product: str, runtime_status: Dict) -> bool:
    """
    判断是否可以执行买入操作
    
    Args:
        product: 产品类型 "spot" 或 "contract"
        runtime_status: 当前持仓状态
        
    Returns:
        bool: 是否可以买入
    """
    is_holding = runtime_status.get('is_holding', False)
    position_side = runtime_status.get('position_side')
    
    if product == "spot":
        # 现货：不能重复买入（必须先卖出才能再买入）
        return not is_holding
    elif product in ["contract", "futures"]:
        # 合约：可以开多仓，或平空仓
        if not is_holding:
            # 没有持仓 → 可以开多仓
            return True
        elif position_side == 'short':
            # 已有空仓 → 可以买入平空仓
            return True
        elif position_side == 'long':
            # 已有多仓 → 不能重复开多（但可以继续持有）
            return False
        else:
            return True  # 未知状态，允许尝试
    else:
        return False

def _can_execute_sell(self, product: str, runtime_status: Dict) -> bool:
    """
    判断是否可以执行卖出操作
    
    Args:
        product: 产品类型 "spot" 或 "contract"
        runtime_status: 当前持仓状态
        
    Returns:
        bool: 是否可以卖出
    """
    is_holding = runtime_status.get('is_holding', False)
    position_side = runtime_status.get('position_side')
    
    if product == "spot":
        # 现货：必须先持有才能卖出
        return is_holding
    elif product in ["contract", "futures"]:
        # 合约：可以开空仓，或平多仓
        if not is_holding:
            # 没有持仓 → 可以开空仓
            return True
        elif position_side == 'long':
            # 已有多仓 → 可以卖出平多仓
            return True
        elif position_side == 'short':
            # 已有空仓 → 不能重复开空（但可以继续持有）
            return False
        else:
            return True  # 未知状态，允许尝试
    else:
        return False
```

### 3. 更新 runtime_status 的逻辑

```python
def _update_runtime_status_after_buy(self, product: str, runtime_status: Dict, price: float):
    """买入后更新持仓状态"""
    if product == "spot":
        runtime_status['is_holding'] = True
        runtime_status['entry_price'] = price
        runtime_status['position_side'] = None  # 现货不需要方向
    elif product in ["contract", "futures"]:
        if runtime_status.get('position_side') == 'short':
            # 平空仓
            runtime_status['is_holding'] = False
            runtime_status['position_side'] = None
            runtime_status['entry_price'] = None
        else:
            # 开多仓
            runtime_status['is_holding'] = True
            runtime_status['position_side'] = 'long'
            runtime_status['entry_price'] = price

def _update_runtime_status_after_sell(self, product: str, runtime_status: Dict, price: float):
    """卖出后更新持仓状态"""
    if product == "spot":
        runtime_status['is_holding'] = False
        runtime_status['entry_price'] = None
        runtime_status['position_side'] = None
    elif product in ["contract", "futures"]:
        if runtime_status.get('position_side') == 'long':
            # 平多仓
            runtime_status['is_holding'] = False
            runtime_status['position_side'] = None
            runtime_status['entry_price'] = None
        else:
            # 开空仓
            runtime_status['is_holding'] = True
            runtime_status['position_side'] = 'short'
            runtime_status['entry_price'] = price
```

### 4. 执行逻辑改进

```python
# 获取产品类型
product = requirements.get('product', 'spot')  # 默认为现货

# 买入逻辑
if decision_action == 'buy' and self._can_execute_buy(product, runtime_status):
    # 执行买入...
    # 更新状态
    self._update_runtime_status_after_buy(product, runtime_status, current_price)
    
# 卖出逻辑
elif decision_action == 'sell' and self._can_execute_sell(product, runtime_status):
    # 执行卖出...
    # 更新状态
    self._update_runtime_status_after_sell(product, runtime_status, current_price)
```

## 总结

1. **扩展 runtime_status**：添加 `position_side` 字段记录持仓方向
2. **创建判断函数**：`_can_execute_buy()` 和 `_can_execute_sell()` 根据产品类型判断
3. **创建更新函数**：`_update_runtime_status_after_buy/sell()` 根据产品类型更新状态
4. **修改执行逻辑**：使用新的判断函数替代硬编码的 `is_holding` 检查

这样就能正确处理现货和合约的不同交易逻辑了。

