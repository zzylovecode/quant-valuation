"""
财报数据模型
============

封装上市公司财务报表核心指标，供各类估值模型调用。
支持从单期数据或多年历史数据构建。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class FinancialData:
    """
    上市公司财务数据容器

    所有金额单位统一为：亿元（人民币）
    每股指标单位：元 / 股

    Attributes:
        ticker: 股票代码
        name: 公司名称
        total_shares: 总股本（亿股）
        current_price: 当前股价（元）

        # 利润表核心指标（最新年度）
        revenue: 营业收入
        net_profit: 归母净利润
        operating_profit: 营业利润
        ebit: 息税前利润
        ebitda: 息税折旧摊销前利润
        eps: 每股收益

        # 资产负债表核心指标
        total_assets: 总资产
        total_equity: 归母所有者权益
        net_debt: 净负债 = 有息负债 - 货币资金
        cash: 货币资金
        interest_bearing_debt: 有息负债
        bvps: 每股净资产

        # 现金流量表核心指标
        operating_cash_flow: 经营活动现金流净额
        investing_cash_flow: 投资活动现金流净额
        financing_cash_flow: 筹资活动现金流净额
        capex: 资本支出
        free_cash_flow: 自由现金流（如已计算）

        # 分红数据
        dividend_per_share: 每股股利
        dividend_payout_ratio: 股利支付率

        # 历史数据（可选）：用于增长率计算
        historical_net_profit: 过去N年净利润列表（从远到近）
        historical_revenue: 过去N年营收列表

        # 行业可比数据（可选）
        industry_pe: 行业平均市盈率
        industry_pb: 行业平均市净率
    """

    ticker: str = ""
    name: str = ""
    total_shares: float = 0.0
    current_price: float = 0.0

    # 利润表
    revenue: float = 0.0
    net_profit: float = 0.0
    operating_profit: float = 0.0
    ebit: float = 0.0
    ebitda: float = 0.0
    eps: float = 0.0

    # 资产负债表
    total_assets: float = 0.0
    total_equity: float = 0.0
    net_debt: float = 0.0
    cash: float = 0.0
    interest_bearing_debt: float = 0.0
    bvps: float = 0.0

    # 现金流量表
    operating_cash_flow: float = 0.0
    investing_cash_flow: float = 0.0
    financing_cash_flow: float = 0.0
    capex: float = 0.0
    free_cash_flow: float = 0.0

    # 分红
    dividend_per_share: float = 0.0
    dividend_payout_ratio: float = 0.0

    # 历史数据
    historical_net_profit: List[float] = field(default_factory=list)
    historical_revenue: List[float] = field(default_factory=list)

    # 行业可比
    industry_pe: float = 0.0
    industry_pb: float = 0.0

    # ---------- 衍生指标计算 ----------

    def calc_pe(self) -> float:
        """市盈率 = 股价 / EPS"""
        if self.eps <= 0:
            return float("inf")
        return self.current_price / self.eps

    def calc_pb(self) -> float:
        """市净率 = 股价 / 每股净资产"""
        if self.bvps <= 0:
            return float("inf")
        return self.current_price / self.bvps

    def calc_ps(self) -> float:
        """市销率 = 市值 / 营收"""
        if self.revenue <= 0:
            return float("inf")
        market_cap = self.current_price * self.total_shares
        return market_cap / self.revenue

    def calc_roe(self) -> float:
        """净资产收益率 ROE = 净利润 / 净资产"""
        if self.total_equity <= 0:
            return 0.0
        return self.net_profit / self.total_equity

    def calc_roa(self) -> float:
        """资产收益率 ROA = 净利润 / 总资产"""
        if self.total_assets <= 0:
            return 0.0
        return self.net_profit / self.total_assets

    def calc_net_margin(self) -> float:
        """净利润率 = 净利润 / 营收"""
        if self.revenue <= 0:
            return 0.0
        return self.net_profit / self.revenue

    def calc_free_cash_flow(self, force: bool = False) -> float:
        """
        自由现金流 FCF = 经营现金流 - 资本支出
        若已设置 free_cash_flow 则直接返回，除非 force=True
        """
        if self.free_cash_flow > 0 and not force:
            return self.free_cash_flow
        self.free_cash_flow = self.operating_cash_flow - self.capex
        return self.free_cash_flow

    def calc_profit_growth_rate(self, years: int = 3) -> float:
        """
        计算净利润复合增长率 CAGR
        years: 使用最近几年的数据计算
        """
        if len(self.historical_net_profit) < years + 1:
            return 0.0
        # 取最后 years+1 个数据点
        data = self.historical_net_profit[-(years + 1) :]
        start, end = data[0], data[-1]
        if start <= 0 or end <= 0:
            return 0.0
        return (end / start) ** (1.0 / years) - 1.0

    def calc_revenue_growth_rate(self, years: int = 3) -> float:
        """营收复合增长率 CAGR"""
        if len(self.historical_revenue) < years + 1:
            return 0.0
        data = self.historical_revenue[-(years + 1) :]
        start, end = data[0], data[-1]
        if start <= 0 or end <= 0:
            return 0.0
        return (end / start) ** (1.0 / years) - 1.0

    def calc_net_debt(self, force: bool = False) -> float:
        """净负债 = 有息负债 - 货币资金"""
        if self.net_debt != 0 and not force:
            return self.net_debt
        self.net_debt = self.interest_bearing_debt - self.cash
        return self.net_debt

    def calc_market_cap(self) -> float:
        """总市值 = 股价 × 总股本"""
        return self.current_price * self.total_shares

    def calc_enterprise_value(self) -> float:
        """企业价值 EV = 市值 + 净负债"""
        return self.calc_market_cap() + self.calc_net_debt()

    # ---------- 便捷构造方法 ----------

    @classmethod
    def from_dict(cls, data: Dict) -> "FinancialData":
        """从字典构造，忽略未知字段"""
        known_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in known_fields}
        return cls(**filtered)

    def summary(self) -> str:
        """输出关键指标摘要"""
        lines = [
            f"=== {self.name} ({self.ticker}) ===",
            f"当前股价: {self.current_price:.2f} 元",
            f"总市值: {self.calc_market_cap():.2f} 亿元",
            f"总股本: {self.total_shares:.2f} 亿股",
            "",
            "--- 估值指标 ---",
            f"PE (TTM): {self.calc_pe():.2f}",
            f"PB: {self.calc_pb():.2f}",
            f"PS: {self.calc_ps():.2f}",
            "",
            "--- 盈利能力 ---",
            f"ROE: {self.calc_roe()*100:.2f}%",
            f"ROA: {self.calc_roa()*100:.2f}%",
            f"净利率: {self.calc_net_margin()*100:.2f}%",
            "",
            "--- 规模指标 ---",
            f"营收: {self.revenue:.2f} 亿元",
            f"净利润: {self.net_profit:.2f} 亿元",
            f"净资产: {self.total_equity:.2f} 亿元",
        ]
        return "\n".join(lines)
