"""
Tushare Pro 数据源客户端
========================

封装 Tushare Pro API，提供：
  - Token 管理（环境变量 / 直接传入 / 配置文件）
  - 接口调用封装（自动重试、错误处理）
  - 常用数据缓存
  - 股票代码标准化

使用方式：
    from quant_valuation.data_sources import TushareClient
    client = TushareClient(token="你的token")
    df = client.get_income("600519.SH")
"""

from __future__ import annotations

import os
import time
import warnings
from typing import Dict, List, Optional

import pandas as pd

try:
    import tushare as ts
except ImportError:
    ts = None


class TushareClient:
    """
    Tushare Pro 客户端封装

    Token 获取优先级：
      1. 构造时传入 token 参数
      2. 环境变量 TUSHARE_TOKEN
      3. 配置文件 ~/.tushare_token
    """

    _instance: Optional["TushareClient"] = None
    _pro = None

    def __init__(
        self,
        token: Optional[str] = None,
        retry_count: int = 3,
        pause: float = 0.5,
    ):
        """
        初始化 Tushare 客户端

        Args:
            token: Tushare Pro API Token
            retry_count: 失败重试次数
            pause: 重试间隔（秒）
        """
        if ts is None:
            raise ImportError(
                "未安装 tushare，请先运行: pip install tushare pandas"
            )

        self.token = token or self._load_token()
        if not self.token:
            raise ValueError(
                "未找到 Tushare Token。请通过以下方式之一设置：\n"
                "  1. 构造参数: TushareClient(token='xxx')\n"
                "  2. 环境变量: set TUSHARE_TOKEN=xxx\n"
                "  3. 配置文件: 在用户目录下创建 .tushare_token 文件"
            )

        self.retry_count = retry_count
        self.pause = pause
        self._init_pro_api()

        # 简单内存缓存
        self._cache: Dict[str, pd.DataFrame] = {}

    def _load_token(self) -> Optional[str]:
        """从环境变量或配置文件加载 Token"""
        # 环境变量
        env_token = os.environ.get("TUSHARE_TOKEN", "").strip()
        if env_token:
            return env_token

        # 配置文件
        home = os.path.expanduser("~")
        token_file = os.path.join(home, ".tushare_token")
        if os.path.exists(token_file):
            with open(token_file, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return content

        return None

    def _init_pro_api(self):
        """初始化 Pro API"""
        ts.set_token(self.token)
        self._pro = ts.pro_api()

    @property
    def pro(self):
        """获取 pro_api 实例"""
        return self._pro

    # ---------- 核心调用封装 ----------

    def _call_api(self, api_name: str, use_cache: bool = True, **kwargs) -> pd.DataFrame:
        """
        通用 API 调用封装，带重试和缓存

        Args:
            api_name: 接口名称，如 'income', 'balancesheet'
            use_cache: 是否使用缓存
            **kwargs: 接口参数
        """
        # 缓存 key
        cache_key = f"{api_name}:" + "&".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        if use_cache and cache_key in self._cache:
            return self._cache[cache_key].copy()

        # 获取 API 函数
        api_func = getattr(self._pro, api_name, None)
        if api_func is None:
            raise ValueError(f"未知的 Tushare 接口: {api_name}")

        # 带重试调用
        last_error = None
        for attempt in range(self.retry_count):
            try:
                df = api_func(**kwargs)
                if use_cache:
                    self._cache[cache_key] = df.copy()
                return df
            except Exception as e:
                last_error = e
                if attempt < self.retry_count - 1:
                    time.sleep(self.pause * (attempt + 1))
                else:
                    raise RuntimeError(
                        f"Tushare 接口 {api_name} 调用失败（重试 {self.retry_count} 次）: {e}"
                    ) from last_error

        raise RuntimeError(f"Tushare 接口 {api_name} 调用失败: {last_error}")

    # ---------- 股票代码工具 ----------

    @staticmethod
    def normalize_ts_code(code: str) -> str:
        """
        将股票代码标准化为 Tushare 格式（如 600519.SH）

        支持输入：
          - 600519 → 600519.SH
          - 000001 → 000001.SZ
          - 600519.SH → 600519.SH (直接返回)
          - sh600519 → 600519.SH
        """
        code = code.strip().upper()

        # 已经是标准格式
        if "." in code and code.split(".")[-1] in ("SH", "SZ", "BJ"):
            return code

        # 去掉前缀
        if code.startswith("SH") or code.startswith("SZ") or code.startswith("BJ"):
            prefix = code[:2]
            num = code[2:]
            return f"{num}.{prefix}"

        # 纯数字代码
        if code.isdigit():
            if code.startswith("6") or code.startswith("9"):
                return f"{code}.SH"
            elif code.startswith("0") or code.startswith("3") or code.startswith("2"):
                return f"{code}.SZ"
            elif code.startswith("4") or code.startswith("8"):
                return f"{code}.BJ"

        return code

    # ---------- 股票基本信息 ----------

    def get_stock_basic(self, ts_code: Optional[str] = None) -> pd.DataFrame:
        """获取股票基本信息"""
        params = {}
        if ts_code:
            params["ts_code"] = self.normalize_ts_code(ts_code)
        return self._call_api("stock_basic", **params)

    def get_daily_basic(self, ts_code: str, trade_date: Optional[str] = None) -> pd.DataFrame:
        """
        获取每日基本指标（PE、PB、PS、市值等）

        Args:
            ts_code: 股票代码
            trade_date: 交易日期 YYYYMMDD，None 表示最新
        """
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if trade_date:
            params["trade_date"] = trade_date
        df = self._call_api("daily_basic", **params)
        return df

    def get_latest_daily_basic(self, ts_code: str) -> pd.Series:
        """获取最新的每日基本指标"""
        df = self.get_daily_basic(ts_code)
        if df.empty:
            raise ValueError(f"未找到 {ts_code} 的每日基本指标数据")
        return df.iloc[0]

    # ---------- 财务报表 ----------

    def get_income(
        self,
        ts_code: str,
        period: str = "",
        report_type: str = "1",
    ) -> pd.DataFrame:
        """
        获取利润表

        Args:
            ts_code: 股票代码
            period: 报告期 YYYYMMDD（年报是 1231，中报 0630，一季报 0331，三季报 0930）
                    为空返回全部
            report_type: 报表类型 1=合并报表, 2=单季
        """
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period
        if report_type:
            params["report_type"] = report_type
        return self._call_api("income", **params)

    def get_balancesheet(
        self,
        ts_code: str,
        period: str = "",
        report_type: str = "1",
    ) -> pd.DataFrame:
        """获取资产负债表"""
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period
        if report_type:
            params["report_type"] = report_type
        return self._call_api("balancesheet", **params)

    def get_cashflow(
        self,
        ts_code: str,
        period: str = "",
        report_type: str = "1",
    ) -> pd.DataFrame:
        """获取现金流量表"""
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period
        if report_type:
            params["report_type"] = report_type
        return self._call_api("cashflow", **params)

    def get_fina_indicator(
        self,
        ts_code: str,
        period: str = "",
    ) -> pd.DataFrame:
        """获取财务指标（ROE、ROA、毛利率等）"""
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if period:
            params["period"] = period
        return self._call_api("fina_indicator", **params)

    # ---------- 分红送股 ----------

    def get_dividend(self, ts_code: str) -> pd.DataFrame:
        """获取分红送股数据"""
        ts_code = self.normalize_ts_code(ts_code)
        return self._call_api("dividend", ts_code=ts_code)

    # ---------- 行业分类 ----------

    def get_industry(self, ts_code: Optional[str] = None, level: str = "L1") -> pd.DataFrame:
        """
        获取申万行业分类

        Args:
            ts_code: 股票代码，None 表示全部
            level: 行业级别 L1/L2/L3
        """
        params = {"level": level}
        if ts_code:
            params["ts_code"] = self.normalize_ts_code(ts_code)
        try:
            return self._call_api("index_classify", **params)
        except Exception:
            # 备用：用申万行业接口
            try:
                return self._call_api("sw_index_classify", **params)
            except Exception:
                return pd.DataFrame()

    def get_industry_member(self, industry_code: str) -> pd.DataFrame:
        """获取行业成分股"""
        try:
            return self._call_api("index_member", index_code=industry_code)
        except Exception:
            return pd.DataFrame()

    # ---------- 行情数据 ----------

    def get_daily(self, ts_code: str, start_date: str = "", end_date: str = "") -> pd.DataFrame:
        """获取日线行情"""
        ts_code = self.normalize_ts_code(ts_code)
        params = {"ts_code": ts_code}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        return self._call_api("daily", **params)

    # ---------- 缓存管理 ----------

    def clear_cache(self):
        """清空缓存"""
        self._cache.clear()

    def cache_size(self) -> int:
        """缓存条目数"""
        return len(self._cache)
