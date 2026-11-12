"""
数据源模块
==========

提供从多种数据源获取财务数据和行情数据的能力，
并自动构建 FinancialData 对象供估值模型使用。

目前支持：
  - Tushare Pro (tushare)
  - AKShare (akshare) - 完全免费，依赖国内数据源
  - Yahoo Finance (yfinance) - 完全免费，海外服务器可用
"""

from .tushare_client import TushareClient
from .tushare_builder import TushareDataBuilder
from .akshare_client import AKShareClient
from .akshare_builder import AKShareDataBuilder
from .yfinance_client import YFinanceClient
from .yfinance_builder import YFinanceDataBuilder

__all__ = [
    "TushareClient",
    "TushareDataBuilder",
    "AKShareClient",
    "AKShareDataBuilder",
    "YFinanceClient",
    "YFinanceDataBuilder",
]
