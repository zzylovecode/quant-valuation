"""
回测模块
========

提供基于估值选股策略的历史回测功能：
  - 策略定义：可扩展的选股策略基类
  - 回测引擎：调仓、持仓、收益计算
  - 绩效分析：收益率、夏普、最大回撤、胜率
  - 基准对比：相对基准的超额收益分析

模块结构：
  - strategies.py: 选股策略
  - backtest_engine.py: 回测引擎
  - performance.py: 绩效分析
  - data_provider.py: 历史数据提供者
"""

from .strategies import (
    BaseStrategy,
    ValueStrategy,
    QualityValueStrategy,
    GARPStrategy,
    DeepValueStrategy,
    LowPEStrategy,
    LowPBStrategy,
    CompositeScoreStrategy,
)
from .backtest_engine import BacktestEngine, BacktestResult, Position
from .performance import PerformanceAnalyzer, PerformanceMetrics
from .data_provider import (
    HistoricalDataProvider,
    MockDataProvider,
    TushareDataProvider,
)

__all__ = [
    "BaseStrategy",
    "ValueStrategy",
    "QualityValueStrategy",
    "GARPStrategy",
    "DeepValueStrategy",
    "LowPEStrategy",
    "LowPBStrategy",
    "CompositeScoreStrategy",
    "BacktestEngine",
    "BacktestResult",
    "Position",
    "PerformanceAnalyzer",
    "PerformanceMetrics",
    "HistoricalDataProvider",
    "MockDataProvider",
    "TushareDataProvider",
]
