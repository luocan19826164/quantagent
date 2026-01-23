# BTC RSI策略回测系统

一个基于RSI指标的比特币交易策略回测系统。

## 策略描述
- **交易品种**: BTC/USDT
- **数据频率**: 日线
- **回测周期**: 最近一年
- **买入条件**: RSI(14) < 20
- **卖出条件**: 买入后RSI > 60
- **仓位管理**: 全仓进出

## 项目结构
```
.
├── README.md              # 项目说明
├── requirements.txt       # Python依赖包
├── config.py             # 配置文件
├── main.py               # 主程序入口
├── data/                 # 数据目录
├── modules/              # 功能模块
│   ├── data_fetcher.py   # 数据获取模块
│   ├── indicators.py     # 技术指标模块
│   ├── strategy.py       # 策略模块
│   ├── backtest.py       # 回测引擎模块
│   └── analysis.py       # 结果分析模块
└── results/              # 回测结果输出目录
```

## 安装依赖
```bash
pip install -r requirements.txt
```

## 使用方法
1. 安装依赖包
2. 运行主程序：
```bash
python main.py
```

## 配置说明
在 `config.py` 中可以修改：
- 交易对和时间间隔
- RSI参数和买卖阈值
- 初始资金和手续费率
- 输出选项

## 输出结果
回测完成后会生成：
- 回测报告（文本格式）
- 资金曲线图
- 买卖点标记图
- 详细的交易记录