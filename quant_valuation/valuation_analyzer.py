"""
估值整合分析器
==============

综合多种估值方法，提供：
  1. 多方法综合估值（加权平均）
  2. 估值区间（安全边际）
  3. 估值评级（低估/合理/高估）
  4. 敏感性分析结果可视化数据
  5. 完整的估值报告输出
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .financial_data import FinancialData
from .dcf_model import DCFModel, DCFResult
from .relative_valuation import RelativeValuation, RelativeValuationResult
from .ddm_model import DDMModel, ResidualIncomeModel, DDMResult, RIMResult


@dataclass
class ValuationSummary:
    """综合估值汇总"""

    company_name: str
    ticker: str
    current_price: float

    # 各方法估值结果（每股内在价值）
    method_values: Dict[str, float] = field(default_factory=dict)
    method_upsides: Dict[str, float] = field(default_factory=dict)

    # 综合估值
    weighted_value: float = 0.0
    weighted_upside: float = 0.0
    weights: Dict[str, float] = field(default_factory=dict)

    # 估值区间
    low_value: float = 0.0   # 保守估值
    high_value: float = 0.0  # 乐观估值
    median_value: float = 0.0  # 中位数估值

    # 评级
    rating: str = "合理"  # 严重低估 / 低估 / 合理 / 高估 / 严重高估
    confidence: str = "中等"  # 高 / 中 / 低

    def summary(self) -> str:
        """格式化输出估值报告"""
        lines = [
            "=" * 60,
            f"  综合估值报告 — {self.company_name} ({self.ticker})",
            "=" * 60,
            f"当前股价: {self.current_price:.2f} 元",
            f"估值评级: {self.rating}",
            f"可信度: {self.confidence}",
            "",
            "-" * 60,
            f"{'估值方法':<15} {'内在价值(元)':>12} {'涨跌空间':>12} {'权重':>8}",
            "-" * 60,
        ]

        for method, value in self.method_values.items():
            upside = self.method_upsides.get(method, 0)
            weight = self.weights.get(method, 0)
            lines.append(
                f"{method:<15} {value:>12.2f} {upside*100:>11.2f}% {weight*100:>7.1f}%"
            )

        lines += [
            "-" * 60,
            f"{'加权平均':<15} {self.weighted_value:>12.2f} {self.weighted_upside*100:>11.2f}%",
            f"{'中位数':<15} {self.median_value:>12.2f}",
            f"{'估值区间':<15} {self.low_value:>8.2f} ~ {self.high_value:<8.2f}",
            "",
            "=" * 60,
        ]
        return "\n".join(lines)


class ValuationAnalyzer:
    """
    综合估值分析器

    整合 DCF、相对估值、DDM、剩余收益等多种方法，
    给出加权平均的内在价值估计和估值评级。

    使用方式：
        analyzer = ValuationAnalyzer(financial_data)
        report = analyzer.full_valuation(config=...)
        print(report.summary())
    """

    # 默认权重配置（可根据公司类型调整）
    DEFAULT_WEIGHTS = {
        "DCF_FCFF": 0.25,
        "DCF_FCFE": 0.15,
        "PE": 0.15,
        "PB": 0.10,
        "PEG": 0.10,
        "RIM": 0.15,
        "DDM": 0.10,
    }

    def __init__(self, data: FinancialData):
        self.data = data
        self.dcf = DCFModel(data)
        self.relative = RelativeValuation(data)
        self.ddm = DDMModel(data)
        self.rim = ResidualIncomeModel(data)

    # ---------- 全量估值 ----------

    def full_valuation(
        self,
        weights: Optional[Dict[str, float]] = None,
        dcf_params: Optional[Dict] = None,
        relative_params: Optional[Dict] = None,
        ddm_params: Optional[Dict] = None,
        rim_params: Optional[Dict] = None,
        enable_ddm: bool = True,
        enable_rim: bool = True,
    ) -> ValuationSummary:
        """
        执行完整的多方法估值并生成综合报告

        Args:
            weights: 各方法权重，不提供则用默认
            dcf_params: DCF 参数字典
            relative_params: 相对估值参数字典
            ddm_params: DDM 参数字典
            rim_params: 剩余收益参数字典
            enable_ddm: 是否启用 DDM（分红少的公司可关闭）
            enable_rim: 是否启用剩余收益模型

        Returns:
            ValuationSummary 综合估值报告
        """
        if weights is None:
            weights = dict(self.DEFAULT_WEIGHTS)

        dcf_params = dcf_params or {}
        relative_params = relative_params or {}
        ddm_params = ddm_params or {}
        rim_params = rim_params or {}

        method_values: Dict[str, float] = {}
        method_upsides: Dict[str, float] = {}
        used_weights: Dict[str, float] = {}

        # ---- DCF FCFF ----
        try:
            fcff_result = self.dcf.fcff_valuation(**dcf_params)
            method_values["DCF_FCFF"] = fcff_result.intrinsic_value_per_share
            method_upsides["DCF_FCFF"] = fcff_result.upside_downside(self.data.current_price)
            used_weights["DCF_FCFF"] = weights.get("DCF_FCFF", 0)
        except Exception:
            pass

        # ---- DCF FCFE ----
        try:
            fcfe_result = self.dcf.fcfe_valuation(**dcf_params)
            method_values["DCF_FCFE"] = fcfe_result.intrinsic_value_per_share
            method_upsides["DCF_FCFE"] = fcfe_result.upside_downside(self.data.current_price)
            used_weights["DCF_FCFE"] = weights.get("DCF_FCFE", 0)
        except Exception:
            pass

        # ---- PE ----
        try:
            pe_result = self.relative.pe_valuation(
                industry_pe=relative_params.get("industry_pe"),
                growth_adjusted=relative_params.get("growth_adjusted", False),
                expected_growth=relative_params.get("expected_growth"),
            )
            method_values["PE"] = pe_result.intrinsic_value_per_share
            method_upsides["PE"] = pe_result.upside_downside
            used_weights["PE"] = weights.get("PE", 0)
        except Exception:
            pass

        # ---- PB ----
        try:
            pb_result = self.relative.pb_valuation(
                industry_pb=relative_params.get("industry_pb"),
                roe_adjusted=relative_params.get("roe_adjusted", True),
            )
            method_values["PB"] = pb_result.intrinsic_value_per_share
            method_upsides["PB"] = pb_result.upside_downside
            used_weights["PB"] = weights.get("PB", 0)
        except Exception:
            pass

        # ---- PEG ----
        try:
            peg_result = self.relative.peg_valuation(
                expected_growth=relative_params.get("expected_growth"),
            )
            method_values["PEG"] = peg_result.intrinsic_value_per_share
            method_upsides["PEG"] = peg_result.upside_downside
            used_weights["PEG"] = weights.get("PEG", 0)
        except Exception:
            pass

        # ---- DDM ----
        if enable_ddm and self.data.dividend_per_share > 0:
            try:
                ddm_result = self.ddm.two_stage_ddm(**ddm_params)
                method_values["DDM"] = ddm_result.intrinsic_value_per_share
                method_upsides["DDM"] = ddm_result.upside_downside(self.data.current_price)
                used_weights["DDM"] = weights.get("DDM", 0)
            except Exception:
                pass

        # ---- 剩余收益 RIM ----
        if enable_rim and self.data.bvps > 0:
            try:
                rim_result = self.rim.valuation(**rim_params)
                method_values["RIM"] = rim_result.intrinsic_value_per_share
                method_upsides["RIM"] = rim_result.upside_downside(self.data.current_price)
                used_weights["RIM"] = weights.get("RIM", 0)
            except Exception:
                pass

        if not method_values:
            raise ValueError("所有估值方法均失败，请检查财务数据是否完整")

        # ---- 权重归一化 ----
        total_weight = sum(used_weights.values())
        if total_weight <= 0:
            n = len(method_values)
            norm_weights = {m: 1.0 / n for m in method_values}
        else:
            norm_weights = {m: w / total_weight for m, w in used_weights.items() if m in method_values}

        # ---- 加权平均 ----
        weighted_value = sum(
            method_values[m] * norm_weights.get(m, 0) for m in method_values
        )
        weighted_upside = (weighted_value - self.data.current_price) / self.data.current_price if self.data.current_price > 0 else 0

        # ---- 估值区间 ----
        values = sorted(method_values.values())
        low_value = values[0]
        high_value = values[-1]
        n = len(values)
        median_value = values[n // 2] if n % 2 == 1 else (values[n // 2 - 1] + values[n // 2]) / 2

        # ---- 评级 ----
        rating, confidence = self._calc_rating(weighted_upside, len(method_values), values)

        return ValuationSummary(
            company_name=self.data.name,
            ticker=self.data.ticker,
            current_price=self.data.current_price,
            method_values=method_values,
            method_upsides=method_upsides,
            weighted_value=weighted_value,
            weighted_upside=weighted_upside,
            weights=norm_weights,
            low_value=low_value,
            high_value=high_value,
            median_value=median_value,
            rating=rating,
            confidence=confidence,
        )

    # ---------- 评级逻辑 ----------

    def _calc_rating(
        self,
        weighted_upside: float,
        num_methods: int,
        values: List[float],
    ) -> Tuple[str, str]:
        """
        根据加权涨跌空间和估值离散度计算评级

        评级标准（相对内在价值的折价/溢价）：
          - 严重低估: upside >= 50%
          - 低估:     20% <= upside < 50%
          - 合理:     -15% <= upside < 20%
          - 高估:     -40% <= upside < -15%
          - 严重高估: upside < -40%

        可信度：
          - 方法数 >= 6 且离散度 < 50%: 高
          - 方法数 >= 4: 中
          - 其他: 低
        """
        # 评级
        if weighted_upside >= 0.50:
            rating = "严重低估"
        elif weighted_upside >= 0.20:
            rating = "低估"
        elif weighted_upside >= -0.15:
            rating = "合理"
        elif weighted_upside >= -0.40:
            rating = "高估"
        else:
            rating = "严重高估"

        # 可信度
        if num_methods >= 6:
            confidence = "高"
        elif num_methods >= 4:
            confidence = "中等"
        else:
            confidence = "低"

        # 离散度校验：各方法估值差异过大则降低可信度
        if len(values) >= 3:
            avg = sum(values) / len(values)
            spread = (max(values) - min(values)) / avg if avg > 0 else 0
            if spread > 1.0:  # 区间超过平均值的 100%
                if confidence == "高":
                    confidence = "中等"
                elif confidence == "中等":
                    confidence = "低"

        return rating, confidence

    # ---------- 敏感性分析 ----------

    def dcf_sensitivity_table(
        self,
        method: str = "FCFF",
        growth_range: Tuple[float, float, int] = (0.05, 0.20, 4),
        discount_range: Tuple[float, float, int] = (0.07, 0.13, 4),
        terminal_growth: float = 0.03,
        high_growth_years: int = 5,
    ) -> str:
        """
        生成 DCF 敏感性分析表格（文本格式）

        行：增长率
        列：折现率
        值：每股内在价值
        """
        result = self.dcf.sensitivity_analysis(
            method=method,
            growth_range=growth_range,
            wacc_range=discount_range,
            terminal_growth=terminal_growth,
            high_growth_years=high_growth_years,
        )

        data = result["growth_rates"]
        # 提取折现率列表
        first_growth = next(iter(data.keys()))
        discount_rates = sorted(data[first_growth].keys())
        growth_rates = sorted(data.keys())

        # 生成表格
        lines = [
            f"DCF {method} 敏感性分析（每股内在价值：元）",
            f"永续增长率: {terminal_growth*100:.1f}%，高速增长期: {high_growth_years} 年",
            "",
            f"{'增长率＼折现率':>12}  " + "  ".join(f"{d*100:>6.1f}%" for d in discount_rates),
            "-" * (14 + len(discount_rates) * 10),
        ]

        current_price = self.data.current_price
        for g in growth_rates:
            row = f"{g*100:>10.1f}%  "
            for d in discount_rates:
                val = data[g][d]
                # 标记低估/高估
                if current_price > 0:
                    upside = (val - current_price) / current_price
                    marker = "↑" if upside > 0.2 else "↓" if upside < -0.2 else "·"
                else:
                    marker = ""
                row += f"{val:>7.2f}{marker}"
            lines.append(row)

        lines += [
            "",
            "↑: 低估 (上涨空间>20%)   ·: 合理   ↓: 高估 (下跌空间>20%)",
        ]
        return "\n".join(lines)

    # ---------- 预设公司类型配置 ----------

    @staticmethod
    def get_weights_for_company_type(company_type: str) -> Dict[str, float]:
        """
        根据公司类型获取建议的权重配置

        可选类型：
          - "growth": 成长型公司（重 DCF、PEG）
          - "value": 价值型公司（重 PE、PB、DDM）
          - "mature": 成熟型公司（重 DDM、PE）
          - "cyclical": 周期型公司（重 PB、EV/EBITDA）
          - "high_tech": 高科技公司（重 DCF、PEG、RIM）
          - "financial": 金融/银行（重 PB、PE、RIM）
        """
        configs = {
            "growth": {
                "DCF_FCFF": 0.25,
                "DCF_FCFE": 0.20,
                "PE": 0.10,
                "PB": 0.05,
                "PEG": 0.25,
                "RIM": 0.10,
                "DDM": 0.05,
            },
            "value": {
                "DCF_FCFF": 0.15,
                "DCF_FCFE": 0.10,
                "PE": 0.20,
                "PB": 0.20,
                "PEG": 0.10,
                "RIM": 0.10,
                "DDM": 0.15,
            },
            "mature": {
                "DCF_FCFF": 0.15,
                "DCF_FCFE": 0.10,
                "PE": 0.20,
                "PB": 0.10,
                "PEG": 0.05,
                "RIM": 0.10,
                "DDM": 0.30,
            },
            "cyclical": {
                "DCF_FCFF": 0.20,
                "DCF_FCFE": 0.10,
                "PE": 0.10,
                "PB": 0.25,
                "PEG": 0.05,
                "RIM": 0.15,
                "DDM": 0.15,
            },
            "high_tech": {
                "DCF_FCFF": 0.25,
                "DCF_FCFE": 0.20,
                "PE": 0.10,
                "PB": 0.05,
                "PEG": 0.20,
                "RIM": 0.15,
                "DDM": 0.05,
            },
            "financial": {
                "DCF_FCFF": 0.05,
                "DCF_FCFE": 0.05,
                "PE": 0.20,
                "PB": 0.30,
                "PEG": 0.05,
                "RIM": 0.25,
                "DDM": 0.10,
            },
        }
        return configs.get(company_type, ValuationAnalyzer.DEFAULT_WEIGHTS)

    # ---------- 安全边际计算 ----------

    def margin_of_safety(
        self,
        intrinsic_value: float,
        safety_margin_ratio: float = 0.25,
    ) -> float:
        """
        计算安全边际买入价
        安全边际 = 内在价值 × (1 - 安全边际率)
        """
        return intrinsic_value * (1 - safety_margin_ratio)

    def value_zone_analysis(self, intrinsic_value: float) -> Dict[str, float]:
        """
        估值区间分析：给出不同安全边际下的买入/持有/卖出参考价
        """
        return {
            "极度低估区": intrinsic_value * 0.5,   # 5折
            "低估区": intrinsic_value * 0.7,        # 7折
            "合理区下限": intrinsic_value * 0.85,   # 85折
            "内在价值": intrinsic_value,
            "合理区上限": intrinsic_value * 1.15,   # 15%溢价
            "高估区": intrinsic_value * 1.3,        # 30%溢价
            "极度高估区": intrinsic_value * 1.5,    # 50%溢价
        }
