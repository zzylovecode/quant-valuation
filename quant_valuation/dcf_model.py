"""
DCF 折现现金流估值模型
=======================

实现两种 DCF 方法：
1. FCFF 模型 (公司自由现金流) → 企业价值 → 股权价值 → 每股内在价值
2. FCFE 模型 (股权自由现金流) → 直接得到股权价值 → 每股内在价值

支持两阶段模型：
- 明确预测期 (high growth period)：高速增长
- 永续增长期 (terminal period)：稳定增长到永远
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .financial_data import FinancialData


@dataclass
class DCFResult:
    """DCF 估值结果"""

    method: str  # "FCFF" 或 "FCFE"
    intrinsic_value_per_share: float  # 每股内在价值
    equity_value: float  # 股权总价值（亿元）
    enterprise_value: float = 0.0  # 企业价值（FCFF方法才有）
    terminal_value: float = 0.0  # 终值
    pv_of_explicit_period: float = 0.0  # 明确预测期现值
    discount_rate: float = 0.0  # 使用的折现率
    fcf_list: List[float] = field(default_factory=list)  # 各期自由现金流
    assumptions: Dict = field(default_factory=dict)  # 使用的假设参数

    def upside_downside(self, current_price: float) -> float:
        """相对当前价格的涨跌空间（正数为低估，负数为高估）"""
        if current_price <= 0:
            return 0.0
        return (self.intrinsic_value_per_share - current_price) / current_price

    def summary(self, current_price: float = 0.0) -> str:
        lines = [
            f"=== DCF 估值结果 ({self.method}) ===",
            f"每股内在价值: {self.intrinsic_value_per_share:.2f} 元",
            f"股权总价值: {self.equity_value:.2f} 亿元",
            f"折现率: {self.discount_rate*100:.2f}%",
            f"明确预测期现值: {self.pv_of_explicit_period:.2f} 亿元",
            f"终值: {self.terminal_value:.2f} 亿元",
        ]
        if self.enterprise_value > 0:
            lines.insert(3, f"企业价值 EV: {self.enterprise_value:.2f} 亿元")
        if current_price > 0:
            ud = self.upside_downside(current_price)
            lines.append(f"当前股价: {current_price:.2f} 元")
            lines.append(f"涨跌空间: {ud*100:.2f}% ({'低估' if ud > 0 else '高估'})")
        return "\n".join(lines)


class DCFModel:
    """
    DCF 折现现金流估值模型

    使用方法：
        model = DCFModel(financial_data)
        result = model.fcff_valuation(
            growth_rate=0.15,
            high_growth_years=5,
            terminal_growth=0.03,
            wacc=0.09,
        )
    """

    def __init__(self, data: FinancialData):
        self.data = data

    # ---------- 核心：FCFF 模型 ----------

    def fcff_valuation(
        self,
        growth_rate: float = 0.10,
        high_growth_years: int = 5,
        terminal_growth: float = 0.03,
        wacc: Optional[float] = None,
        base_fcff: Optional[float] = None,
        tax_rate: float = 0.25,
    ) -> DCFResult:
        """
        公司自由现金流 (FCFF) 估值法

        Args:
            growth_rate: 高速增长期 FCFF 年增长率
            high_growth_years: 高速增长期年数
            terminal_growth: 永续增长率 (g)，通常接近 GDP 增速
            wacc: 加权平均资本成本。为 None 时自动估算
            base_fcff: 基期 FCFF（亿元）。为 None 时从财报数据估算
            tax_rate: 企业所得税率

        Returns:
            DCFResult 估值结果对象
        """
        # 1. 估算基期 FCFF
        if base_fcff is None:
            base_fcff = self._estimate_fcff(tax_rate=tax_rate)

        # 2. 估算 WACC
        if wacc is None:
            wacc = self._estimate_wacc(tax_rate=tax_rate)

        # 3. 生成预测期 FCFF
        fcff_list = []
        current = base_fcff
        for _ in range(high_growth_years):
            current *= 1 + growth_rate
            fcff_list.append(current)

        # 4. 计算明确预测期现值
        pv_explicit = 0.0
        for i, fcf in enumerate(fcff_list):
            pv_explicit += fcf / ((1 + wacc) ** (i + 1))

        # 5. 计算终值（Gordon 增长模型）
        final_fcf = fcff_list[-1] * (1 + terminal_growth)
        if wacc <= terminal_growth:
            raise ValueError(
                f"WACC ({wacc*100:.2f}%) 必须大于永续增长率 ({terminal_growth*100:.2f}%)"
            )
        terminal_value = final_fcf / (wacc - terminal_growth)
        pv_terminal = terminal_value / ((1 + wacc) ** high_growth_years)

        # 6. 企业价值 = 预测期现值 + 终值现值
        ev = pv_explicit + pv_terminal

        # 7. 股权价值 = 企业价值 - 净负债
        net_debt = self.data.calc_net_debt()
        equity_value = ev - net_debt
        if equity_value <= 0:
            equity_value = 0.0001  # 防止除零

        # 8. 每股内在价值
        per_share = equity_value / self.data.total_shares

        return DCFResult(
            method="FCFF",
            intrinsic_value_per_share=per_share,
            equity_value=equity_value,
            enterprise_value=ev,
            terminal_value=terminal_value,
            pv_of_explicit_period=pv_explicit,
            discount_rate=wacc,
            fcf_list=fcff_list,
            assumptions={
                "growth_rate": growth_rate,
                "high_growth_years": high_growth_years,
                "terminal_growth": terminal_growth,
                "wacc": wacc,
                "base_fcff": base_fcff,
                "tax_rate": tax_rate,
                "net_debt": net_debt,
            },
        )

    # ---------- 核心：FCFE 模型 ----------

    def fcfe_valuation(
        self,
        growth_rate: float = 0.10,
        high_growth_years: int = 5,
        terminal_growth: float = 0.03,
        cost_of_equity: Optional[float] = None,
        base_fcfe: Optional[float] = None,
        tax_rate: float = 0.25,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> DCFResult:
        """
        股权自由现金流 (FCFE) 估值法

        Args:
            growth_rate: 高速增长期 FCFE 年增长率
            high_growth_years: 高速增长期年数
            terminal_growth: 永续增长率
            cost_of_equity: 股权资本成本 Ke。为 None 时用 CAPM 估算
            base_fcfe: 基期 FCFE（亿元）。为 None 时从财报估算
            tax_rate: 企业所得税率
            risk_free_rate: 无风险利率 (CAPM)
            equity_risk_premium: 股权风险溢价 (CAPM)
            beta: 贝塔系数 (CAPM)

        Returns:
            DCFResult 估值结果对象
        """
        # 1. 估算基期 FCFE
        if base_fcfe is None:
            base_fcfe = self._estimate_fcfe()

        # 2. 估算股权成本 Ke
        if cost_of_equity is None:
            cost_of_equity = self._capm(risk_free_rate, equity_risk_premium, beta)

        # 3. 生成预测期 FCFE
        fcfe_list = []
        current = base_fcfe
        for _ in range(high_growth_years):
            current *= 1 + growth_rate
            fcfe_list.append(current)

        # 4. 明确预测期现值
        pv_explicit = 0.0
        for i, fcf in enumerate(fcfe_list):
            pv_explicit += fcf / ((1 + cost_of_equity) ** (i + 1))

        # 5. 终值
        final_fcf = fcfe_list[-1] * (1 + terminal_growth)
        if cost_of_equity <= terminal_growth:
            raise ValueError(
                f"Ke ({cost_of_equity*100:.2f}%) 必须大于永续增长率 ({terminal_growth*100:.2f}%)"
            )
        terminal_value = final_fcf / (cost_of_equity - terminal_growth)
        pv_terminal = terminal_value / ((1 + cost_of_equity) ** high_growth_years)

        # 6. 股权价值
        equity_value = pv_explicit + pv_terminal
        if equity_value <= 0:
            equity_value = 0.0001

        per_share = equity_value / self.data.total_shares

        return DCFResult(
            method="FCFE",
            intrinsic_value_per_share=per_share,
            equity_value=equity_value,
            enterprise_value=0.0,
            terminal_value=terminal_value,
            pv_of_explicit_period=pv_explicit,
            discount_rate=cost_of_equity,
            fcf_list=fcfe_list,
            assumptions={
                "growth_rate": growth_rate,
                "high_growth_years": high_growth_years,
                "terminal_growth": terminal_growth,
                "cost_of_equity": cost_of_equity,
                "base_fcfe": base_fcfe,
                "risk_free_rate": risk_free_rate,
                "equity_risk_premium": equity_risk_premium,
                "beta": beta,
            },
        )

    # ---------- 辅助方法 ----------

    def _estimate_fcff(self, tax_rate: float = 0.25) -> float:
        """
        估算 FCFF = EBIT × (1 - 税率) + 折旧摊销 - 资本支出 - 营运资本增加
        简化版本：若缺少数据，用经营现金流近似
        """
        if self.data.ebitda > 0 and self.data.ebit > 0:
            # 完整公式
            depreciation = self.data.ebitda - self.data.ebit
            nopat = self.data.ebit * (1 - tax_rate)
            # 用经营现金流近似 (经营现金流 ≈ NOPAT + 折旧 - 营运资本增加)
            if self.data.operating_cash_flow > 0 and self.data.capex > 0:
                return self.data.operating_cash_flow + self.data.interest_bearing_debt * 0.04 * (1 - tax_rate) - self.data.capex
            return nopat + depreciation - self.data.capex

        if self.data.operating_cash_flow > 0 and self.data.capex > 0:
            # 经营现金流 - 资本支出 + 利息税后（近似）
            interest_approx = self.data.interest_bearing_debt * 0.04
            return self.data.operating_cash_flow + interest_approx * (1 - tax_rate) - self.data.capex

        # 最简化：用净利润近似
        return max(self.data.net_profit * 0.8, 0.001)

    def _estimate_fcfe(self) -> float:
        """
        估算 FCFE = 净利润 + 折旧摊销 - 资本支出 - 营运资本增加 + 净借款
        简化版本
        """
        # FCFE ≈ 经营现金流 - 资本支出 + 净借款
        if self.data.operating_cash_flow > 0 and self.data.capex > 0:
            # 假设净借款约为资本支出的一部分（维持债务比率不变）
            net_borrowing = self.data.capex * 0.3
            return self.data.operating_cash_flow - self.data.capex + net_borrowing

        # 简化：用净利润的一定比例
        return max(self.data.net_profit * 0.7, 0.001)

    def _estimate_wacc(
        self,
        tax_rate: float = 0.25,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
        cost_of_debt: float = 0.045,
    ) -> float:
        """
        估算 WACC = E/V × Ke + D/V × Kd × (1 - T)

        若数据充足，用实际资本结构；否则用默认 70% 股权 + 30% 债务
        """
        ke = self._capm(risk_free_rate, equity_risk_premium, beta)

        # 估算资本结构
        market_cap = self.data.calc_market_cap()
        if market_cap > 0 and self.data.interest_bearing_debt > 0:
            debt = self.data.interest_bearing_debt
            v = market_cap + debt
            we = market_cap / v
            wd = debt / v
        else:
            we = 0.75
            wd = 0.25

        wacc = we * ke + wd * cost_of_debt * (1 - tax_rate)
        return max(wacc, 0.05)  # 不低于 5%

    def _capm(
        self,
        risk_free_rate: float = 0.03,
        equity_risk_premium: float = 0.06,
        beta: float = 1.0,
    ) -> float:
        """CAPM: Ke = Rf + β × ERP"""
        return risk_free_rate + beta * equity_risk_premium

    # ---------- 敏感性分析 ----------

    def sensitivity_analysis(
        self,
        method: str = "FCFF",
        growth_range: Tuple[float, float, int] = (0.05, 0.20, 4),
        wacc_range: Tuple[float, float, int] = (0.07, 0.12, 4),
        terminal_growth: float = 0.03,
        high_growth_years: int = 5,
    ) -> Dict[str, Dict[float, Dict[float, float]]]:
        """
        二维敏感性分析：增长率 × 折现率 对内在价值的影响

        Args:
            method: "FCFF" 或 "FCFE"
            growth_range: (最小值, 最大值, 点数)
            wacc_range: (最小值, 最大值, 点数)

        Returns:
            嵌套字典: {增长率: {折现率: 每股内在价值}}
        """
        g_min, g_max, g_n = growth_range
        w_min, w_max, w_n = wacc_range

        growth_rates = [g_min + (g_max - g_min) * i / max(g_n - 1, 1) for i in range(g_n)]
        wacc_values = [w_min + (w_max - w_min) * i / max(w_n - 1, 1) for i in range(w_n)]

        results: Dict[str, Dict[float, Dict[float, float]]] = {
            "growth_rates": {},
        }

        for g in growth_rates:
            results["growth_rates"][round(g, 4)] = {}
            for w in wacc_values:
                if method == "FCFF":
                    res = self.fcff_valuation(
                        growth_rate=g,
                        high_growth_years=high_growth_years,
                        terminal_growth=terminal_growth,
                        wacc=w,
                    )
                else:
                    res = self.fcfe_valuation(
                        growth_rate=g,
                        high_growth_years=high_growth_years,
                        terminal_growth=terminal_growth,
                        cost_of_equity=w,
                    )
                results["growth_rates"][round(g, 4)][round(w, 4)] = round(
                    res.intrinsic_value_per_share, 2
                )

        return results
