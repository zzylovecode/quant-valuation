"""
选股策略
========

所有选股策略继承自 BaseStrategy，在每个调仓日：
  1. 接收股票池及当期财务数据
  2. 按策略逻辑打分/筛选
  3. 返回选中的股票列表及权重

内置策略：
  - ValueStrategy:         简单价值策略（选最被低估的 N 只）
  - QualityValueStrategy:  质优价廉（高 ROE + 低估）
  - GARPStrategy:          合理价格成长（GARP）
  - DeepValueStrategy:     深度价值（低 PE + 低 PB）
  - LowPEStrategy:         低 PE 策略
  - LowPBStrategy:         低 PB 策略
  - CompositeScoreStrategy:多因子综合打分
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Tuple

import pandas as pd


class BaseStrategy(ABC):
    """
    选股策略基类

    子类需实现 select_stocks 方法，在每个调仓日返回选中的股票及权重。
    """

    def __init__(self, name: str = "BaseStrategy", top_n: int = 10):
        """
        Args:
            name: 策略名称
            top_n: 选股数量
        """
        self.name = name
        self.top_n = top_n

    @abstractmethod
    def select_stocks(
        self,
        stock_data: pd.DataFrame,
        date: str,
    ) -> List[Tuple[str, float]]:
        """
        在指定日期选择股票

        Args:
            stock_data: 当日所有股票的财务数据 DataFrame，
                        至少包含列: ts_code, name, price, pe, pb, roe,
                        profit_growth, upside_downside, market_cap
            date: 调仓日期 YYYYMMDD

        Returns:
            [(ts_code, weight), ...] 列表，权重之和应为 1
            等权时每只权重 = 1 / top_n
        """
        pass

    def _equal_weight(self, codes: List[str]) -> List[Tuple[str, float]]:
        """等权分配"""
        if not codes:
            return []
        w = 1.0 / len(codes)
        return [(code, w) for code in codes]

    def _rank_weighted(self, codes: List[str], decay: float = 0.9) -> List[Tuple[str, float]]:
        """
        排名加权（排名越靠前权重越高）
        decay: 权重衰减系数，0.9 表示第2名是第1名的 90%
        """
        if not codes:
            return []
        raw_weights = [decay ** i for i in range(len(codes))]
        total = sum(raw_weights)
        return [(code, w / total) for code, w in zip(codes, raw_weights)]


# ============================================================
# 内置策略
# ============================================================

class ValueStrategy(BaseStrategy):
    """
    简单价值策略
    按估值上涨空间（upside_downside）排序，选最被低估的 top_n 只
    """

    def __init__(self, top_n: int = 10, min_upside: float = -0.5, name: str = "价值策略(低估)"):
        super().__init__(name=name, top_n=top_n)
        self.min_upside = min_upside

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()
        # 过滤掉极端值（可能是数据异常）
        df = df[df["upside_downside"] >= self.min_upside]
        # 按上涨空间降序
        df = df.sort_values("upside_downside", ascending=False)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._equal_weight(selected)


class QualityValueStrategy(BaseStrategy):
    """
    质优价廉策略
    综合考虑 ROE（质量）和 上涨空间（估值）
    筛选条件：ROE > 阈值 且 上涨空间 > 阈值
    然后按综合得分排序
    """

    def __init__(
        self,
        top_n: int = 10,
        min_roe: float = 0.12,
        min_upside: float = 0.10,
        min_profit: float = 1.0,
        name: str = "质优价廉",
    ):
        super().__init__(name=name, top_n=top_n)
        self.min_roe = min_roe
        self.min_upside = min_upside
        self.min_profit = min_profit

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()

        # 基本筛选
        df = df[
            (df["roe"] >= self.min_roe)
            & (df["upside_downside"] >= self.min_upside)
            & (df["net_profit"] >= self.min_profit)
        ]

        if df.empty:
            return []

        # 综合得分 = ROE 标准化得分 × 0.5 + 上涨空间标准化得分 × 0.5
        def zscore(s):
            std = s.std()
            if std == 0:
                return s * 0
            return (s - s.mean()) / std

        df["roe_score"] = zscore(df["roe"])
        df["value_score"] = zscore(df["upside_downside"])
        df["total_score"] = df["roe_score"] * 0.5 + df["value_score"] * 0.5

        df = df.sort_values("total_score", ascending=False)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._rank_weighted(selected, decay=0.85)


class GARPStrategy(BaseStrategy):
    """
    GARP 策略 (Growth at a Reasonable Price)
    合理价格下的成长股：高增长 + 估值不过分高
    按 PEG 思路排序
    """

    def __init__(
        self,
        top_n: int = 10,
        min_growth: float = 0.15,
        max_pe: float = 50,
        min_upside: float = -0.20,
        name: str = "GARP成长",
    ):
        super().__init__(name=name, top_n=top_n)
        self.min_growth = min_growth
        self.max_pe = max_pe
        self.min_upside = min_upside

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()

        # 筛选：正增长 + PE 合理 + 上涨空间不太低
        df = df[
            (df["profit_growth"] >= self.min_growth)
            & (df["pe"] > 0)
            & (df["pe"] <= self.max_pe)
            & (df["upside_downside"] >= self.min_upside)
        ]

        if df.empty:
            return []

        # PEG 得分（越低越好，但增长也要够）
        df["peg"] = df["pe"] / (df["profit_growth"] * 100)
        # 综合：增长越高越好 + PEG 越低越好
        def zscore(s):
            std = s.std()
            if std == 0:
                return s * 0
            return (s - s.mean()) / std

        df["growth_score"] = zscore(df["profit_growth"])
        df["peg_score"] = -zscore(df["peg"])  # 负号因为越低越好
        df["total_score"] = df["growth_score"] * 0.6 + df["peg_score"] * 0.4

        df = df.sort_values("total_score", ascending=False)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._rank_weighted(selected, decay=0.9)


class DeepValueStrategy(BaseStrategy):
    """
    深度价值策略
    低 PE + 低 PB + 正盈利
    经典格雷厄姆式烟蒂投资
    """

    def __init__(
        self,
        top_n: int = 10,
        max_pe: float = 15,
        max_pb: float = 1.5,
        min_roe: float = 0.05,
        name: str = "深度价值",
    ):
        super().__init__(name=name, top_n=top_n)
        self.max_pe = max_pe
        self.max_pb = max_pb
        self.min_roe = min_roe

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()

        df = df[
            (df["pe"] > 0)
            & (df["pe"] <= self.max_pe)
            & (df["pb"] > 0)
            & (df["pb"] <= self.max_pb)
            & (df["roe"] >= self.min_roe)
        ]

        if df.empty:
            return []

        # 按 PE/PB 综合排序（越低越好）
        df["pe_rank"] = df["pe"].rank(pct=True)
        df["pb_rank"] = df["pb"].rank(pct=True)
        df["total_score"] = -(df["pe_rank"] + df["pb_rank"])  # 负号：越低分越高

        df = df.sort_values("total_score", ascending=False)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._equal_weight(selected)


class LowPEStrategy(BaseStrategy):
    """低 PE 策略"""

    def __init__(self, top_n: int = 10, max_pe: float = 30, name: str = "低PE"):
        super().__init__(name=name, top_n=top_n)
        self.max_pe = max_pe

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()
        df = df[(df["pe"] > 0) & (df["pe"] <= self.max_pe)]
        df = df.sort_values("pe", ascending=True)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._equal_weight(selected)


class LowPBStrategy(BaseStrategy):
    """低 PB 策略"""

    def __init__(self, top_n: int = 10, max_pb: float = 3.0, name: str = "低PB"):
        super().__init__(name=name, top_n=top_n)
        self.max_pb = max_pb

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()
        df = df[(df["pb"] > 0) & (df["pb"] <= self.max_pb)]
        df = df.sort_values("pb", ascending=True)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._equal_weight(selected)


class CompositeScoreStrategy(BaseStrategy):
    """
    多因子综合打分策略
    综合考虑：估值(30%) + 质量(25%) + 成长(25%) + 规模(10%) + 动量(10%)

    每个因子做排名百分位转化，然后加权求和。
    """

    def __init__(
        self,
        top_n: int = 10,
        weights: Optional[Dict[str, float]] = None,
        name: str = "多因子综合",
    ):
        super().__init__(name=name, top_n=top_n)
        self.weights = weights or {
            "value": 0.30,    # 估值因子（上涨空间）
            "quality": 0.25,  # 质量因子（ROE）
            "growth": 0.25,   # 成长因子（利润增速）
            "size": 0.10,     # 规模因子（市值越小得分越高，小市值溢价）
            "momentum": 0.10, # 动量因子（需要额外数据，这里用上涨空间近似）
        }

    def select_stocks(self, stock_data: pd.DataFrame, date: str) -> List[Tuple[str, float]]:
        df = stock_data.copy()

        # 估值因子：上涨空间越大越好
        df["value_score"] = df["upside_downside"].rank(pct=True)

        # 质量因子：ROE 越高越好
        df["quality_score"] = df["roe"].rank(pct=True)

        # 成长因子：增速越高越好
        df["growth_score"] = df["profit_growth"].rank(pct=True)

        # 规模因子：市值越小越好（小市值溢价）
        df["size_score"] = 1 - df["market_cap"].rank(pct=True)

        # 动量因子：用 PE 分位近似（低 PE = 可能被低估=潜在反转）
        df["momentum_score"] = 1 - df["pe"].rank(pct=True)

        # 综合得分
        df["total_score"] = (
            df["value_score"] * self.weights.get("value", 0.3)
            + df["quality_score"] * self.weights.get("quality", 0.25)
            + df["growth_score"] * self.weights.get("growth", 0.25)
            + df["size_score"] * self.weights.get("size", 0.1)
            + df["momentum_score"] * self.weights.get("momentum", 0.1)
        )

        df = df.sort_values("total_score", ascending=False)
        selected = df.head(self.top_n)["ts_code"].tolist()
        return self._rank_weighted(selected, decay=0.9)
