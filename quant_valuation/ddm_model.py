"""
股息贴现模型 (DDM) & 剩余收益模型 (RIM)
=======================================

DDM: 股息贴现模型，适用于高分红、稳定派息的成熟公司
  - 零增长模型 (Zero Growth DDM)
  - 固定增长模型 (Gordon Growth Model)
  - 两阶段增长模型 (Two-Stage DDM)

RIM: 剩余收益模型（也称 EVA 模型）
  企业价值 = 账面价值 + 未来剩余收益的现值
  剩余收益 = 净利润 - 股权成本 × 期初账面价值
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .financial_data import FinancialData


@dataclass
class DDMResult:
    """DDM 估值结果"""

    model: str  # zero_growth / gordon / two_stage
    intrinsic_value_per_share: float
    cost_of_equity: float
    assumptions: Dict = field(default_factory=dict)

    def upside_downside(self, current_price: float) -> float:
        if current_price <= 0:
            return 0.0
        return (self.intrinsic_value_per_share - current_price) / current_price

    def summary(self, current_price: float = 0.0) -> str:
        lines = [
            f"=== DDM 估值结果 ({self.model}) ===",
            f"每股内在价值: {self.intrinsic_value_per_share:.2f} 元",
            f"股权成本 Ke: {self.cost_of_equity*100:.2f}%",
        ]
        if current_price > 0:
            ud = self.upside_downside(current_price)
            lines.append(f"当前股价: {current_price:.2f} 元")
            lines.append(f"涨跌空间: {ud*100:.2f}% ({'低估' if ud > 0 else '高估'})")
        return "\n".join(lines)


@dataclass
class RIMResult:
    """剩余收益模型结果"""

    intrinsic_value_per_share: float
    book_value_per_share: float
    pv_of_residual_income: float
    cost_of_equity: float
    assumptions: Dict = field(default_factory=dict)

    def upside_downside(self, current_price: float) -> float:
        if current_price <= 0:
            return 0.0
        return (self.intrinsic_value_per_share - current_price) / current_price

    def summary(self, current_price: float = 0.0) -> str:
        lines = [
            "=== 剩余收益模型 (RIM) 估值结果 ===",
            f"每股内在价值: {self.intrinsic_value_per_share:.2f} 元",
            f"每股净资产 (BVPS): {self.book_value_per_share:.2f} 元",
            f"剩余收益现值: {self.pv_of_residual_income:.2f} 元/股",
            f"股权成本 Ke: {self.cost_of_equity*100:.2f}%",
        ]
        if current_price > 0:
            ud = self.upside_downside(current_price)
            lines.append(f"当前股价: {current_price:.2f} 元")
            lines.append(f"涨跌空间: {ud*100:.2f}% ({'低估' if ud > 0 else '高估'})")
        return "\n".join(lines)


class DDMModel:
    """股息贴现模型"""

    def __init__(self, data: FinancialData):
        self.data = data

    def zero_growth_ddm(
        self,
        cost_of_equity: Optional[float] = None,
        dividend: Optional[float] = None,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> DDMResult:
        """
        零增长 DDM：假设股息永远不变
        V = D / Ke
        适用于成熟稳定、分红固定的公司（如公用事业）
        """
        if dividend is None:
            dividend = self.data.dividend_per_share
        if dividend <= 0:
            raise ValueError("每股股息必须大于 0")

        if cost_of_equity is None:
            cost_of_equity = risk_free_rate + beta * equity_risk_premium

        if cost_of_equity <= 0:
            raise ValueError("股权成本必须大于 0")

        intrinsic = dividend / cost_of_equity

        return DDMResult(
            model="zero_growth",
            intrinsic_value_per_share=intrinsic,
            cost_of_equity=cost_of_equity,
            assumptions={
                "dividend": dividend,
                "cost_of_equity": cost_of_equity,
            },
        )

    def gordon_growth_ddm(
        self,
        growth_rate: float = 0.03,
        cost_of_equity: Optional[float] = None,
        dividend: Optional[float] = None,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> DDMResult:
        """
        Gordon 增长模型（固定增长 DDM）
        V = D1 / (Ke - g)
        D1 = D0 × (1 + g)

        适用于股息稳定增长的成熟公司
        """
        if dividend is None:
            dividend = self.data.dividend_per_share
        if dividend <= 0:
            raise ValueError("每股股息必须大于 0")

        if cost_of_equity is None:
            cost_of_equity = risk_free_rate + beta * equity_risk_premium

        if cost_of_equity <= growth_rate:
            raise ValueError(
                f"股权成本 ({cost_of_equity*100:.2f}%) 必须大于增长率 ({growth_rate*100:.2f}%)"
            )

        d1 = dividend * (1 + growth_rate)
        intrinsic = d1 / (cost_of_equity - growth_rate)

        return DDMResult(
            model="gordon_growth",
            intrinsic_value_per_share=intrinsic,
            cost_of_equity=cost_of_equity,
            assumptions={
                "dividend_d0": dividend,
                "dividend_d1": d1,
                "growth_rate": growth_rate,
                "cost_of_equity": cost_of_equity,
            },
        )

    def two_stage_ddm(
        self,
        high_growth_rate: float = 0.08,
        high_growth_years: int = 5,
        stable_growth_rate: float = 0.03,
        cost_of_equity: Optional[float] = None,
        dividend: Optional[float] = None,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> DDMResult:
        """
        两阶段 DDM
        阶段1：高速增长期（高股息增长）
        阶段2：永续稳定增长期
        """
        if dividend is None:
            dividend = self.data.dividend_per_share
        if dividend <= 0:
            raise ValueError("每股股息必须大于 0")

        if cost_of_equity is None:
            cost_of_equity = risk_free_rate + beta * equity_risk_premium

        # 阶段1：预测期股息现值
        pv_dividends = 0.0
        current_div = dividend
        for i in range(high_growth_years):
            current_div *= 1 + high_growth_rate
            pv_dividends += current_div / ((1 + cost_of_equity) ** (i + 1))

        # 阶段2：终值（Gordon 模型）
        terminal_div = current_div * (1 + stable_growth_rate)
        if cost_of_equity <= stable_growth_rate:
            raise ValueError("稳定期股权成本必须大于稳定增长率")

        terminal_value = terminal_div / (cost_of_equity - stable_growth_rate)
        pv_terminal = terminal_value / ((1 + cost_of_equity) ** high_growth_years)

        intrinsic = pv_dividends + pv_terminal

        return DDMResult(
            model="two_stage",
            intrinsic_value_per_share=intrinsic,
            cost_of_equity=cost_of_equity,
            assumptions={
                "dividend_d0": dividend,
                "high_growth_rate": high_growth_rate,
                "high_growth_years": high_growth_years,
                "stable_growth_rate": stable_growth_rate,
                "pv_of_growth_period": pv_dividends,
                "terminal_value": terminal_value,
            },
        )


class ResidualIncomeModel:
    """
    剩余收益模型 (Residual Income Model)

    核心公式：
      每股内在价值 = BVPS + Σ(剩余收益_t / (1+Ke)^t)
      剩余收益 = EPS_t - Ke × BVPS_{t-1}

    优点：
      - 以账面价值为锚，估值更稳健
      - 适合轻资产、高 ROE 公司
    """

    def __init__(self, data: FinancialData):
        self.data = data

    def valuation(
        self,
        high_growth_years: int = 5,
        high_growth_roe: Optional[float] = None,
        terminal_roe: Optional[float] = None,
        cost_of_equity: Optional[float] = None,
        retention_ratio: Optional[float] = None,
        terminal_growth: float = 0.03,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> RIMResult:
        """
        两阶段剩余收益估值

        Args:
            high_growth_years: 高速增长期年数
            high_growth_roe: 高速增长期 ROE。默认用当前 ROE
            terminal_roe: 稳定期 ROE。默认 = Ke（剩余收益为0）
            cost_of_equity: 股权成本 Ke
            retention_ratio: 利润留存率 = 1 - 分红率
            terminal_growth: 永续增长率
        """
        bvps = self.data.bvps
        if bvps <= 0:
            raise ValueError("每股净资产必须大于 0")

        # 参数初始化
        if cost_of_equity is None:
            cost_of_equity = risk_free_rate + beta * equity_risk_premium

        if high_growth_roe is None:
            high_growth_roe = self.data.calc_roe()
        if high_growth_roe <= 0:
            high_growth_roe = 0.10  # 默认 10%

        if terminal_roe is None:
            terminal_roe = cost_of_equity  # 竞争均衡：ROE 回归到资本成本

        if retention_ratio is None:
            if self.data.dividend_payout_ratio > 0:
                retention_ratio = 1 - self.data.dividend_payout_ratio
            else:
                retention_ratio = 0.6  # 默认 60% 留存

        # 阶段1：预测期剩余收益
        pv_ri = 0.0
        current_bvps = bvps
        ri_list = []

        for i in range(high_growth_years):
            eps = current_bvps * high_growth_roe
            ri = eps - cost_of_equity * current_bvps
            ri_list.append(ri)
            pv_ri += ri / ((1 + cost_of_equity) ** (i + 1))
            # 期末账面价值 = 期初 + 留存收益
            current_bvps += eps * retention_ratio

        # 阶段2：终值（永续剩余收益）
        # 假设稳定期 ROE = terminal_roe，BVPS 按 terminal_growth 增长
        final_bvps = current_bvps
        final_ri = final_bvps * (terminal_roe - cost_of_equity)

        if terminal_roe == cost_of_equity:
            # 剩余收益为 0，终值为 0
            terminal_ri_value = 0.0
        else:
            if cost_of_equity <= terminal_growth:
                # 永续增长率过高，用有限期摊销法
                terminal_ri_value = 0.0
            else:
                # 永续增长的剩余收益
                terminal_ri_value = final_ri / (cost_of_equity - terminal_growth)

        pv_terminal_ri = terminal_ri_value / ((1 + cost_of_equity) ** high_growth_years)

        # 每股内在价值 = 账面价值 + 剩余收益现值
        intrinsic = bvps + pv_ri + pv_terminal_ri
        total_pv_ri = pv_ri + pv_terminal_ri

        return RIMResult(
            intrinsic_value_per_share=intrinsic,
            book_value_per_share=bvps,
            pv_of_residual_income=total_pv_ri,
            cost_of_equity=cost_of_equity,
            assumptions={
                "high_growth_years": high_growth_years,
                "high_growth_roe": high_growth_roe,
                "terminal_roe": terminal_roe,
                "cost_of_equity": cost_of_equity,
                "retention_ratio": retention_ratio,
                "terminal_growth": terminal_growth,
                "residual_income_list": ri_list,
                "ending_bvps": final_bvps,
            },
        )
