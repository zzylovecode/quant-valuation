"""
Tushare 数据构建器
==================

从 Tushare 获取原始数据，自动构建 FinancialData 对象。

核心类：TushareDataBuilder

功能：
  - 单只股票一键构建 FinancialData
  - 自动获取最新年报数据
  - 历史多年财务数据自动聚合
  - 行业平均估值指标计算
  - 股本、分红、行情数据自动整合
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .tushare_client import TushareClient
from ..financial_data import FinancialData


class TushareDataBuilder:
    """
    Tushare 数据 → FinancialData 构建器

    使用方式：
        builder = TushareDataBuilder(token="你的token")
        data = builder.build("600519.SH")
        # 或者：
        data = builder.build("600519", years=5, include_industry=True)
    """

    def __init__(self, client: Optional[TushareClient] = None, token: Optional[str] = None):
        """
        Args:
            client: 已有的 TushareClient 实例
            token: Tushare Token（client 为 None 时使用）
        """
        if client is not None:
            self.client = client
        else:
            self.client = TushareClient(token=token)

    # ---------- 一键构建 ----------

    def build(
        self,
        ts_code: str,
        years: int = 5,
        include_industry: bool = True,
        industry_level: str = "L2",
    ) -> FinancialData:
        """
        一键构建 FinancialData 对象

        Args:
            ts_code: 股票代码
            years: 获取历史财务数据年数
            include_industry: 是否包含行业可比数据
            industry_level: 行业分类级别 L1/L2/L3

        Returns:
            FinancialData 对象
        """
        ts_code = self.client.normalize_ts_code(ts_code)
        print(f"正在获取 {ts_code} 的数据...")

        # 1. 基本信息
        print("  [1/6] 股票基本信息...", end=" ")
        basic_info = self._get_basic_info(ts_code)
        print("✓")

        # 2. 最新行情与估值指标
        print("  [2/6] 行情与估值指标...", end=" ")
        daily_info = self._get_latest_daily_basic(ts_code)
        print("✓")

        # 3. 利润表（多年）
        print("  [3/6] 利润表数据...", end=" ")
        income_data = self._get_annual_income(ts_code, years)
        print("✓")

        # 4. 资产负债表（最新）
        print("  [4/6] 资产负债表...", end=" ")
        balance_data = self._get_latest_balance(ts_code)
        print("✓")

        # 5. 现金流量表（最新）
        print("  [5/6] 现金流量表...", end=" ")
        cashflow_data = self._get_latest_cashflow(ts_code)
        print("✓")

        # 6. 分红数据
        print("  [6/6] 分红数据...", end=" ")
        dividend_info = self._get_dividend_info(ts_code)
        print("✓")

        # 行业可比数据
        industry_pe = 0.0
        industry_pb = 0.0
        if include_industry:
            print("  行业可比数据...", end=" ")
            try:
                industry_pe, industry_pb = self._get_industry_avg(ts_code, level=industry_level)
                print(f"✓ (PE={industry_pe:.1f}, PB={industry_pb:.1f})")
            except Exception as e:
                print(f"✗ ({e})")

        # 组装 FinancialData
        fd = self._assemble(
            ts_code=ts_code,
            basic_info=basic_info,
            daily_info=daily_info,
            income_data=income_data,
            balance_data=balance_data,
            cashflow_data=cashflow_data,
            dividend_info=dividend_info,
            industry_pe=industry_pe,
            industry_pb=industry_pb,
            years=years,
        )

        return fd

    # ---------- 各数据获取方法 ----------

    def _get_basic_info(self, ts_code: str) -> Dict:
        """获取股票基本信息"""
        df = self.client.get_stock_basic(ts_code)
        if df.empty:
            raise ValueError(f"未找到股票 {ts_code} 的基本信息")

        row = df.iloc[0]
        return {
            "ts_code": row.get("ts_code", ts_code),
            "name": row.get("name", ""),
            "total_share": self._safe_float(row.get("total_share", 0)) / 10000,  # 万股 → 亿股
            "float_share": self._safe_float(row.get("float_share", 0)) / 10000,
            "industry": row.get("industry", ""),
            "list_date": row.get("list_date", ""),
        }

    def _get_latest_daily_basic(self, ts_code: str) -> Dict:
        """获取最新每日基本指标"""
        try:
            row = self.client.get_latest_daily_basic(ts_code)
            return {
                "close": self._safe_float(row.get("close", 0)),
                "pe": self._safe_float(row.get("pe", 0)),
                "pe_ttm": self._safe_float(row.get("pe_ttm", 0)),
                "pb": self._safe_float(row.get("pb", 0)),
                "ps": self._safe_float(row.get("ps", 0)),
                "ps_ttm": self._safe_float(row.get("ps_ttm", 0)),
                "total_mv": self._safe_float(row.get("total_mv", 0)) / 10000,  # 万元 → 亿元
                "circ_mv": self._safe_float(row.get("circ_mv", 0)) / 10000,
                "dv_ratio": self._safe_float(row.get("dv_ratio", 0)),
                "dv_ttm": self._safe_float(row.get("dv_ttm", 0)),
                "trade_date": row.get("trade_date", ""),
            }
        except Exception:
            return {}

    def _get_annual_income(self, ts_code: str, years: int) -> List[Dict]:
        """获取最近 N 年的年度利润表（从旧到新）"""
        df = self.client.get_income(ts_code)
        if df.empty:
            raise ValueError(f"未找到 {ts_code} 的利润表数据")

        # 筛选年报（end_date 以 1231 结尾）
        annual = df[df["end_date"].str.endswith("1231")].copy()
        # 按日期排序
        annual = annual.sort_values("end_date")
        # 取最近 N 年
        annual = annual.tail(years)

        result = []
        for _, row in annual.iterrows():
            result.append({
                "end_date": row.get("end_date", ""),
                "revenue": self._safe_float(row.get("revenue", 0)) / 10000,  # 千元 → 亿元
                "operate_profit": self._safe_float(row.get("operate_profit", 0)) / 10000,
                "total_profit": self._safe_float(row.get("total_profit", 0)) / 10000,
                "n_income": self._safe_float(row.get("n_income", 0)) / 10000,
                "n_income_attr_p": self._safe_float(row.get("n_income_attr_p", 0)) / 10000,
                "ebit": self._safe_float(row.get("ebit", 0)) / 10000,
                "ebitda": self._safe_float(row.get("ebitda", 0)) / 10000,
                "basic_eps": self._safe_float(row.get("basic_eps", 0)),
            })

        return result

    def _get_latest_balance(self, ts_code: str) -> Dict:
        """获取最新年报的资产负债表"""
        df = self.client.get_balancesheet(ts_code)
        if df.empty:
            raise ValueError(f"未找到 {ts_code} 的资产负债表数据")

        # 筛选年报
        annual = df[df["end_date"].str.endswith("1231")].copy()
        annual = annual.sort_values("end_date")
        row = annual.iloc[-1]

        return {
            "end_date": row.get("end_date", ""),
            "total_assets": self._safe_float(row.get("total_assets", 0)) / 10000,
            "total_liab": self._safe_float(row.get("total_liab", 0)) / 10000,
            "total_hldr_eqy_exc_min_int": self._safe_float(
                row.get("total_hldr_eqy_exc_min_int", 0)
            ) / 10000,
            "total_hldr_eqy_inc_min_int": self._safe_float(
                row.get("total_hldr_eqy_inc_min_int", 0)
            ) / 10000,
            "money_cap": self._safe_float(row.get("money_cap", 0)) / 10000,
            "trad_asset": self._safe_float(row.get("trad_asset", 0)) / 10000,
            # 有息负债 = 短期借款 + 长期借款 + 应付债券 + 一年内到期的非流动负债
            "st_borrow": self._safe_float(row.get("st_borrow", 0)) / 10000,
            "lt_borrow": self._safe_float(row.get("lt_borrow", 0)) / 10000,
            "bonds_payable": self._safe_float(row.get("bonds_payable", 0)) / 10000,
            "non_cur_liab_due_1y": self._safe_float(row.get("non_cur_liab_due_1y", 0)) / 10000,
            # 固定资产等
            "fix_assets": self._safe_float(row.get("fix_assets", 0)) / 10000,
            "intang_assets": self._safe_float(row.get("intang_assets", 0)) / 10000,
            "goodwill": self._safe_float(row.get("goodwill", 0)) / 10000,
        }

    def _get_latest_cashflow(self, ts_code: str) -> Dict:
        """获取最新年报的现金流量表"""
        df = self.client.get_cashflow(ts_code)
        if df.empty:
            raise ValueError(f"未找到 {ts_code} 的现金流量表数据")

        annual = df[df["end_date"].str.endswith("1231")].copy()
        annual = annual.sort_values("end_date")
        row = annual.iloc[-1]

        return {
            "end_date": row.get("end_date", ""),
            "n_cashflow_act": self._safe_float(row.get("n_cashflow_act", 0)) / 10000,
            "n_cashflow_inv": self._safe_float(row.get("n_cashflow_inv", 0)) / 10000,
            "n_cashflow_fra": self._safe_float(row.get("n_cashflow_fra", 0)) / 10000,
            # 资本支出：购建固定资产、无形资产和其他长期资产支付的现金
            "c_pay_acq_const_fiolta": self._safe_float(
                row.get("c_pay_acq_const_fiolta", 0)
            ) / 10000,
            # 折旧摊销
            "fa_depr": self._safe_float(row.get("fa_depr", 0)) / 10000,
            "intang_asset_amort": self._safe_float(row.get("intang_asset_amort", 0)) / 10000,
        }

    def _get_dividend_info(self, ts_code: str) -> Dict:
        """获取最新分红信息"""
        try:
            df = self.client.get_dividend(ts_code)
            if df.empty:
                return {"dividend_per_share": 0.0, "payout_ratio": 0.0}

            # 只看已实施的现金分红
            cash_div = df[
                (df["div_proc"] == "实施")
                & (df["stk_div"].isna() | (df["stk_div"] == 0))
            ].copy()

            if cash_div.empty:
                return {"dividend_per_share": 0.0, "payout_ratio": 0.0}

            # 按除权除息日排序，取最近一次
            cash_div = cash_div.sort_values("ex_date", na_position="first")
            latest = cash_div.iloc[-1]

            cash_amount = self._safe_float(latest.get("cash_div", 0))  # 元（税前）
            # cash_div 单位是 元/10股 → 转换为 元/股
            if cash_amount > 1:  # 可能单位是元/10股
                dividend_ps = cash_amount / 10
            else:
                dividend_ps = cash_amount

            return {
                "dividend_per_share": round(dividend_ps, 4),
                "payout_ratio": 0.0,  # 后面结合 EPS 计算
            }
        except Exception:
            return {"dividend_per_share": 0.0, "payout_ratio": 0.0}

    def _get_industry_avg(
        self,
        ts_code: str,
        level: str = "L2",
        top_n: int = 30,
    ) -> Tuple[float, float]:
        """
        估算行业平均 PE 和 PB

        思路：
          1. 获取同行业成分股列表
          2. 取市值最大的 top_n 只
          3. 计算 PE 和 PB 的中位数（剔除负值和极端值）

        注：需要较高的 Tushare 积分才能获取行业成分股数据，
            如果失败则返回 0
        """
        try:
            # 尝试获取申万行业分类
            industry_df = self.client.get_industry(ts_code, level=level)
            if industry_df.empty:
                return 0.0, 0.0

            industry_code = industry_df.iloc[0].get("index_code", "")
            if not industry_code:
                return 0.0, 0.0

            # 获取行业成分股
            members = self.client.get_industry_member(industry_code)
            if members.empty:
                return 0.0, 0.0

            # 取前 N 只（按市值排序需要额外接口，这里简化处理）
            member_codes = members["con_code"].head(top_n).tolist()

            # 获取各成分股的 PE、PB
            pe_list = []
            pb_list = []
            for code in member_codes[:20]:  # 限制数量避免请求过多
                try:
                    daily = self.client.get_latest_daily_basic(code)
                    pe = self._safe_float(daily.get("pe_ttm", 0))
                    pb = self._safe_float(daily.get("pb", 0))
                    if pe > 0 and pe < 200:  # 过滤异常值
                        pe_list.append(pe)
                    if pb > 0 and pb < 50:
                        pb_list.append(pb)
                except Exception:
                    continue

            if not pe_list or not pb_list:
                return 0.0, 0.0

            # 取中位数更稳健
            pe_list.sort()
            pb_list.sort()
            avg_pe = pe_list[len(pe_list) // 2]
            avg_pb = pb_list[len(pb_list) // 2]

            return avg_pe, avg_pb

        except Exception as e:
            warnings.warn(f"获取行业平均数据失败: {e}")
            return 0.0, 0.0

    # ---------- 组装 FinancialData ----------

    def _assemble(
        self,
        ts_code: str,
        basic_info: Dict,
        daily_info: Dict,
        income_data: List[Dict],
        balance_data: Dict,
        cashflow_data: Dict,
        dividend_info: Dict,
        industry_pe: float,
        industry_pb: float,
        years: int,
    ) -> FinancialData:
        """将所有数据组装成 FinancialData 对象"""

        # 最新一期利润表
        latest_income = income_data[-1] if income_data else {}

        # 有息负债估算
        interest_bearing_debt = (
            balance_data.get("st_borrow", 0)
            + balance_data.get("lt_borrow", 0)
            + balance_data.get("bonds_payable", 0)
            + balance_data.get("non_cur_liab_due_1y", 0)
        )

        # 货币资金（含交易性金融资产近似）
        cash = balance_data.get("money_cap", 0) + balance_data.get("trad_asset", 0) * 0.5

        # 净负债
        net_debt = interest_bearing_debt - cash

        # 总股本（亿股）
        total_shares = basic_info.get("total_share", 0)
        if total_shares <= 0:
            # 从市值反推
            total_mv = daily_info.get("total_mv", 0)
            close = daily_info.get("close", 0)
            if close > 0:
                total_shares = total_mv / close

        # 每股收益
        eps = latest_income.get("basic_eps", 0)
        if eps <= 0 and total_shares > 0:
            eps = latest_income.get("n_income_attr_p", 0) / total_shares

        # 每股净资产
        total_equity = balance_data.get("total_hldr_eqy_exc_min_int", 0)
        bvps = total_equity / total_shares if total_shares > 0 else 0

        # 自由现金流
        ocf = cashflow_data.get("n_cashflow_act", 0)
        capex = cashflow_data.get("c_pay_acq_const_fiolta", 0)
        fcf = ocf - capex

        # 分红率
        dividend_ps = dividend_info.get("dividend_per_share", 0)
        payout_ratio = dividend_ps / eps if eps > 0 else 0.0

        # 历史净利润（亿元）
        historical_net_profit = [
            item.get("n_income_attr_p", item.get("n_income", 0))
            for item in income_data
        ]
        # 历史营收
        historical_revenue = [item.get("revenue", 0) for item in income_data]

        # 当前股价
        current_price = daily_info.get("close", 0)

        # 构造 FinancialData
        fd = FinancialData(
            ticker=ts_code,
            name=basic_info.get("name", ""),
            total_shares=round(total_shares, 4),
            current_price=round(current_price, 2),

            # 利润表
            revenue=round(latest_income.get("revenue", 0), 4),
            net_profit=round(latest_income.get("n_income_attr_p", 0), 4),
            operating_profit=round(latest_income.get("operate_profit", 0), 4),
            ebit=round(latest_income.get("ebit", 0), 4),
            ebitda=round(latest_income.get("ebitda", 0), 4),
            eps=round(eps, 4),

            # 资产负债表
            total_assets=round(balance_data.get("total_assets", 0), 4),
            total_equity=round(total_equity, 4),
            net_debt=round(net_debt, 4),
            cash=round(cash, 4),
            interest_bearing_debt=round(interest_bearing_debt, 4),
            bvps=round(bvps, 4),

            # 现金流量表
            operating_cash_flow=round(ocf, 4),
            investing_cash_flow=round(cashflow_data.get("n_cashflow_inv", 0), 4),
            financing_cash_flow=round(cashflow_data.get("n_cashflow_fra", 0), 4),
            capex=round(capex, 4),
            free_cash_flow=round(fcf, 4),

            # 分红
            dividend_per_share=round(dividend_ps, 4),
            dividend_payout_ratio=round(payout_ratio, 4),

            # 历史数据
            historical_net_profit=historical_net_profit,
            historical_revenue=historical_revenue,

            # 行业可比
            industry_pe=round(industry_pe, 2),
            industry_pb=round(industry_pb, 2),
        )

        return fd

    # ---------- 工具方法 ----------

    @staticmethod
    def _safe_float(value) -> float:
        """安全转换为 float"""
        if value is None:
            return 0.0
        try:
            if pd.isna(value):
                return 0.0
            return float(value)
        except (ValueError, TypeError):
            return 0.0
