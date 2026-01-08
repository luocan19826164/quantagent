# runtime_status 改进方案

## 当前问题

当前 `runtime_status` 结构：
```python
{
    "is_holding": False,
    "entry_price": None,
    "last_update": None
}
```

**缺少的关键字段：**
- ❌ `quantity`：持仓数量（base 资产的数量）
- ❌ `position_side`：持仓方向（合约需要：'long' 或 'short'）
- ❌ `position_value`：持仓价值（可选，用于计算盈亏）

## 改进后的结构

```python
runtime_status = {
    "is_holding": False,        # 是否持仓
    "entry_price": None,        # 开仓价格
    "quantity": 0.0,           # 持仓数量（base 资产，如 BTC 数量）
    "position_side": None,      # 持仓方向：'long'（多头）或 'short'（空头），仅合约使用
    "position_value": 0.0,      # 持仓价值（quote 资产，如 USDT），可选
    "last_update": None         # 最后更新时间
}
```

## 使用场景

### 1. 买入时记录 quantity

```python
# 买入后更新
runtime_status['is_holding'] = True
runtime_status['entry_price'] = current_price
runtime_status['quantity'] = quantity  # 买入的 base 资产数量
runtime_status['position_value'] = quantity * current_price  # 持仓价值
if product == "contract":
    runtime_status['position_side'] = 'long'  # 合约开多
```

### 2. 卖出时使用 quantity

```python
# 卖出时从 runtime_status 获取数量
quantity_to_sell = runtime_status.get('quantity', 0)

if quantity_to_sell > 0:
    order_res = place_order.invoke({
        "exchange": exchange,
        "symbol": symbol,
        "side": "sell",
        "order_type": "market",
        "quantity": quantity_to_sell  # 使用实际持仓数量
    })
```

### 3. 部分平仓支持

```python
# 如果只平部分仓位
partial_quantity = quantity_to_sell * 0.5  # 平一半
runtime_status['quantity'] = quantity_to_sell - partial_quantity  # 更新剩余数量
```

## 需要修改的地方

1. **state_manager.py**：更新 `runtime_status` 初始化
2. **execution_agent.py**：
   - 买入时记录 `quantity`
   - 卖出时使用 `quantity`
   - 更新状态时保留 `quantity`

## 示例代码

```python
# 买入后更新
if "order_id" in order_res:
    runtime_status['is_holding'] = True
    runtime_status['entry_price'] = current_price
    runtime_status['quantity'] = quantity  # 新增
    runtime_status['position_value'] = quantity * current_price  # 新增
    if product in ["contract", "futures"]:
        runtime_status['position_side'] = 'long'  # 新增
    runtime_status['last_update'] = datetime.now().isoformat()

# 卖出时使用
quantity_to_sell = runtime_status.get('quantity', 0)
if quantity_to_sell > 0:
    order_res = place_order.invoke({
        "exchange": exchange,
        "symbol": symbol,
        "side": "sell",
        "order_type": "market",
        "quantity": quantity_to_sell  # 使用实际数量
    })
    
    if "order_id" in order_res:
        # 平仓后清空
        runtime_status['is_holding'] = False
        runtime_status['entry_price'] = None
        runtime_status['quantity'] = 0.0  # 清空
        runtime_status['position_side'] = None  # 清空
        runtime_status['position_value'] = 0.0  # 清空
```

