"""
估值筛选器
==========

从批量估值结果中按条件筛选和排序，生成各种排行榜：
  - 低估榜（上涨空间最大）
  - 高估榜（下跌空间最大）
  - 低 PE / 低 PB 榜
  - 高 ROE 且低估（质优价廉）
  - 高成长且合理估值
"""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .batch_valuator import StockValuationResult


class ValuationScreener:
    """
    估值筛选器

    使用方式：
        screener = ValuationScreener(results)
        # 低估榜（上涨空间 > 30%）
        undervalued = screener.undervalued(min_upside=0.30)
        # 质优价廉（高 ROE + 低估）
        quality = screener.quality_value(min_roe=0.15, min_upside=0.20)
        # 自定义筛选
        filtered = screener.filter(lambda r: r.pe < 10 and r.roe > 0.10)
    """

    def __init__(self, results: List[StockValuationResult]):
        self.results = results

    # ---------- 基础筛选 ----------

    def filter(
        self,
        condition: Callable[[StockValuationResult], bool],
        sort_by: str = "upside_downside",
        ascending: bool = False,
        limit: int = 0,
    ) -> List[StockValuationResult]:
        """
        自定义筛选

        Args:
            condition: 筛选条件函数
            sort_by: 排序字段名
            ascending: 是否升序
            limit: 返回数量限制，0 表示全部
        """
        filtered = [r for r in self.results if condition(r)]
        filtered.sort(key=lambda r: getattr(r, sort_by, 0), reverse=not ascending)
        if limit > 0:
            filtered = filtered[:limit]
        return filtered

    # ---------- 估值相关榜单 ----------

    def undervalued(
        self,
        min_upside: float = 0.20,
        min_confidence: str = "中等",
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        低估榜：上涨空间大于 min_upside

        Args:
            min_upside: 最小上涨空间（如 0.20 表示 20%）
            min_confidence: 最低可信度（高/中等/低）
            limit: 返回数量
        """
        confidence_rank = {"高": 3, "中等": 2, "低": 1}
        min_rank = confidence_rank.get(min_confidence, 0)

        return self.filter(
            lambda r: (
                r.upside_downside >= min_upside
                and confidence_rank.get(r.confidence, 0) >= min_rank
            ),
            sort_by="upside_downside",
            ascending=False,
            limit=limit,
        )

    def overvalued(
        self,
        max_upside: float = -0.20,
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        高估榜：下跌空间大于 max_upside（绝对值）
        """
        return self.filter(
            lambda r: r.upside_downside <= max_upside,
            sort_by="upside_downside",
            ascending=True,
            limit=limit,
        )

    def reasonable(
        self,
        upside_range: tuple = (-0.15, 0.20),
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        估值合理榜：涨跌空间在合理范围内
        """
        low, high = upside_range
        return self.filter(
            lambda r: low <= r.upside_downside <= high,
            sort_by="roe",
            ascending=False,
            limit=limit,
        )

    # ---------- 质量 + 估值 组合筛选 ----------

    def quality_value(
        self,
        min_roe: float = 0.15,
        min_upside: float = 0.15,
        min_profit: float = 5.0,
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        质优价廉榜：高 ROE + 低估 + 盈利规模

        经典价值投资策略：找好公司（高 ROE）+ 好价格（低估）
        """
        return self.filter(
            lambda r: (
                r.roe >= min_roe
                and r.upside_downside >= min_upside
                and r.net_profit >= min_profit
            ),
            sort_by="upside_downside",
            ascending=False,
            limit=limit,
        )

    def growth_at_reasonable_price(
        self,
        min_growth: float = 0.15,
        max_upside: float = 0.50,
        min_upside: float = -0.10,
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        GARP 策略：合理价格下的成长股

        高增长 + 估值不极端（不过度高估也不过度低估，后者可能有陷阱）
        """
        return self.filter(
            lambda r: (
                r.profit_growth >= min_growth
                and min_upside <= r.upside_downside <= max_upside
            ),
            sort_by="profit_growth",
            ascending=False,
            limit=limit,
        )

    def deep_value(
        self,
        max_pe: float = 15.0,
        max_pb: float = 1.5,
        min_roe: float = 0.08,
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        深度价值：低 PE + 低 PB + 正 ROE
        """
        return self.filter(
            lambda r: (
                0 < r.pe <= max_pe
                and 0 < r.pb <= max_pb
                and r.roe >= min_roe
            ),
            sort_by="pe",
            ascending=True,
            limit=limit,
        )

    def high_dividend_value(
        self,
        min_dividend_yield: float = 0.03,
        min_upside: float = 0.0,
        limit: int = 20,
    ) -> List[StockValuationResult]:
        """
        高股息价值股（需要股息数据，这里用估值结果中的分红信息近似）
        注：StockValuationResult 中不含股息率，需结合原始 FinancialData
        """
        # 此方法依赖额外数据，实际使用时请结合 FinancialData
        return self.filter(
            lambda r: r.upside_downside >= min_upside,
            sort_by="upside_downside",
            ascending=False,
            limit=limit,
        )

    # ---------- 排行榜（排序） ----------

    def top_by_upside(self, n: int = 20) -> List[StockValuationResult]:
        """上涨空间最大 Top N"""
        return sorted(self.results, key=lambda r: r.upside_downside, reverse=True)[:n]

    def bottom_by_upside(self, n: int = 20) -> List[StockValuationResult]:
        """下跌空间最大 Top N"""
        return sorted(self.results, key=lambda r: r.upside_downside)[:n]

    def top_by_roe(self, n: int = 20) -> List[StockValuationResult]:
        """ROE 最高 Top N"""
        return sorted(self.results, key=lambda r: r.roe, reverse=True)[:n]

    def top_by_growth(self, n: int = 20) -> List[StockValuationResult]:
        """利润增速最高 Top N"""
        return sorted(self.results, key=lambda r: r.profit_growth, reverse=True)[:n]

    def lowest_pe(self, n: int = 20) -> List[StockValuationResult]:
        """PE 最低 Top N（正值）"""
        positive = [r for r in self.results if r.pe > 0]
        return sorted(positive, key=lambda r: r.pe)[:n]

    def lowest_pb(self, n: int = 20) -> List[StockValuationResult]:
        """PB 最低 Top N（正值）"""
        positive = [r for r in self.results if r.pb > 0]
        return sorted(positive, key=lambda r: r.pb)[:n]

    # ---------- 分布统计 ----------

    def rating_distribution(self) -> Dict[str, int]:
        """估值评级分布"""
        dist: Dict[str, int] = {}
        for r in self.results:
            dist[r.rating] = dist.get(r.rating, 0) + 1
        return dist

    def upside_distribution(
        self,
        bins: Optional[List[tuple]] = None,
    ) -> Dict[str, int]:
        """
        涨跌空间分布

        默认分桶：
          - 严重低估: >= 50%
          - 低估: 20% ~ 50%
          - 合理偏低: 0% ~ 20%
          - 合理偏高: -15% ~ 0%
          - 高估: -40% ~ -15%
          - 严重高估: < -40%
        """
        if bins is None:
            bins = [
                ("严重低估", lambda u: u >= 0.50),
                ("低估", lambda u: 0.20 <= u < 0.50),
                ("合理偏低", lambda u: 0.0 <= u < 0.20),
                ("合理偏高", lambda u: -0.15 <= u < 0.0),
                ("高估", lambda u: -0.40 <= u < -0.15),
                ("严重高估", lambda u: u < -0.40),
            ]

        dist = {label: 0 for label, _ in bins}
        for r in self.results:
            for label, condition in bins:
                if condition(r.upside_downside):
                    dist[label] += 1
                    break

        return dist
