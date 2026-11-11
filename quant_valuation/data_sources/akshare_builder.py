"""
AKShare 数据构建器
==================

从 AKShare 获取免费公开数据，自动构建 FinancialData 对象。

核心类：AKShareDataBuilder

功能：
  - 单只股票一键构建 FinancialData
  - 自动获取最新年报数据
  - 历史多年财务数据自动聚合
  - 股本、行情数据自动整合
  - 完全免费，无需 Token
"""

from __future__ import annotations

import warnings
from typing import Dict, List, Optional

import pandas as pd

from .akshare_client import AKShareClient
from ..financial_data import FinancialData


class AKShareDataBuilder:
    """
    AKShare 数据 → FinancialData 构建器

    使用方式：
        builder = AKShareDataBuilder()
        data = builder.build("600519.SH")
    """

    def __init__(self, client: Optional[AKShareClient] = None):
        """
        Args:
            client: 已有的 AKShareClient 实例
        """
        self.client = client or AKShareClient()

    # ---------- 一键构建 ----------

    def build(
        self,
        ts_code: str,
        years: int = 5,
        include_industry: bool = False,
    ) -> FinancialData:
        """
        一键构建 FinancialData 对象

        Args:
            ts_code: 股票代码（Tushare 格式，如 600519.SH）
            years: 使用多少年的历史财务数据
            include_industry: 是否包含行业平均数据（AKShare 获取行业数据较麻烦，默认 False）

        Returns:
            FinancialData 对象
        """
        # 1. 基本信息
        basic_df = self.client.get_stock_basic(ts_code)
        if basic_df.empty:
            raise ValueError(f"无法获取股票基本信息: {ts_code}")

        basic = basic_df.iloc[0]
        name = str(basic.get("name", ts_code))
        industry = str(basic.get("industry", ""))

        # 2. 利润表
        income_df = self.client.get_income(ts_code)
        if income_df.empty:
            raise ValueError(f"无法获取利润表: {ts_code}")

        # 筛选年报数据（12月31日的报告）
        annual_income = income_df[income_df["end_date"].str.endswith("1231")].copy()
        annual_income = annual_income.head(years).sort_values("end_date")

        if len(annual_income) < 2:
            # 年报不够，用所有报告期数据凑
            annual_income = income_df.head(years).sort_values("end_date")

        # 3. 资产负债表
        balance_df = self.client.get_balance_sheet(ts_code)
        annual_balance = balance_df[balance_df["end_date"].str.endswith("1231")].copy() if not balance_df.empty else pd.DataFrame()
        annual_balance = annual_balance.head(years).sort_values("end_date") if not annual_balance.empty else pd.DataFrame()

        # 4. 现金流量表
        cashflow_df = self.client.get_cashflow(ts_code)
        annual_cashflow = cashflow_df[cashflow_df["end_date"].str.endswith("1231")].copy() if not cashflow_df.empty else pd.DataFrame()
        annual_cashflow = annual_cashflow.head(years).sort_values("end_date") if not annual_cashflow.empty else pd.DataFrame()

        # 5. 最新日行情指标（PE/PB/市值/股价）
        daily_df = self.client.get_daily_basic(ts_code)
        current_price = 0.0
        pe_ratio = 0.0
        pb_ratio = 0.0
        market_cap = 0.0

        if not daily_df.empty:
            latest = daily_df.iloc[0]
            pe_ratio = float(latest.get("pe_ttm", 0) or 0)
            pb_ratio = float(latest.get("pb", 0) or 0)
            market_cap = float(latest.get("total_mv", 0) or 0)
            # 市值单位：get_daily_basic 返回的是万元，转为元
            if market_cap > 0:
                market_cap = market_cap * 10000

            # 优先用 close 字段（从日线获取的真实收盘价）
            if latest.get("close", 0):
                current_price = float(latest["close"])
            elif basic.get("total_share", 0) > 0 and market_cap > 0:
                # 通过市值和总股本估算股价
                total_share = float(basic["total_share"])
                if total_share > 0:
                    current_price = market_cap / total_share

        # 如果没拿到价格，用最新日线收盘价
        if current_price <= 0:
            daily_hist = self.client.get_daily(ts_code)
            if not daily_hist.empty:
                current_price = float(daily_hist.iloc[-1]["close"])

        # 6. 构建财务历史数据
        fiscal_years = []
        revenue_history = []
        net_profit_history = []
        total_assets_history = []
        equity_history = []
        ocf_history = []

        for i, row in annual_income.iterrows():
            year_str = row["end_date"][:4]
            fiscal_years.append(year_str)
            revenue_history.append(float(row.get("revenue", 0)))
            net_profit_history.append(float(row.get("n_income", 0) or row.get("net_profit", 0)))

        if not annual_balance.empty:
            for i, row in annual_balance.iterrows():
                total_assets_history.append(float(row.get("total_assets", 0)))
                equity_history.append(float(row.get("total_hldr_eqy_exc_min_int", 0) or row.get("total_hldr_eqy_inc_min_int", 0)))

        if not annual_cashflow.empty:
            for i, row in annual_cashflow.iterrows():
                ocf_history.append(float(row.get("n_cashflow_act", 0)))

        # 确保各列表长度一致
        n_years = len(fiscal_years)
        total_assets_history = total_assets_history[:n_years] or [0] * n_years
        equity_history = equity_history[:n_years] or [0] * n_years
        ocf_history = ocf_history[:n_years] or [0] * n_years

        # 7. 计算当前年度财务数据（取最新一期年报）
        if not annual_income.empty:
            latest_income = annual_income.iloc[-1]
            revenue = float(latest_income.get("revenue", 0))
            net_profit = float(latest_income.get("n_income", 0) or latest_income.get("net_profit", 0))
            total_cost = float(latest_income.get("total_cost", 0))
            operate_cost = float(latest_income.get("operate_cost", 0))
            sell_exp = float(latest_income.get("sell_exp", 0))
            admin_exp = float(latest_income.get("admin_exp", 0))
            fin_exp = float(latest_income.get("fin_exp", 0))
            rd_exp = float(latest_income.get("rd_exp", 0))
            operate_profit = float(latest_income.get("operate_profit", 0))
            total_profit = float(latest_income.get("total_profit", 0))
        else:
            revenue = net_profit = total_cost = operate_cost = 0
            sell_exp = admin_exp = fin_exp = rd_exp = 0
            operate_profit = total_profit = 0

        if not annual_balance.empty:
            latest_bs = annual_balance.iloc[-1]
            total_assets = float(latest_bs.get("total_assets", 0))
            total_liab = float(latest_bs.get("total_liab", 0))
            total_equity = float(latest_bs.get("total_hldr_eqy_exc_min_int", 0) or latest_bs.get("total_hldr_eqy_inc_min_int", 0))
            current_assets = float(latest_bs.get("total_cur_assets", 0))
            current_liab = float(latest_bs.get("total_cur_liab", 0))
            cash = float(latest_bs.get("money_cap", 0))
            inventory = float(latest_bs.get("inventories", 0))
            receivables = float(latest_bs.get("accounts_receiv", 0))
            st_borrow = float(latest_bs.get("st_borrow", 0))
            lt_borrow = float(latest_bs.get("lt_borrow", 0))
        else:
            total_assets = total_liab = total_equity = 0
            current_assets = current_liab = cash = inventory = 0
            receivables = st_borrow = lt_borrow = 0

        if not annual_cashflow.empty:
            latest_cf = annual_cashflow.iloc[-1]
            ocf = float(latest_cf.get("n_cashflow_act", 0))
            icf = float(latest_cf.get("n_cashflow_inv_act", 0))
            fcf = float(latest_cf.get("stot_cashflows_frn_act_2", 0))
        else:
            ocf = icf = fcf = 0

        # 单位转换：AKShare 返回的是元，FinancialData 用的是亿元
        YI = 1e8  # 一亿

        # 8. 总股本（AKShare 返回的是股，转为亿股）
        total_shares_yi = float(basic.get("total_share", 0) or 0) / YI

        # 9. 财务指标（ROE等）
        roe = 0.0
        gross_margin = 0.0

        fina_df = self.client.get_fina_indicator(ts_code)
        if not fina_df.empty:
            latest_fina = fina_df.iloc[0]
            roe = float(latest_fina.get("roe", 0) or 0)
            gross_margin = float(latest_fina.get("grossprofit_margin", 0) or 0)

        # 如果 ROE 为 0，手动计算
        if roe <= 0 and net_profit > 0 and total_equity > 0:
            roe = net_profit / total_equity

        # 10. 计算 EPS（每股收益）
        eps = 0.0
        if total_shares_yi > 0:
            eps = (net_profit / YI) / total_shares_yi

        # 11. 每股净资产 BVPS
        bvps = 0.0
        if total_shares_yi > 0:
            bvps = (total_equity / YI) / total_shares_yi

        # 12. 有息负债
        interest_bearing_debt = st_borrow + lt_borrow

        # 13. 净负债
        net_debt = interest_bearing_debt - cash

        # 14. EBIT（息税前利润，粗略估算 = 营业利润 + 财务费用）
        ebit = operate_profit + abs(fin_exp) if fin_exp < 0 else operate_profit - fin_exp
        ebitda = ebit  # 简化，折旧摊销数据没拿到

        # 15. 分红数据
        dividend_per_share = 0.0
        dividend_payout_ratio = 0.0
        div_df = self.client.get_dividend(ts_code)
        if not div_df.empty and "cash_div" in div_df.columns:
            divs = pd.to_numeric(div_df["cash_div"], errors="coerce").dropna()
            if len(divs) > 0:
                # 每 10 股派息 → 每股派息
                dividend_per_share = float(divs.iloc[0]) / 10
            if eps > 0:
                dividend_payout_ratio = dividend_per_share / eps

        # 16. 自由现金流（简化 = 经营现金流 - 资本支出，这里先设为经营现金流）
        free_cash_flow = ocf
        capex = 0.0  # 资本支出数据后面再补

        # 17. 历史数据转换（元 → 亿元）
        historical_revenue = [x / YI for x in revenue_history]
        historical_net_profit = [x / YI for x in net_profit_history]

        # 18. 构建 FinancialData
        data = FinancialData(
            ticker=ts_code,
            name=name,
            total_shares=round(total_shares_yi, 4),
            current_price=round(current_price, 2),

            # 利润表（亿元）
            revenue=round(revenue / YI, 4),
            net_profit=round(net_profit / YI, 4),
            operating_profit=round(operate_profit / YI, 4),
            ebit=round(ebit / YI, 4),
            ebitda=round(ebitda / YI, 4),
            eps=round(eps, 4),

            # 资产负债表（亿元）
            total_assets=round(total_assets / YI, 4),
            total_equity=round(total_equity / YI, 4),
            net_debt=round(net_debt / YI, 4),
            cash=round(cash / YI, 4),
            interest_bearing_debt=round(interest_bearing_debt / YI, 4),
            bvps=round(bvps, 4),

            # 现金流量表（亿元）
            operating_cash_flow=round(ocf / YI, 4),
            investing_cash_flow=round(icf / YI, 4),
            financing_cash_flow=round(fcf / YI, 4),
            capex=round(capex / YI, 4),
            free_cash_flow=round(free_cash_flow / YI, 4),

            # 分红
            dividend_per_share=round(dividend_per_share, 4),
            dividend_payout_ratio=round(dividend_payout_ratio, 4),

            # 历史数据
            historical_net_profit=historical_net_profit,
            historical_revenue=historical_revenue,

            # 行业可比（AKShare 行业数据获取较复杂，暂时留空）
            industry_pe=0.0,
            industry_pb=0.0,
        )

        # 附加属性（不影响估值，但方便界面展示）
        data.industry = industry
        data.pe_ratio = pe_ratio
        data.pb_ratio = pb_ratio
        data.market_cap = market_cap / YI  # 亿元
        data.gross_margin = gross_margin
        data.roe = roe

        return data
