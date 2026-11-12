"""
量化估值模型工具包
==================

提供多种上市公司估值方法：
- DCF (折现现金流模型)
- 相对估值 (PE / PB / PEG)
- DDM (股息贴现模型)
- 剩余收益模型 (Residual Income)
- 综合估值分析与敏感性分析
- Tushare 数据源接入
- 批量估值与筛选
- 回测框架（绩效分析 + 多策略对比）

用法示例：
    from quant_valuation import FinancialData, DCFModel, ValuationAnalyzer
    from quant_valuation.data_sources import TushareDataBuilder
    from quant_valuation.batch import BatchValuator, ValuationScreener
    from quant_valuation.backtest import BacktestEngine, PerformanceAnalyzer

    builder = TushareDataBuilder(token="你的token")
    data = builder.build("600519.SH")
    analyzer = ValuationAnalyzer(data)
    report = analyzer.full_valuation()
"""

from .financial_data import FinancialData
from .dcf_model import DCFModel
from .relative_valuation import RelativeValuation
from .ddm_model import DDMModel, ResidualIncomeModel
from .valuation_analyzer import ValuationAnalyzer
from . import data_sources
from . import batch
from . import backtest

__all__ = [
    "FinancialData",
    "DCFModel",
    "RelativeValuation",
    "DDMModel",
    "ResidualIncomeModel",
    "ValuationAnalyzer",
    "data_sources",
    "batch",
    "backtest",
]

__version__ = "0.6.1"
