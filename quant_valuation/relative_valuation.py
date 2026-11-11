"""
相对估值模型
============

PE / PB / PEG / PS / EV/EBITDA 等多种相对估值方法。

相对估值核心逻辑：
  目标公司估值 = 目标公司指标 × 可比公司（或行业）估值倍数

支持：
  - 基于行业平均倍数的估值
  - 基于可比公司列表的估值
  - 历史估值分位判断
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .financial_data import FinancialData


@dataclass
class RelativeValuationResult:
    """相对估值结果"""

    method: str  # PE / PB / PEG / PS / EV_EBITDA
    target_multiple: float  # 目标估值倍数
    company_multiple: float  # 公司当前倍数
    intrinsic_value_per_share: float  # 每股内在价值
    upside_downside: float  # 涨跌空间
    assumptions: Dict = field(default_factory=dict)

    def summary(self) -> str:
        verdict = "低估" if self.upside_downside > 0 else "高估"
        lines = [
            f"=== 相对估值 ({self.method}) ===",
            f"公司当前{self.method}: {self.company_multiple:.2f}",
            f"目标{self.method}倍数: {self.target_multiple:.2f}",
            f"每股内在价值: {self.intrinsic_value_per_share:.2f} 元",
            f"涨跌空间: {self.upside_downside*100:.2f}% ({verdict})",
        ]
        return "\n".join(lines)


class RelativeValuation:
    """
    相对估值模型

    方法一览：
      - pe_valuation: 市盈率估值
      - pb_valuation: 市净率估值
      - peg_valuation: PEG 估值（考虑成长性的 PE）
      - ps_valuation: 市销率估值
      - ev_ebitda_valuation: EV/EBITDA 估值
    """

    def __init__(self, data: FinancialData):
        self.data = data

    # ---------- PE 估值 ----------

    def pe_valuation(
        self,
        target_pe: Optional[float] = None,
        industry_pe: Optional[float] = None,
        growth_adjusted: bool = False,
        expected_growth: Optional[float] = None,
    ) -> RelativeValuationResult:
        """
        市盈率 PE 估值

        Args:
            target_pe: 目标 PE 倍数。若为 None，优先使用 industry_pe
            industry_pe: 行业平均 PE。若为 None，使用 data.industry_pe
            growth_adjusted: 是否用成长性调整（PEG 思路）
            expected_growth: 预期净利润增长率（小数形式，如 0.15 表示 15%）

        Returns:
            RelativeValuationResult
        """
        if target_pe is None:
            if industry_pe is None:
                industry_pe = self.data.industry_pe
            if industry_pe <= 0:
                raise ValueError("需要提供 target_pe 或 industry_pe（行业平均PE）")
            target_pe = industry_pe

        # 成长性调整
        if growth_adjusted and expected_growth and expected_growth > 0:
            industry_growth = 0.08  # 默认行业增速 8%
            # PEG 思路：增长越快，可接受的 PE 越高
            # 目标 PE = 行业 PE × (公司增速 / 行业增速)
            target_pe = target_pe * (expected_growth / industry_growth)
            # 给予一定折价，避免过于乐观
            target_pe *= 0.8

        current_pe = self.data.calc_pe()
        if self.data.eps <= 0:
            intrinsic = 0.0
        else:
            intrinsic = self.data.eps * target_pe

        upside = (intrinsic - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return RelativeValuationResult(
            method="PE",
            target_multiple=target_pe,
            company_multiple=current_pe,
            intrinsic_value_per_share=intrinsic,
            upside_downside=upside,
            assumptions={
                "industry_pe": industry_pe,
                "growth_adjusted": growth_adjusted,
                "expected_growth": expected_growth or 0.0,
                "eps": self.data.eps,
            },
        )

    # ---------- PB 估值 ----------

    def pb_valuation(
        self,
        target_pb: Optional[float] = None,
        industry_pb: Optional[float] = None,
        roe_adjusted: bool = False,
    ) -> RelativeValuationResult:
        """
        市净率 PB 估值

        Args:
            target_pb: 目标 PB 倍数
            industry_pb: 行业平均 PB
            roe_adjusted: 是否用 ROE 调整（高 ROE 公司应享有更高 PB）

        理论关系: PB = ROE × PE
        """
        if target_pb is None:
            if industry_pb is None:
                industry_pb = self.data.industry_pb
            if industry_pb <= 0:
                raise ValueError("需要提供 target_pb 或 industry_pb（行业平均PB）")
            target_pb = industry_pb

        # ROE 调整
        if roe_adjusted:
            # 假设行业平均 ROE 为 10%
            industry_roe = 0.10
            company_roe = self.data.calc_roe()
            if industry_roe > 0 and company_roe > 0:
                # 合理 PB 与 ROE 正相关
                target_pb = target_pb * (company_roe / industry_roe)
                target_pb = max(target_pb, 0.5)  # 不低于 0.5 倍

        current_pb = self.data.calc_pb()
        if self.data.bvps <= 0:
            intrinsic = 0.0
        else:
            intrinsic = self.data.bvps * target_pb

        upside = (intrinsic - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return RelativeValuationResult(
            method="PB",
            target_multiple=target_pb,
            company_multiple=current_pb,
            intrinsic_value_per_share=intrinsic,
            upside_downside=upside,
            assumptions={
                "industry_pb": industry_pb or 0.0,
                "roe_adjusted": roe_adjusted,
                "company_roe": self.data.calc_roe(),
                "bvps": self.data.bvps,
            },
        )

    # ---------- PEG 估值 ----------

    def peg_valuation(
        self,
        target_peg: float = 1.0,
        expected_growth: Optional[float] = None,
        growth_years: int = 3,
    ) -> RelativeValuationResult:
        """
        PEG 估值法

        PEG = PE / (盈利增长率 × 100)
        PEG = 1 被认为估值合理

        Args:
            target_peg: 目标 PEG 比率，通常 1.0 为合理
            expected_growth: 预期净利润增长率（小数）。为 None 时用历史 CAGR
            growth_years: 历史增长率计算年数
        """
        if expected_growth is None:
            expected_growth = self.data.calc_profit_growth_rate(years=growth_years)
        if expected_growth <= 0:
            raise ValueError("PEG 估值需要正的盈利增长率")

        # 合理 PE = PEG × 增长率（百分比）
        target_pe = target_peg * expected_growth * 100
        current_pe = self.data.calc_pe()
        current_peg = current_pe / (expected_growth * 100) if expected_growth > 0 else float("inf")

        intrinsic = self.data.eps * target_pe if self.data.eps > 0 else 0.0
        upside = (intrinsic - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return RelativeValuationResult(
            method="PEG",
            target_multiple=target_peg,
            company_multiple=current_peg,
            intrinsic_value_per_share=intrinsic,
            upside_downside=upside,
            assumptions={
                "target_peg": target_peg,
                "expected_growth": expected_growth,
                "target_pe": target_pe,
                "current_pe": current_pe,
                "eps": self.data.eps,
            },
        )

    # ---------- PS 估值 ----------

    def ps_valuation(
        self,
        target_ps: float = 3.0,
        industry_ps: Optional[float] = None,
    ) -> RelativeValuationResult:
        """
        市销率 PS 估值
        适用于盈利不稳定但营收稳定增长的公司
        """
        if industry_ps is not None:
            target_ps = industry_ps

        current_ps = self.data.calc_ps()
        # 每股营收 = 营收 / 总股本
        revenue_per_share = self.data.revenue / self.data.total_shares if self.data.total_shares > 0 else 0.0
        intrinsic = revenue_per_share * target_ps

        upside = (intrinsic - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return RelativeValuationResult(
            method="PS",
            target_multiple=target_ps,
            company_multiple=current_ps,
            intrinsic_value_per_share=intrinsic,
            upside_downside=upside,
            assumptions={
                "target_ps": target_ps,
                "revenue_per_share": revenue_per_share,
            },
        )

    # ---------- EV/EBITDA 估值 ----------

    def ev_ebitda_valuation(
        self,
        target_ev_ebitda: float = 10.0,
        industry_ev_ebitda: Optional[float] = None,
    ) -> RelativeValuationResult:
        """
        EV/EBITDA 估值法
        适用于重资产、高折旧行业，消除资本结构差异
        """
        if industry_ev_ebitda is not None:
            target_ev_ebitda = industry_ev_ebitda

        if self.data.ebitda <= 0:
            raise ValueError("EBITDA 必须为正值才能使用 EV/EBITDA 估值")

        current_ev = self.data.calc_enterprise_value()
        current_ev_ebitda = current_ev / self.data.ebitda if self.data.ebitda > 0 else float("inf")

        # 目标 EV = EBITDA × 目标倍数
        target_ev = self.data.ebitda * target_ev_ebitda
        # 股权价值 = EV - 净负债
        target_equity = target_ev - self.data.calc_net_debt()
        intrinsic = target_equity / self.data.total_shares if self.data.total_shares > 0 else 0.0
        if intrinsic < 0:
            intrinsic = 0.0

        upside = (intrinsic - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return RelativeValuationResult(
            method="EV/EBITDA",
            target_multiple=target_ev_ebitda,
            company_multiple=current_ev_ebitda,
            intrinsic_value_per_share=intrinsic,
            upside_downside=upside,
            assumptions={
                "target_ev_ebitda": target_ev_ebitda,
                "ebitda": self.data.ebitda,
                "net_debt": self.data.calc_net_debt(),
                "target_ev": target_ev,
            },
        )

    # ---------- 综合相对估值 ----------

    def comprehensive_relative_valuation(
        self,
        methods: Optional[List[str]] = None,
        weights: Optional[Dict[str, float]] = None,
        **kwargs,
    ) -> Dict[str, object]:
        """
        综合相对估值：多种方法加权平均

        Args:
            methods: 要使用的方法列表，默认 ["PE", "PB", "PEG", "PS"]
            weights: 各方法权重，如 {"PE": 0.4, "PB": 0.3, ...}
            **kwargs: 传递给各估值方法的参数

        Returns:
            {
                "results": {method: RelativeValuationResult},
                "weighted_value": 加权平均内在价值,
                "upside_downside": 综合涨跌空间,
            }
        """
        if methods is None:
            methods = ["PE", "PB", "PEG", "PS"]

        # 默认等权
        if weights is None:
            weights = {m: 1.0 / len(methods) for m in methods}

        results = {}
        for method in methods:
            try:
                if method == "PE":
                    results[method] = self.pe_valuation(
                        industry_pe=kwargs.get("industry_pe"),
                        growth_adjusted=kwargs.get("growth_adjusted", False),
                        expected_growth=kwargs.get("expected_growth"),
                    )
                elif method == "PB":
                    results[method] = self.pb_valuation(
                        industry_pb=kwargs.get("industry_pb"),
                        roe_adjusted=kwargs.get("roe_adjusted", False),
                    )
                elif method == "PEG":
                    results[method] = self.peg_valuation(
                        target_peg=kwargs.get("target_peg", 1.0),
                        expected_growth=kwargs.get("expected_growth"),
                    )
                elif method == "PS":
                    results[method] = self.ps_valuation(
                        target_ps=kwargs.get("target_ps", 3.0),
                    )
                elif method == "EV/EBITDA":
                    results[method] = self.ev_ebitda_valuation(
                        target_ev_ebitda=kwargs.get("target_ev_ebitda", 10.0),
                    )
            except Exception:
                # 某个方法失败不影响其他
                continue

        if not results:
            raise ValueError("所有相对估值方法都失败了，请检查数据")

        # 重新归一化权重（只对成功的方法）
        valid_methods = list(results.keys())
        total_weight = sum(weights.get(m, 0) for m in valid_methods)
        if total_weight <= 0:
            total_weight = len(valid_methods)
            norm_weights = {m: 1.0 / len(valid_methods) for m in valid_methods}
        else:
            norm_weights = {m: weights.get(m, 0) / total_weight for m in valid_methods}

        weighted_value = sum(
            results[m].intrinsic_value_per_share * norm_weights[m]
            for m in valid_methods
        )
        upside = (weighted_value - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0.0

        return {
            "results": results,
            "weighted_value": weighted_value,
            "upside_downside": upside,
            "weights": norm_weights,
        }
