"""
Yahoo Finance (yfinance) 免费数据源客户端
==========================================

通过 yfinance 从雅虎财经获取 A 股数据。

特点：
  - 完全免费，无需 Token / 积分
  - 雅虎财经美国服务器，Streamlit Cloud 海外环境直接可用
  - A 股代码格式：上交所 .SS，深交所 .SZ
  - 合并报表（无"归母净利润/净资产"拆分），估值时按合并口径估算

Tushare 格式 ↔ Yahoo 格式转换：
  600519.SH → 600519.SS
  000333.SZ → 000333.SZ
"""

from __future__ import annotations

import time
import warnings
from typing import Dict, List, Optional

import pandas as pd

try:
    import yfinance as yf
except ImportError:
    yf = None


def _ts_to_yf(ts_code: str) -> str:
    """Tushare 格式 → yfinance 代码格式"""
    code, market = ts_code.split(".")
    market = market.upper()
    if market == "SH":
        return f"{code}.SS"
    elif market == "SZ":
        return f"{code}.SZ"
    return ts_code


class YFinanceClient:
    """
    YFinance 客户端

    接口与 AKShareClient / TushareClient 对齐，方便 builder 复用。
    """

    def __init__(self, enable_cache: bool = True):
        if yf is None:
            raise ImportError("需要安装 yfinance：pip install yfinance")
        self.enable_cache = enable_cache
        self._cache: Dict[str, object] = {}
        self.errors: Dict[str, str] = {}

    def _fail(self, key: str, e: Exception):
        self.errors[key] = f"{type(e).__name__}: {str(e)[:200]}"
        warnings.warn(f"[YFinance] {key} 失败: {e}")

    def _ticker(self, ts_code: str):
        cache_key = f"ticker_{ts_code}"
        if cache_key in self._cache:
            return self._cache[cache_key]
        tk = yf.Ticker(_ts_to_yf(ts_code))
        if self.enable_cache:
            self._cache[cache_key] = tk
        return tk

    # ---------- 基本信息 ----------
    def get_stock_basic(self, ts_code: str) -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            info = tk.info or {}
        except Exception as e:
            self._fail(f"info {ts_code}", e)
            info = {}

        if not info:
            return pd.DataFrame()

        name = str(info.get("longName") or info.get("shortName") or ts_code)
        industry = str(info.get("industry") or info.get("sector") or "")
        total_share = float(info.get("sharesOutstanding") or info.get("floatShares") or 0)
        float_share = float(info.get("floatShares") or total_share)
        total_mv = float(info.get("marketCap") or 0)  # 美元

        return pd.DataFrame([{
            "ts_code": ts_code,
            "name": name,
            "industry": industry,
            "list_date": "",
            "total_share": total_share,
            "float_share": float_share,
            "total_mv": total_mv,
        }])

    # ---------- 日线 ----------
    def get_daily(self, ts_code: str,
                  start: str = "20200101",
                  end: str = "20991231") -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            start_fmt = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
            end_fmt = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
            df = tk.history(start=start_fmt, end=end_fmt, auto_adjust=False)
        except Exception as e:
            self._fail(f"history {ts_code}", e)
            return pd.DataFrame()

        if df is None or df.empty:
            return pd.DataFrame()

        df = df.reset_index()
        df.rename(columns={
            "Date": "trade_date",
            "Open": "open",
            "High": "high",
            "Low": "low",
            "Close": "close",
            "Volume": "vol",
            "Dividends": "dividends",
            "Stock Splits": "split",
        }, inplace=True)
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y%m%d")
        return df[["trade_date", "open", "high", "low", "close", "vol"]].copy()

    def get_daily_basic(self, ts_code: str) -> pd.DataFrame:
        """日度指标（PE/PB/市值/收盘价）"""
        tk = self._ticker(ts_code)
        try:
            info = tk.info or {}
        except Exception as e:
            self._fail(f"info {ts_code}", e)
            info = {}

        try:
            hist = tk.history(period="5d", auto_adjust=False)
            close_price = float(hist["Close"].iloc[-1]) if hist is not None and not hist.empty else 0.0
        except Exception:
            close_price = 0.0

        market_cap = float(info.get("marketCap") or 0)
        shares = float(info.get("sharesOutstanding") or 0)
        pe = float(info.get("trailingPE") or info.get("forwardPE") or 0)
        pb = float(info.get("priceToBook") or 0)

        return pd.DataFrame([{
            "ts_code": ts_code,
            "trade_date": time.strftime("%Y%m%d"),
            "close": close_price,
            "total_mv": market_cap,
            "pe_ttm": pe,
            "pb": pb,
            "turnover_rate": 0.0,
            "volume": shares,
        }])

    # ---------- 利润表 ----------
    def get_income(self, ts_code: str) -> pd.DataFrame:
        """
        利润表（合并口径）。yfinance 返回 MultiIndex，科目 → 报告日期。
        标准科目（部分）：
            Total Revenue, Cost Of Revenue, Gross Profit,
            Operating Expense, Operating Income,
            Income Before Tax, Income Tax Expense,
            Net Income, Net Income Common Stockholders,
            Basic EPS, Diluted EPS, ...
        """
        tk = self._ticker(ts_code)
        try:
            df = tk.financials  # 年度
        except Exception as e:
            self._fail(f"financials {ts_code}", e)
            return pd.DataFrame()
        if df is None or df.empty:
            try:
                df = tk.get_financials()  # 备用
            except Exception as e:
                self._fail(f"financials2 {ts_code}", e)
                return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()

        # index 是科目名（英文），columns 是日期（Timestamp）
        out = pd.DataFrame()
        col_map = {
            "total_revenue": "Total Revenue",
            "total_cost": "Cost Of Revenue",
            "gross_profit": "Gross Profit",
            "sell_exp": "Selling General And Administration",
            "admin_exp": "Selling General And Administration",
            "operate_profit": "Operating Income",
            "total_profit": "Pretax Income",
            "net_profit": "Net Income",
            "n_income": "Net Income Common Stockholders",
        }
        out["end_date"] = [pd.Timestamp(c).strftime("%Y%m%d") for c in df.columns]
        for std, src in col_map.items():
            if src in df.index:
                out[std] = [float(v) if pd.notna(v) else 0.0 for v in df.loc[src].values]
            else:
                out[std] = 0.0
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    # ---------- 资产负债表 ----------
    def get_balance_sheet(self, ts_code: str) -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            df = tk.balance_sheet
        except Exception as e:
            self._fail(f"balance_sheet {ts_code}", e)
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()

        out = pd.DataFrame()
        col_map = {
            "money_cap": "Cash And Cash Equivalents",
            "total_cur_assets": "Total Current Assets",
            "total_assets": "Total Assets",
            "st_borrow": "Short Long Term Debt",
            "total_cur_liab": "Total Current Liabilities Net Minority Interest",
            "lt_borrow": "Long Term Debt",
            "total_liab": "Total Liabilities Net Minority Interest",
            "total_hldr_eqy_exc_min_int": "Stockholders Equity",
            "accounts_receiv": "Accounts Receivable",
            "inventories": "Inventory",
        }
        out["end_date"] = [pd.Timestamp(c).strftime("%Y%m%d") for c in df.columns]
        for std, src in col_map.items():
            if src in df.index:
                out[std] = [float(v) if pd.notna(v) else 0.0 for v in df.loc[src].values]
            else:
                out[std] = 0.0
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    # ---------- 现金流 ----------
    def get_cashflow(self, ts_code: str) -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            df = tk.cashflow
        except Exception as e:
            self._fail(f"cashflow {ts_code}", e)
            return pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame()

        out = pd.DataFrame()
        col_map = {
            "n_cashflow_act": "Operating Cash Flow",
            "n_cashflow_inv_act": "Investing Cash Flow",
            "stot_cashflows_frn_act_2": "Financing Cash Flow",
            "net_increase_cash_equ": "Change In Cash",
            "end_cash_cash_equ": "Ending Cash Position",
        }
        out["end_date"] = [pd.Timestamp(c).strftime("%Y%m%d") for c in df.columns]
        for std, src in col_map.items():
            if src in df.index:
                out[std] = [float(v) if pd.notna(v) else 0.0 for v in df.loc[src].values]
            else:
                out[std] = 0.0
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    # ---------- 财务指标（直接从 info 取） ----------
    def get_fina_indicator(self, ts_code: str) -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            info = tk.info or {}
        except Exception as e:
            self._fail(f"info {ts_code}", e)
            info = {}

        roe = float(info.get("returnOnEquity") or 0)
        gross_margin = float(info.get("grossMargins") or 0)
        if roe > 1:
            roe /= 100
        if gross_margin > 1:
            gross_margin /= 100

        return pd.DataFrame([{
            "ts_code": ts_code,
            "end_date": time.strftime("%Y%m%d"),
            "roe": roe,
            "grossprofit_margin": gross_margin,
        }])

    # ---------- 分红 ----------
    def get_dividend(self, ts_code: str) -> pd.DataFrame:
        tk = self._ticker(ts_code)
        try:
            div = tk.dividends  # Series, index=Date, value=amount
        except Exception as e:
            self._fail(f"dividends {ts_code}", e)
            return pd.DataFrame()

        if div is None or div.empty:
            return pd.DataFrame()

        # yfinance 返回的是**每股分红金额（美元）**，直接就是 per share，不用除以 10
        df = div.reset_index()
        df.columns = ["ann_date", "cash_div"]
        df["cash_div"] = pd.to_numeric(df["cash_div"], errors="coerce").fillna(0)
        df = df[df["cash_div"] > 0].sort_values("ann_date", ascending=False)
        return df.head(5).reset_index(drop=True)
