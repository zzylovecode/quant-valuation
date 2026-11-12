"""
AKShare 免费数据源客户端
=======================

封装 AKShare 接口，提供与 TushareClient 类似的接口，便于切换。

AKShare 特点：
  - 完全免费，无需 Token
  - 数据来源于东方财富、新浪财经等公开网站
  - 接口可能随网站改版而变化
  - 速度相对较慢，建议加缓存

使用方式：
    from quant_valuation.data_sources import AKShareClient
    client = AKShareClient()
    df = client.get_income("600519.SH")
"""

from __future__ import annotations

import time
import warnings
from typing import Dict, List, Optional

import pandas as pd


def _get_ak():
    """延迟导入 akshare（避免 import quant_valuation 时就触发网络请求，
    导致 Streamlit Cloud 等境外环境启动超时）"""
    try:
        import akshare as ak  # noqa: PLC0415
        return ak
    except ImportError as e:
        raise ImportError("需要安装 akshare 库：pip install akshare") from e


# 代码格式转换：Tushare格式(600519.SH) <-> AKShare格式(sh600519 / 600519)
def _ts_to_ak(ts_code: str) -> str:
    """Tushare 格式转 AKShare 前缀格式"""
    code, market = ts_code.split(".")
    if market.upper() == "SH":
        return f"sh{code}"
    elif market.upper() == "SZ":
        return f"sz{code}"
    return ts_code


def _ts_to_code(ts_code: str) -> str:
    """Tushare 格式转纯数字代码"""
    return ts_code.split(".")[0]


def _ak_to_ts(ak_code: str) -> str:
    """AKShare 格式转 Tushare 格式"""
    ak_code = ak_code.lower()
    if ak_code.startswith("sh"):
        return f"{ak_code[2:]}.SH"
    elif ak_code.startswith("sz"):
        return f"{ak_code[2:]}.SZ"
    return ak_code


class AKShareClient:
    """
    AKShare 客户端封装

    完全免费，无需 Token。接口设计尽量与 TushareClient 保持一致，
    方便在两个数据源之间切换。
    """

    def __init__(
        self,
        timeout: int = 30,
        enable_cache: bool = True,
    ):
        """
        初始化 AKShare 客户端

        Args:
            timeout: 请求超时时间（秒）
            enable_cache: 是否启用内存缓存
        """
        self._ak = _get_ak()  # 延迟导入 akshare，避免 import 包时就触发网络访问

        self.timeout = timeout
        self.enable_cache = enable_cache
        self._cache: Dict[str, pd.DataFrame] = {}
        # 记录各接口的失败原因，供界面诊断展示
        self.errors: Dict[str, str] = {}

    def _fail(self, key: str, e: Exception):
        """记录接口失败原因（不再静默吞掉异常）"""
        self.errors[key] = f"{type(e).__name__}: {str(e)[:200]}"
        warnings.warn(f"{key} 失败: {e}")

    def diagnose(self, ts_code: str = "600519.SH") -> pd.DataFrame:
        """
        逐个测试数据接口，返回状态表。用于排查云端环境下的数据源问题。

        Args:
            ts_code: 测试用股票代码

        Returns:
            DataFrame，列为 接口 / 状态 / 详情
        """
        rows = []
        try:
            import akshare

            rows.append({"接口": "akshare 版本", "状态": "OK", "详情": akshare.__version__})
        except Exception as e:  # pragma: no cover
            rows.append({"接口": "akshare 导入", "状态": "FAIL", "详情": str(e)[:150]})
            return pd.DataFrame(rows)

        code = _ts_to_code(ts_code)
        ak_code = _ts_to_ak(ts_code)

        checks = [
            ("stock_profile_cninfo(公司概况)",
             lambda: self._ak.stock_profile_cninfo(symbol=code)),
            ("stock_zh_a_gbjg_em(股本结构)",
             lambda: self._ak.stock_zh_a_gbjg_em(symbol=code)),
            ("stock_zh_a_daily(新浪日线)",
             lambda: self._ak.stock_zh_a_daily(symbol=ak_code, adjust="qfq")),
            ("stock_profit_sheet_by_report_em(东财利润表)",
             lambda: self._ak.stock_profit_sheet_by_report_em(symbol=ak_code.upper())),
            ("stock_balance_sheet_by_report_em(东财资产负债表)",
             lambda: self._ak.stock_balance_sheet_by_report_em(symbol=ak_code.upper())),
            ("stock_cash_flow_sheet_by_report_em(东财现金流)",
             lambda: self._ak.stock_cash_flow_sheet_by_report_em(symbol=ak_code.upper())),
            ("stock_financial_report_sina(新浪利润表)",
             lambda: self._ak.stock_financial_report_sina(stock=ak_code, symbol="利润表")),
            ("stock_financial_analysis_indicator(财务指标)",
             lambda: self._ak.stock_financial_analysis_indicator(symbol=code)),
            ("stock_individual_info_em(东财push2，易限流)",
             lambda: self._ak.stock_individual_info_em(symbol=code)),
        ]

        for name, fn in checks:
            try:
                df = fn()
                rows.append({"接口": name, "状态": "OK", "详情": f"返回 {len(df)} 行"})
            except Exception as e:
                detail = f"{type(e).__name__}: {str(e)[:150]}"
                if not hasattr(akshare, name.split("(")[0]):
                    detail = "当前 akshare 版本不存在该接口"
                rows.append({"接口": name, "状态": "FAIL", "详情": detail})

        return pd.DataFrame(rows)

    def _get_cache(self, key: str) -> Optional[pd.DataFrame]:
        if not self.enable_cache:
            return None
        return self._cache.get(key)

    # ---------- 东方财富报表通道（境外服务器访问更稳定） ----------

    def _em_income(self, ts_code: str) -> pd.DataFrame:
        """东方财富利润表，返回与新浪通道一致的列名"""
        df = self._ak.stock_profit_sheet_by_report_em(symbol=_ts_to_ak(ts_code).upper())
        if df is None or df.empty or "REPORT_DATE" not in df.columns:
            return pd.DataFrame()

        out = pd.DataFrame()
        out["end_date"] = df["REPORT_DATE"].astype(str).str[:10].str.replace("-", "")
        rev_src = "OPERATE_INCOME" if "OPERATE_INCOME" in df.columns else "TOTAL_OPERATE_INCOME"
        field_map = [
            ("revenue", rev_src),
            ("total_cost", "TOTAL_OPERATE_COST"),
            ("operate_cost", "OPERATE_COST"),
            ("sell_exp", "SALE_EXPENSE"),
            ("admin_exp", "MANAGE_EXPENSE"),
            ("fin_exp", "FINANCE_EXPENSE"),
            ("rd_exp", "RESEARCH_EXPENSE"),
            ("operate_profit", "OPERATE_PROFIT"),
            ("total_profit", "TOTAL_PROFIT"),
            ("net_profit", "NETPROFIT"),
            ("n_income", "PARENT_NETPROFIT"),
            ("basic_eps", "BASIC_EPS"),
        ]
        for std, src in field_map:
            out[std] = (pd.to_numeric(df[src], errors="coerce").fillna(0)
                        if src in df.columns else 0.0)
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    def _em_balance(self, ts_code: str) -> pd.DataFrame:
        """东方财富资产负债表，返回与新浪通道一致的列名"""
        df = self._ak.stock_balance_sheet_by_report_em(symbol=_ts_to_ak(ts_code).upper())
        if df is None or df.empty or "REPORT_DATE" not in df.columns:
            return pd.DataFrame()

        out = pd.DataFrame()
        out["end_date"] = df["REPORT_DATE"].astype(str).str[:10].str.replace("-", "")
        field_map = [
            ("money_cap", "MONETARYFUNDS"),
            ("notes_receiv", "NOTE_RECE"),
            ("accounts_receiv", "ACCOUNTS_RECE"),
            ("inventories", "INVENTORY"),
            ("total_cur_assets", "TOTAL_CURRENT_ASSETS"),
            ("fix_assets", "FIXED_ASSET"),
            ("total_assets", "TOTAL_ASSETS"),
            ("st_borrow", "SHORT_LOAN"),
            ("notes_payable", "NOTE_PAYABLE"),
            ("acct_payable", "ACCOUNTS_PAYABLE"),
            ("total_cur_liab", "TOTAL_CURRENT_LIAB"),
            ("lt_borrow", "LONG_LOAN"),
            ("total_liab", "TOTAL_LIABILITIES"),
            ("total_hldr_eqy_exc_min_int", "TOTAL_PARENT_EQUITY"),
        ]
        for std, src in field_map:
            out[std] = (pd.to_numeric(df[src], errors="coerce").fillna(0)
                        if src in df.columns else 0.0)
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    def _em_cashflow(self, ts_code: str) -> pd.DataFrame:
        """东方财富现金流量表，返回与新浪通道一致的列名"""
        df = self._ak.stock_cash_flow_sheet_by_report_em(symbol=_ts_to_ak(ts_code).upper())
        if df is None or df.empty or "REPORT_DATE" not in df.columns:
            return pd.DataFrame()

        out = pd.DataFrame()
        out["end_date"] = df["REPORT_DATE"].astype(str).str[:10].str.replace("-", "")
        field_map = [
            ("n_cashflow_act", "NETCASH_OPERATE"),
            ("n_cashflow_inv_act", "NETCASH_INVEST"),
            ("stot_cashflows_frn_act_2", "NETCASH_FINANCE"),
            ("net_increase_cash_equ", "CCE_ADD"),
            ("end_cash_cash_equ", "END_CCE"),
        ]
        for std, src in field_map:
            out[std] = (pd.to_numeric(df[src], errors="coerce").fillna(0)
                        if src in df.columns else 0.0)
        out["ts_code"] = ts_code
        return out.sort_values("end_date", ascending=False).reset_index(drop=True)

    def _set_cache(self, key: str, df: pd.DataFrame):
        if self.enable_cache:
            self._cache[key] = df

    # ============================================================
    # 股票基本信息
    # ============================================================

    def get_stock_basic(self, ts_code: str) -> pd.DataFrame:
        """
        获取股票基本信息

        Args:
            ts_code: 股票代码（Tushare 格式，如 600519.SH）

        Returns:
            DataFrame，包含 ts_code, name, industry 等
        """
        cache_key = f"basic_{ts_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        code = _ts_to_code(ts_code)
        name, industry, list_date = "", "", ""
        total_share = 0.0
        float_share = 0.0

        # 1) 巨潮公司概况：名称 / 行业（不依赖东财 push2，稳定）
        try:
            prof = self._ak.stock_profile_cninfo(symbol=code)
            if prof is not None and not prof.empty:
                row = prof.iloc[0]
                name = str(row.get("A股简称", "") or "")
                industry = str(row.get("所属行业", "") or "")
                list_date = str(row.get("上市日期", "") or "")
        except Exception as e:
            self._fail(f"公司概况 {ts_code}", e)

        # 2) 东财 F10 股本结构：总股本 / 流通股本（非 push2 接口）
        try:
            gbjg = self._ak.stock_zh_a_gbjg_em(symbol=code)
            if gbjg is not None and not gbjg.empty:
                gbjg = gbjg.sort_values("变更日期", ascending=False)
                total_share = float(gbjg.iloc[0].get("总股本", 0) or 0)
                float_share = float(gbjg.iloc[0].get("已上市流通A股", 0) or 0)
        except Exception as e:
            self._fail(f"股本结构 {ts_code}", e)

        # 3) 兜底：东财个股信息（走 push2，可能触发限流，仅在前两者失败时使用）
        if not name or total_share <= 0:
            try:
                info = self._ak.stock_individual_info_em(symbol=code)
                d = dict(zip(info["item"], info["value"]))
                name = name or str(d.get("股票简称", "") or "")
                industry = industry or str(d.get("行业", "") or "")
                total_share = total_share or float(d.get("总股本", 0) or 0)
                float_share = float_share or float(d.get("流通股", 0) or 0)
                list_date = list_date or str(d.get("上市时间", "") or "")
            except Exception as e:
                self._fail(f"个股信息 {ts_code}", e)

        if not name and total_share <= 0:
            return pd.DataFrame()

        result = pd.DataFrame([{
            "ts_code": ts_code,
            "name": name,
            "industry": industry,
            "list_date": list_date,
            "total_share": total_share,
            "float_share": float_share,
            "total_mv": 0.0,  # 市值在 get_daily_basic 中按 股本×收盘价 计算
        }])
        self._set_cache(cache_key, result)
        return result

    # ============================================================
    # 利润表
    # ============================================================

    def get_income(self, ts_code: str) -> pd.DataFrame:
        """
        获取利润表数据

        Args:
            ts_code: 股票代码（Tushare 格式）

        Returns:
            DataFrame，按报告期倒序
        """
        cache_key = f"income_{ts_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        ak_code = _ts_to_ak(ts_code)
        try:
            # 优先新浪（单次请求约 1s），失败再回退东方财富（分批请求，较慢）
            df = pd.DataFrame()
            try:
                df = self._ak.stock_financial_report_sina(stock=ak_code, symbol="利润表")
            except Exception as e:
                self._fail(f"新浪利润表 {ts_code}", e)
            if df.empty:
                try:
                    df = self._em_income(ts_code)
                except Exception as e:
                    self._fail(f"东财利润表 {ts_code}", e)
                    df = pd.DataFrame()
            if df.empty:
                return pd.DataFrame()

            # 字段映射
            rename_map = {
                "报告日": "end_date",
                "营业收入": "revenue",
                "营业总成本": "total_cost",
                "营业成本": "operate_cost",
                "销售费用": "sell_exp",
                "管理费用": "admin_exp",
                "财务费用": "fin_exp",
                "研发费用": "rd_exp",
                "营业利润": "operate_profit",
                "利润总额": "total_profit",
                "净利润": "net_profit",
                "归属于母公司所有者的净利润": "n_income",
                "基本每股收益": "basic_eps",
                "营业税金及附加": "biz_tax_surchg",
                "资产减值损失": "asset_impair_loss",
                "投资收益": "invest_income",
            }
            df = df.rename(columns=rename_map)

            # 只保留我们需要的列
            keep_cols = [c for c in rename_map.values() if c in df.columns]
            df = df[keep_cols].copy()

            # 数值列转换
            for col in df.columns:
                if col != "end_date":
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            df["ts_code"] = ts_code
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values("end_date", ascending=False).reset_index(drop=True)

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取利润表失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 资产负债表
    # ============================================================

    def get_balance_sheet(self, ts_code: str) -> pd.DataFrame:
        """
        获取资产负债表数据
        """
        cache_key = f"balance_{ts_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        ak_code = _ts_to_ak(ts_code)
        try:
            # 优先新浪，失败再回退东方财富
            df = pd.DataFrame()
            try:
                df = self._ak.stock_financial_report_sina(stock=ak_code, symbol="资产负债表")
            except Exception as e:
                self._fail(f"新浪资产负债表 {ts_code}", e)
            if df.empty:
                try:
                    df = self._em_balance(ts_code)
                except Exception as e:
                    self._fail(f"东财资产负债表 {ts_code}", e)
                    df = pd.DataFrame()
            if df.empty:
                return pd.DataFrame()

            rename_map = {
                "报告日": "end_date",
                "货币资金": "money_cap",
                "应收票据": "notes_receiv",
                "应收账款": "accounts_receiv",
                "存货": "inventories",
                "流动资产合计": "total_cur_assets",
                "固定资产": "fix_assets",
                "资产总计": "total_assets",
                "短期借款": "st_borrow",
                "应付票据": "notes_payable",
                "应付账款": "acct_payable",
                "流动负债合计": "total_cur_liab",
                "长期借款": "lt_borrow",
                "负债合计": "total_liab",
                "实收资本（或股本）": "capital_stk",
                "资本公积": "capital_rese",
                "盈余公积": "surplus_rese",
                "未分配利润": "undistributed_profit",
                "股东权益合计": "total_hldr_eqy_inc_min_int",
                "归属于母公司股东权益合计": "total_hldr_eqy_exc_min_int",
            }
            df = df.rename(columns=rename_map)

            keep_cols = [c for c in rename_map.values() if c in df.columns]
            df = df[keep_cols].copy()

            for col in df.columns:
                if col != "end_date":
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            df["ts_code"] = ts_code
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values("end_date", ascending=False).reset_index(drop=True)

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取资产负债表失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 现金流量表
    # ============================================================

    def get_cashflow(self, ts_code: str) -> pd.DataFrame:
        """
        获取现金流量表数据
        """
        cache_key = f"cashflow_{ts_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        ak_code = _ts_to_ak(ts_code)
        try:
            # 优先新浪，失败再回退东方财富
            df = pd.DataFrame()
            try:
                df = self._ak.stock_financial_report_sina(stock=ak_code, symbol="现金流量表")
            except Exception as e:
                self._fail(f"新浪现金流量表 {ts_code}", e)
            if df.empty:
                try:
                    df = self._em_cashflow(ts_code)
                except Exception as e:
                    self._fail(f"东财现金流量表 {ts_code}", e)
                    df = pd.DataFrame()
            if df.empty:
                return pd.DataFrame()

            rename_map = {
                "报告日": "end_date",
                "经营活动产生的现金流量净额": "n_cashflow_act",
                "投资活动产生的现金流量净额": "n_cashflow_inv_act",
                "筹资活动产生的现金流量净额": "stot_cashflows_frn_act_2",
                "现金及现金等价物净增加额": "net_increase_cash_equ",
                "期初现金及现金等价物余额": "beg_cash_cash_equ",
                "期末现金及现金等价物余额": "end_cash_cash_equ",
                "净利润": "net_profit",
            }
            df = df.rename(columns=rename_map)

            keep_cols = [c for c in rename_map.values() if c in df.columns]
            df = df[keep_cols].copy()

            for col in df.columns:
                if col != "end_date":
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            df["ts_code"] = ts_code
            df["end_date"] = df["end_date"].astype(str)
            df = df.sort_values("end_date", ascending=False).reset_index(drop=True)

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取现金流量表失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 每日指标（PE/PB/市值等）
    # ============================================================

    def get_daily_basic(self, ts_code: str, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取每日指标（PE/PB/市值等）

        注：AKShare 没有直接的 daily_basic 接口，
        这里通过基本信息 + 财务数据组合计算得到。

        Args:
            ts_code: 股票代码
            trade_date: 交易日期（YYYYMMDD），None 表示最新
        """
        cache_key = f"daily_basic_{ts_code}_{trade_date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        code = _ts_to_code(ts_code)
        try:
            # 总市值 = 总股本 × 最新收盘价（避免调用 push2 的个股信息接口）
            basic_df = self.get_stock_basic(ts_code)
            total_share = 0.0
            if not basic_df.empty:
                total_share = float(basic_df.iloc[0].get("total_share", 0) or 0)

            # 从日线获取最新收盘价
            daily_df = self.get_daily(ts_code)
            if daily_df.empty:
                return pd.DataFrame()

            latest = daily_df.iloc[-1]
            close_price = float(latest.get("close", 0))
            trade_date_str = str(latest.get("trade_date", ""))
            total_mv = total_share * close_price
            # 单位：元 → 万元（与 Tushare 一致）
            total_mv_wan = total_mv / 10000

            # 从利润表获取最新年报净利润，用于计算 PE
            income_df = self.get_income(ts_code)
            pe_ttm = 0.0
            if not income_df.empty:
                # 取最近年报的归母净利润
                annual = income_df[income_df["end_date"].str.endswith("1231")]
                if not annual.empty:
                    net_profit = float(annual.iloc[0].get("n_income", 0) or 0)
                    if net_profit > 0:
                        pe_ttm = total_mv / net_profit

            # 从资产负债表获取净资产，用于计算 PB
            balance_df = self.get_balance_sheet(ts_code)
            pb = 0.0
            if not balance_df.empty:
                annual_bs = balance_df[balance_df["end_date"].str.endswith("1231")]
                if not annual_bs.empty:
                    equity = float(annual_bs.iloc[0].get("total_hldr_eqy_exc_min_int", 0)
                                   or annual_bs.iloc[0].get("total_hldr_eqy_inc_min_int", 0) or 0)
                    if equity > 0:
                        pb = total_mv / equity

            result = pd.DataFrame([{
                "ts_code": ts_code,
                "trade_date": trade_date_str,
                "close": close_price,
                "pe_ttm": round(pe_ttm, 2),
                "pb": round(pb, 2),
                "total_mv": total_mv_wan,  # 万元
                "circ_mv": total_mv_wan,   # 简化，用总市值代替
                "turnover_rate": 0.0,
                "dv_ratio": 0.0,
            }])

            self._set_cache(cache_key, result)
            return result
        except Exception as e:
            self._fail(f"获取每日指标失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 日线行情
    # ============================================================

    def get_daily(self, ts_code: str, start_date: str = "", end_date: str = "") -> pd.DataFrame:
        """
        获取日线行情数据

        Args:
            ts_code: 股票代码
            start_date: 开始日期（YYYYMMDD）
            end_date: 结束日期（YYYYMMDD）
        """
        cache_key = f"daily_{ts_code}_{start_date}_{end_date}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        code = _ts_to_code(ts_code)
        try:
            # 如果没有指定日期，默认取最近 3 年
            if not start_date:
                from datetime import datetime
                end_year = datetime.now().year
                start_date = f"{end_year - 3}0101"
            if not end_date:
                from datetime import datetime
                end_date = datetime.now().strftime("%Y%m%d")

            start = start_date
            end = end_date

            # 优先新浪日线（不经过东财 push2，不会触发行情限流），失败再回退东财 / 腾讯
            df = pd.DataFrame()
            try:
                raw = self._ak.stock_zh_a_daily(symbol=_ts_to_ak(ts_code), adjust="qfq")
                if raw is not None and not raw.empty:
                    df = raw.rename(columns={"date": "trade_date", "volume": "vol"})
            except Exception as e:
                self._fail(f"新浪日线 {ts_code}", e)

            if df.empty:
                try:
                    raw = self._ak.stock_zh_a_hist(
                        symbol=code,
                        period="daily",
                        start_date=start,
                        end_date=end,
                        adjust="qfq",
                    )
                    if raw is not None and not raw.empty:
                        df = raw.rename(columns={
                            "日期": "trade_date", "开盘": "open", "收盘": "close",
                            "最高": "high", "最低": "low", "成交量": "vol",
                            "成交额": "amount", "振幅": "amplitude",
                            "涨跌幅": "pct_chg", "涨跌额": "change", "换手率": "turnover",
                        })
                except Exception as e:
                    self._fail(f"东财日线 {ts_code}", e)

            if df.empty:
                try:
                    raw = self._ak.stock_zh_a_hist_tx(
                        symbol=_ts_to_ak(ts_code),
                        start_date=start,
                        end_date=end,
                        adjust="qfq",
                    )
                    if raw is not None and not raw.empty:
                        df = raw.rename(columns={"date": "trade_date", "volume": "vol"})
                except Exception as e:
                    self._fail(f"腾讯日线 {ts_code}", e)

            if df.empty:
                return pd.DataFrame()

            keep = ["trade_date", "open", "close", "high", "low", "vol", "amount",
                    "amplitude", "pct_chg", "change", "turnover"]
            df = df[[c for c in keep if c in df.columns]].copy()
            df["ts_code"] = ts_code
            df["trade_date"] = df["trade_date"].astype(str).str[:10].str.replace("-", "")
            df = df[(df["trade_date"] >= start) & (df["trade_date"] <= end)]
            df = df.sort_values("trade_date").reset_index(drop=True)

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取日线行情失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 分红送股数据
    # ============================================================

    def get_dividend(self, ts_code: str) -> pd.DataFrame:
        """
        获取分红送股数据
        """
        cache_key = f"dividend_{ts_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        code = _ts_to_code(ts_code)
        try:
            # 新浪单只股票分红历史（0.5s 级别；原 stock_fhps_em 需拉全市场，非常慢）
            df = self._ak.stock_history_dividend_detail(symbol=code, indicator="分红")
            if df is None or df.empty:
                return pd.DataFrame()

            rename_map = {
                "公告日期": "ann_date",
                "派息": "cash_div",       # 每10股派息（税前，元）
                "送股": "stock_div",
                "转增": "transfer_sh",
                "股权登记日": "record_date",
                "除权除息日": "ex_date",
            }
            df = df.rename(columns=rename_map)
            keep_cols = [c for c in rename_map.values() if c in df.columns]
            df = df[keep_cols].copy()
            df["ts_code"] = ts_code

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取分红数据失败 {ts_code}", e)
            return pd.DataFrame()

    # ============================================================
    # 财务指标（ROE等）
    # ============================================================

    def get_fina_indicator(self, ts_code: str, period: str = "") -> pd.DataFrame:
        """
        获取财务指标

        Args:
            ts_code: 股票代码
            period: 报告期（YYYYMMDD）
        """
        cache_key = f"fina_indicator_{ts_code}_{period}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cached

        code = _ts_to_code(ts_code)
        try:
            df = self._ak.stock_financial_analysis_indicator(symbol=code)
            if df.empty:
                return pd.DataFrame()

            # 日期格式转换
            if "日期" in df.columns:
                df["end_date"] = df["日期"].astype(str).str.replace("-", "")

            rename_map = {
                "净资产收益率(%)": "roe",
                "总资产报酬率(%)": "roa",
                "净利润增长率(%)": "profit_yoy",
                "营业收入增长率(%)": "tr_yoy",
                "资产负债率(%)": "debt_to_assets",
                "流动比率": "current_ratio",
                "速动比率": "quick_ratio",
                "毛利率(%)": "grossprofit_margin",
                "净利率(%)": "netprofit_margin",
                "每股收益(元)": "eps",
                "每股净资产(元)": "bps",
            }
            df = df.rename(columns=rename_map)
            keep_cols = ["end_date"] + [c for c in rename_map.values() if c in df.columns]
            df = df[keep_cols].copy()

            # 百分比转换为小数
            for col in ["roe", "roa", "profit_yoy", "tr_yoy", "debt_to_assets",
                        "grossprofit_margin", "netprofit_margin"]:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce") / 100

            if period:
                df = df[df["end_date"].astype(str).str.contains(period[:4])]

            df["ts_code"] = ts_code
            df = df.sort_values("end_date", ascending=False).reset_index(drop=True)

            self._set_cache(cache_key, df)
            return df
        except Exception as e:
            self._fail(f"获取财务指标失败 {ts_code}", e)
            return pd.DataFrame()
