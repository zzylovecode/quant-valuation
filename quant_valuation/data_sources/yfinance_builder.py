"""
Yahoo Finance 数据构建器
========================

与 AKShareDataBuilder / TushareDataBuilder 同风格，
从 YFinanceClient 取数，自动构建 FinancialData。
"""

from __future__ import annotations

import warnings
from typing import Optional

import pandas as pd

from .yfinance_client import YFinanceClient
from ..financial_data import FinancialData


class YFinanceDataBuilder:
    """
    YFinance → FinancialData 构建器

    特点：
      - 合并报表口径（无"归母"拆分），直接用合并净利润 / 股东权益
      - 币种：yfinance 自动转换，A股 info.currency == "CNY"
      - 美元计价的字段（marketCap 等）按 info.currency 判断是否需要换算
    """

    def __init__(self, client: Optional[YFinanceClient] = None):
        self.client = client or YFinanceClient()

    def build(
        self,
        ts_code: str,
        years: int = 5,
        include_industry: bool = False,
    ) -> FinancialData:
        # 1. 基本信息
        basic_df = self.client.get_stock_basic(ts_code)
        if basic_df.empty:
            raise ValueError(f"无法获取股票基本信息: {ts_code}")

        basic = basic_df.iloc[0]
        name = str(basic.get("name", ts_code))
        industry = str(basic.get("industry", ""))
        total_share = float(basic.get("total_share", 0) or 0)
        float_share = float(basic.get("float_share", total_share) or 0)
        market_cap_raw = float(basic.get("total_mv", 0) or 0)

        # 2. 利润表
        income_df = self.client.get_income(ts_code)
        if income_df.empty:
            raise ValueError(f"无法获取利润表: {ts_code}")

        annual_income = income_df.head(years).sort_values("end_date")
        # yfinance 只返回年报，无需筛选 1231

        # 3. 资产负债表
        balance_df = self.client.get_balance_sheet(ts_code)
        annual_balance = balance_df.head(years).sort_values("end_date") if not balance_df.empty else pd.DataFrame()

        # 4. 现金流量表
        cashflow_df = self.client.get_cashflow(ts_code)
        annual_cashflow = cashflow_df.head(years).sort_values("end_date") if not cashflow_df.empty else pd.DataFrame()

        # 5. 日行情指标
        daily_df = self.client.get_daily_basic(ts_code)
        current_price = 0.0
        pe_ratio = 0.0
        pb_ratio = 0.0
        if not daily_df.empty:
            latest = daily_df.iloc[0]
            current_price = float(latest.get("close", 0) or 0)
            pe_ratio = float(latest.get("pe_ttm", 0) or 0)
            pb_ratio = float(latest.get("pb", 0) or 0)

        if current_price <= 0:
            daily_hist = self.client.get_daily(ts_code)
            if not daily_hist.empty:
                current_price = float(daily_hist.iloc[-1]["close"])

        # 6. 财务历史（合并口径）
        fiscal_years = []
        revenue_history = []
        net_profit_history = []

        for _, row in annual_income.iterrows():
            year_str = row["end_date"][:4]
            fiscal_years.append(year_str)
            revenue_history.append(float(row.get("total_revenue", 0) or 0))
            net_profit_history.append(
                float(row.get("n_income", 0) or row.get("net_profit", 0) or 0)
            )

        total_assets_history = []
        equity_history = []
        ocf_history = []
        if not annual_balance.empty:
            for _, row in annual_balance.iterrows():
                total_assets_history.append(float(row.get("total_assets", 0) or 0))
                equity_history.append(float(
                    row.get("total_hldr_eqy_exc_min_int", 0) or 0
                ))
        if not annual_cashflow.empty:
            for _, row in annual_cashflow.iterrows():
                ocf_history.append(float(row.get("n_cashflow_act", 0) or 0))

        n_years = len(fiscal_years)
        total_assets_history = total_assets_history[:n_years] or [0] * n_years
        equity_history = equity_history[:n_years] or [0] * n_years
        ocf_history = ocf_history[:n_years] or [0] * n_years

        # 7. 最新一期年报
        if not annual_income.empty:
            latest_income = annual_income.iloc[-1]
            revenue = float(latest_income.get("total_revenue", 0) or 0)
            net_profit = float(
                latest_income.get("n_income", 0)
                or latest_income.get("net_profit", 0)
                or 0
            )
            operate_profit = float(latest_income.get("operate_profit", 0) or 0)
            total_profit = float(latest_income.get("total_profit", 0) or 0)
        else:
            revenue = net_profit = operate_profit = total_profit = 0

        if not annual_balance.empty:
            latest_bs = annual_balance.iloc[-1]
            total_assets = float(latest_bs.get("total_assets", 0) or 0)
            total_liab = float(latest_bs.get("total_liab", 0) or 0)
            total_equity = float(
                latest_bs.get("total_hldr_eqy_exc_min_int", 0) or 0
            )
            st_borrow = float(latest_bs.get("st_borrow", 0) or 0)
            lt_borrow = float(latest_bs.get("lt_borrow", 0) or 0)
            cash = float(latest_bs.get("money_cap", 0) or 0)
        else:
            total_assets = total_liab = total_equity = 0
            st_borrow = lt_borrow = cash = 0

        if not annual_cashflow.empty:
            latest_cf = annual_cashflow.iloc[-1]
            ocf = float(latest_cf.get("n_cashflow_act", 0) or 0)
            icf = float(latest_cf.get("n_cashflow_inv_act", 0) or 0)
            fcf = float(latest_cf.get("stot_cashflows_frn_act_2", 0) or 0)
        else:
            ocf = icf = fcf = 0

        # 8. yfinance 单位：A股返回元（info.currency == "CNY"），
        # 但不同字段历史上可能略有差异。FinancialData 统一用 **亿元**。
        # yfinance 财报（financials / balance_sheet / cashflow）单位是美元，
        # info 里 marketCap 也是美元。我们需要用 info.currency 判断。
        currency = "CNY"
        try:
            info = self.client._ticker(ts_code).info or {}
            currency = str(info.get("currency", "CNY") or "CNY")
        except Exception:
            currency = "CNY"

        YI = 1e8  # 一亿
        USD_TO_CNY = 7.2  # 估算汇率，用于美元计价字段换算

        def _conv(val: float) -> float:
            """统一转成人民币元"""
            if currency.upper() in ("CNY", "RMB", "CNH"):
                return val
            return val * USD_TO_CNY

        revenue = _conv(revenue)
        net_profit = _conv(net_profit)
        operate_profit = _conv(operate_profit)
        total_profit = _conv(total_profit)
        total_assets = _conv(total_assets)
        total_liab = _conv(total_liab)
        total_equity = _conv(total_equity)
        st_borrow = _conv(st_borrow)
        lt_borrow = _conv(lt_borrow)
        cash = _conv(cash)
        ocf = _conv(ocf)
        icf = _conv(icf)
        fcf = _conv(fcf)

        revenue_history = [_conv(x) for x in revenue_history]
        net_profit_history = [_conv(x) for x in net_profit_history]
        total_assets_history = [_conv(x) for x in total_assets_history]
        equity_history = [_conv(x) for x in equity_history]
        ocf_history = [_conv(x) for x in ocf_history]

        # 9. 财务指标
        fina_df = self.client.get_fina_indicator(ts_code)
        roe = 0.0
        gross_margin = 0.0
        if not fina_df.empty:
            latest_fina = fina_df.iloc[0]
            roe = float(latest_fina.get("roe", 0) or 0)
            gross_margin = float(latest_fina.get("grossprofit_margin", 0) or 0)

        if roe <= 0 and net_profit > 0 and total_equity > 0:
            roe = net_profit / total_equity

        # 10. EPS / BVPS
        total_shares_yi = total_share / YI
        eps = (net_profit / YI) / total_shares_yi if total_shares_yi > 0 else 0.0
        bvps = (total_equity / YI) / total_shares_yi if total_shares_yi > 0 else 0.0

        interest_bearing_debt = st_borrow + lt_borrow
        net_debt = interest_bearing_debt - cash
        ebit = operate_profit
        ebitda = ebit

        # 11. 分红（yfinance 已返回每股金额）
        dividend_per_share = 0.0
        dividend_payout_ratio = 0.0
        div_df = self.client.get_dividend(ts_code)
        if not div_df.empty and "cash_div" in div_df.columns:
            divs = pd.to_numeric(div_df["cash_div"], errors="coerce").dropna()
            if len(divs) > 0:
                dividend_per_share = float(divs.iloc[0])
                if eps > 0:
                    dividend_payout_ratio = dividend_per_share / eps

        # 12. 自由现金流（简化 = 经营现金流）
        free_cash_flow = ocf

        # 13. 构建 FinancialData（单位统一：亿元）
        data = FinancialData(
            ticker=ts_code,
            name=name,
            total_shares=round(total_shares_yi, 4),
            current_price=round(current_price, 2),

            revenue=round(revenue / YI, 4),
            net_profit=round(net_profit / YI, 4),
            operating_profit=round(operate_profit / YI, 4),
            ebit=round(ebit / YI, 4),
            ebitda=round(ebitda / YI, 4),
            eps=round(eps, 4),

            total_assets=round(total_assets / YI, 4),
            total_equity=round(total_equity / YI, 4),
            net_debt=round(net_debt / YI, 4),
            cash=round(cash / YI, 4),
            interest_bearing_debt=round(interest_bearing_debt / YI, 4),
            bvps=round(bvps, 4),

            operating_cash_flow=round(ocf / YI, 4),
            investing_cash_flow=round(icf / YI, 4),
            financing_cash_flow=round(fcf / YI, 4),
            capex=0.0,
            free_cash_flow=round(free_cash_flow / YI, 4),

            dividend_per_share=round(dividend_per_share, 4),
            dividend_payout_ratio=round(dividend_payout_ratio, 4),

            historical_net_profit=[round(x / YI, 4) for x in net_profit_history],
            historical_revenue=[round(x / YI, 4) for x in revenue_history],

            industry_pe=0.0,
            industry_pb=0.0,
        )

        # 附加属性
        data.industry = industry
        data.pe_ratio = pe_ratio
        data.pb_ratio = pb_ratio
        data.market_cap = round(
            _conv(market_cap_raw) / YI, 4
        )
        data.gross_margin = gross_margin
        data.roe = roe

        return data
