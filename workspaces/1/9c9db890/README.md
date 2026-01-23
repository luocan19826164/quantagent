# BTC RSI策略回测系统

一个基于RSI指标的比特币量化交易策略回测系统。

## 策略规则
1. 当RSI(14) < 20时买入
2. 买入后当RSI(14) > 60时卖出

## 项目结构
```
.
├── main.py                    # 主程序入口
├── requirements.txt           # 依赖包
├── README.md                  # 项目说明
├── config/
│   └── settings.py           # 配置文件
├── modules/                  # 功能模块
├── strategies/               # 策略模块
├── backtest/                 # 回测引擎
├── data/                     # 数据存储
├── results/                  # 回测结果
└── logs/                     # 日志文件
```

## 快速开始

### 1. 安装依赖
```bash
pip install -r requirements.txt
```

### 2. 运行回测
```bash
python main.py
```

### 3. 查看结果
回测结果将保存在 `results/` 目录下，包括：
- 资金曲线图
- 交易记录
- 统计指标

## 配置说明
在 `config/settings.py` 中可以修改以下配置：

### 数据配置
- `symbol`: 交易对（默认：BTC-USD）
- `start_date`: 开始日期（默认：一年前）
- `end_date`: 结束日期（默认：今天）
- `interval`: 数据间隔（默认：1d，日线）

### 策略配置
- `rsi_period`: RSI计算周期（默认：14）
- `buy_threshold`: 买入阈值（默认：20）
- `sell_threshold`: 卖出阈值（默认：60）
- `initial_capital`: 初始资金（默认：10000）
- `commission`: 手续费率（默认：0.001，0.1%）

## 功能特性
- ✅ 自动获取BTC价格数据
- ✅ 计算RSI技术指标
- ✅ 实现RSI策略逻辑
- ✅ 回测引擎模拟交易
- ✅ 统计指标计算
- ✅ 可视化图表生成

## 注意事项
1. 回测结果仅供参考，不构成投资建议
2. 实际交易需考虑滑点、流动性等因素
3. 建议在不同市场环境下测试策略表现