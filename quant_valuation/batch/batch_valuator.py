"""
批量估值引擎
============

对一批 FinancialData 对象执行综合估值，
输出标准化的估值结果列表，供后续筛选排序。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..financial_data import FinancialData
from ..valuation_analyzer import ValuationAnalyzer, ValuationSummary
from ..industry_assumptions import resolve_terminal_growth


@dataclass
class StockValuationResult:
    """单只股票的估值结果"""

    ts_code: str
    name: str
    current_price: float
    intrinsic_value: float       # 加权平均内在价值
    upside_downside: float       # 涨跌空间
    rating: str                  # 估值评级
    confidence: str              # 可信度

    # 各方法估值
    method_values: Dict[str, float] = field(default_factory=dict)
    method_upsides: Dict[str, float] = field(default_factory=dict)

    # 基本财务指标
    pe: float = 0.0
    pb: float = 0.0
    roe: float = 0.0
    revenue: float = 0.0
    net_profit: float = 0.0
    market_cap: float = 0.0
    profit_growth: float = 0.0

    # 估值区间
    low_value: float = 0.0
    high_value: float = 0.0
    median_value: float = 0.0

    # 假设参数
    terminal_growth: float = 0.03      # 实际使用的永续增长率
    growth_assumption_note: str = ""   # 行业假设说明

    def to_dict(self) -> Dict:
        """转换为字典（用于导出）"""
        return {
            "股票代码": self.ts_code,
            "股票名称": self.name,
            "当前价": round(self.current_price, 2),
            "内在价值": round(self.intrinsic_value, 2),
            "涨跌空间": round(self.upside_downside * 100, 2),
            "估值评级": self.rating,
            "可信度": self.confidence,
            "PE": round(self.pe, 2),
            "PB": round(self.pb, 2),
            "ROE(%)": round(self.roe * 100, 2),
            "营收(亿)": round(self.revenue, 2),
            "净利润(亿)": round(self.net_profit, 2),
            "市值(亿)": round(self.market_cap, 2),
            "利润增速(%)": round(self.profit_growth * 100, 2),
            "保守估值": round(self.low_value, 2),
            "乐观估值": round(self.high_value, 2),
            "中位估值": round(self.median_value, 2),
            "永续增长率(%)": round(self.terminal_growth * 100, 2),
        }


class BatchValuator:
    """
    批量估值引擎

    使用方式：
        valuator = BatchValuator()
        results = valuator.valuate(data_list)
        # results 是 StockValuationResult 列表
    """

    def __init__(
        self,
        company_type: str = "growth",
        dcf_growth_rate: Optional[float] = None,
        dcf_years: int = 5,
        terminal_growth: Optional[float] = None,
        enable_ddm: bool = True,
        enable_rim: bool = True,
        verbose: bool = True,
    ):
        """
        Args:
            company_type: 公司类型模板 (growth/value/mature/cyclical/high_tech/financial)
            dcf_growth_rate: DCF 增长率，None 表示自动用历史 CAGR
            dcf_years: DCF 高速增长期年数
            terminal_growth: 永续增长率。None 表示按行业自动取假设
                （见 industry_assumptions.py，白酒板块下调至 1%）；
                传入具体数值则对全部股票统一使用该值
            enable_ddm: 是否启用 DDM
            enable_rim: 是否启用剩余收益模型
            verbose: 是否打印进度
        """
        self.company_type = company_type
        self.dcf_growth_rate = dcf_growth_rate
        self.dcf_years = dcf_years
        self.terminal_growth = terminal_growth
        self.enable_ddm = enable_ddm
        self.enable_rim = enable_rim
        self.verbose = verbose

    def valuate(
        self,
        data_list: List[FinancialData],
    ) -> List[StockValuationResult]:
        """
        对一批股票执行估值

        Args:
            data_list: FinancialData 对象列表

        Returns:
            StockValuationResult 列表（按涨跌空间降序排列）
        """
        results: List[StockValuationResult] = []
        total = len(data_list)

        if self.verbose:
            print(f"\n开始批量估值，共 {total} 只股票...\n")

        for i, data in enumerate(data_list):
            if self.verbose:
                print(f"  [{i+1}/{total}] {data.ticker} {data.name}...", end=" ", flush=True)

            try:
                result = self._valuate_one(data)
                results.append(result)
                if self.verbose:
                    status = "↑" if result.upside_downside > 0 else "↓"
                    print(f"{status} {result.upside_downside*100:+.1f}% ({result.rating})")

            except Exception as e:
                if self.verbose:
                    print(f"✗ 估值失败: {e}")

        # 按涨跌空间降序排列
        results.sort(key=lambda x: x.upside_downside, reverse=True)

        if self.verbose:
            print(f"\n估值完成：成功 {len(results)}/{total} 只")

        return results

    def _valuate_one(self, data: FinancialData) -> StockValuationResult:
        """对单只股票执行估值"""
        analyzer = ValuationAnalyzer(data)

        # 永续增长率：显式指定则统一使用，否则按行业假设（白酒下调至 1%）
        if self.terminal_growth is not None:
            terminal_growth = self.terminal_growth
            assumption_note = ""
        else:
            terminal_growth, assumption_note = resolve_terminal_growth(data)

        # 自动估算增长率
        growth_rate = self.dcf_growth_rate
        if growth_rate is None:
            growth_rate = data.calc_profit_growth_rate(3)
        # 限制在合理范围
        growth_rate = max(0.02, min(growth_rate, 0.25))

        # 权重配置
        weights = ValuationAnalyzer.get_weights_for_company_type(self.company_type)

        # 执行综合估值
        summary = analyzer.full_valuation(
            weights=weights,
            dcf_params={
                "growth_rate": growth_rate,
                "high_growth_years": self.dcf_years,
                "terminal_growth": terminal_growth,
            },
            relative_params={
                "industry_pe": data.industry_pe if data.industry_pe > 0 else None,
                "industry_pb": data.industry_pb if data.industry_pb > 0 else None,
                "expected_growth": growth_rate,
                "roe_adjusted": True,
            },
            ddm_params={
                "high_growth_rate": min(growth_rate * 0.7, 0.10),
                "high_growth_years": 5,
                "stable_growth_rate": terminal_growth,
            },
            rim_params={
                "high_growth_years": 5,
                "high_growth_roe": min(data.calc_roe(), 0.30),
                "terminal_roe": 0.10,
            },
            enable_ddm=self.enable_ddm and data.dividend_per_share > 0,
            enable_rim=self.enable_rim and data.bvps > 0,
        )

        # 构造结果
        result = StockValuationResult(
            ts_code=data.ticker,
            name=data.name,
            current_price=data.current_price,
            intrinsic_value=summary.weighted_value,
            upside_downside=summary.weighted_upside,
            rating=summary.rating,
            confidence=summary.confidence,
            method_values=dict(summary.method_values),
            method_upsides=dict(summary.method_upsides),
            pe=data.calc_pe(),
            pb=data.calc_pb(),
            roe=data.calc_roe(),
            revenue=data.revenue,
            net_profit=data.net_profit,
            market_cap=data.calc_market_cap(),
            profit_growth=data.calc_profit_growth_rate(3),
            low_value=summary.low_value,
            high_value=summary.high_value,
            median_value=summary.median_value,
            terminal_growth=terminal_growth,
            growth_assumption_note=assumption_note,
        )

        return result

    # ---------- 统计摘要 ----------

    @staticmethod
    def summary(results: List[StockValuationResult]) -> Dict:
        """生成批量估值结果的统计摘要"""
        if not results:
            return {"total": 0}

        upsides = [r.upside_downside for r in results]
        ratings = {}
        for r in results:
            ratings[r.rating] = ratings.get(r.rating, 0) + 1

        return {
            "total": len(results),
            "avg_upside": sum(upsides) / len(upsides),
            "median_upside": sorted(upsides)[len(upsides) // 2],
            "max_upside": max(upsides),
            "min_upside": min(upsides),
            "ratings": ratings,
            "undervalued_count": sum(1 for u in upsides if u > 0.2),
            "overvalued_count": sum(1 for u in upsides if u < -0.2),
        }
