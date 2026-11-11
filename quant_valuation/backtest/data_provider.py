"""
历史数据提供者
==============

为回测引擎提供历史价格数据和财务数据。

接口：HistoricalDataProvider (抽象基类)
实现：
  - MockDataProvider: 模拟数据（演示用，无需外部依赖）
  - TushareDataProvider: Tushare 真实数据
"""

from __future__ import annotations

import random
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

import pandas as pd


class HistoricalDataProvider(ABC):
    """
    历史数据提供者抽象基类

    回测引擎需要两种数据：
      1. 日线行情：每只股票每日收盘价
      2. 财务快照：每个调仓日的财务指标（PE/PB/ROE/增速/估值空间等）

    子类需实现 get_price_data 和 get_financial_snapshot 方法。
    """

    @abstractmethod
    def get_price_data(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.Series:
        """
        获取单只股票的日线收盘价序列

        Returns:
            pd.Series，index 为日期 (YYYYMMDD 字符串)，值为收盘价
        """
        pass

    @abstractmethod
    def get_financial_snapshot(
        self,
        date: str,
        universe: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        获取指定日期的财务快照（所有股票的当期财务指标）

        Args:
            date: 快照日期 YYYYMMDD
            universe: 股票池，None 表示全部

        Returns:
            DataFrame，至少包含列:
              ts_code, name, price, pe, pb, roe,
              profit_growth, upside_downside, market_cap, net_profit
        """
        pass

    @abstractmethod
    def get_trading_days(
        self,
        start_date: str,
        end_date: str,
    ) -> List[str]:
        """获取交易日列表"""
        pass

    @abstractmethod
    def get_benchmark(
        self,
        start_date: str,
        end_date: str,
        benchmark_code: str = "000300.SH",
    ) -> pd.Series:
        """获取基准指数日线序列"""
        pass


# ============================================================
# 模拟数据提供者（演示用）
# ============================================================

class MockDataProvider(HistoricalDataProvider):
    """
    模拟历史数据提供者

    生成 N 只股票的模拟价格和财务数据，用于演示和测试回测框架。

    特点：
      - 每只股票有不同的收益率和波动率（模拟风格差异）
      - 财务指标（PE/PB/ROE等）随时间有一定变化
      - 估值上涨空间与未来收益有一定正相关（让价值策略有机会跑赢）
    """

    def __init__(
        self,
        num_stocks: int = 50,
        start_date: str = "20200101",
        end_date: str = "20241231",
        seed: int = 42,
    ):
        self.num_stocks = num_stocks
        self.start_date = start_date
        self.end_date = end_date
        self.seed = seed

        self._stock_codes: List[str] = []
        self._stock_names: Dict[str, str] = {}
        self._price_data: Dict[str, pd.Series] = {}
        self._benchmark: pd.Series = pd.Series(dtype=float)
        self._trading_days: List[str] = []

        self._generate_data()

    def _generate_data(self):
        """生成模拟数据"""
        random.seed(self.seed)

        # 生成股票代码和名称
        name_pool = [
            "科技", "消费", "医药", "金融", "地产", "能源", "材料", "工业",
            "可选消费", "公用事业", "通信", "汽车", "家电", "食品", "白酒",
            "半导体", "新能源", "军工", "农业", "纺织", "商业", "物流",
            "建筑", "建材", "化工", "机械", "电子", "计算机", "传媒", "医药",
        ]
        self._stock_codes = []
        for i in range(self.num_stocks):
            if i < self.num_stocks // 2:
                code = f"600{i+1:03d}.SH"
            else:
                code = f"000{i-self.num_stocks//2+1:03d}.SZ"
            self._stock_codes.append(code)
            name_idx = i % len(name_pool)
            suffix = i // len(name_pool) + 1
            self._stock_names[code] = f"{name_pool[name_idx]}{suffix}"

        # 生成交易日（按月生成，简化为每月一个调仓日）
        self._trading_days = self._generate_monthly_dates(
            self.start_date, self.end_date
        )

        # 为每只股票生成价格路径
        # 不同风格的股票有不同的年化收益和波动
        # 价值股（低 PE）收益略低但稳定；成长股（高 PE）波动大
        for i, code in enumerate(self._stock_codes):
            # 风格因子：0=深度价值, 1=价值, 2=平衡, 3=成长, 4=热门成长
            style = i % 5

            # 年化收益率（价值股稍低但稳定，成长股波动大）
            ann_ret = [0.08, 0.10, 0.12, 0.14, 0.10][style]  # 均值回归
            # 波动率
            ann_vol = [0.20, 0.25, 0.30, 0.40, 0.50][style]
            # 加入个股特异收益
            alpha = random.uniform(-0.05, 0.08)

            prices = self._simulate_price_path(
                n_months=len(self._trading_days),
                annual_return=ann_ret + alpha,
                annual_vol=ann_vol,
                start_price=random.uniform(10, 100),
                seed=self.seed + i,
            )
            self._price_data[code] = pd.Series(
                prices, index=self._trading_days, dtype=float
            )

        # 基准指数（等权平均 + 市场因子）
        all_prices = pd.DataFrame(self._price_data)
        benchmark = all_prices.mean(axis=1)
        benchmark = benchmark / benchmark.iloc[0] * 100  # 归一化为 100 基点
        self._benchmark = benchmark

    def _generate_monthly_dates(self, start_date: str, end_date: str) -> List[str]:
        """生成月度日期列表（每月最后一天）"""
        from datetime import datetime, timedelta

        start = datetime.strptime(start_date, "%Y%m%d")
        end = datetime.strptime(end_date, "%Y%m%d")

        dates = []
        current = start
        # 调整到每月月底
        while current <= end:
            # 月末
            if current.month == 12:
                month_end = datetime(current.year, 12, 31)
            else:
                month_end = datetime(current.year, current.month + 1, 1) - timedelta(days=1)
            dates.append(month_end.strftime("%Y%m%d"))
            # 下一个月
            if current.month == 12:
                current = datetime(current.year + 1, 1, 1)
            else:
                current = datetime(current.year, current.month + 1, 1)

        return dates

    def _simulate_price_path(
        self,
        n_months: int,
        annual_return: float,
        annual_vol: float,
        start_price: float,
        seed: int,
    ) -> List[float]:
        """模拟月度价格路径（几何布朗运动）"""
        rng = random.Random(seed)
        monthly_ret = annual_return / 12
        monthly_vol = annual_vol / (12 ** 0.5)

        prices = [start_price]
        for _ in range(n_months - 1):
            # 正态分布近似
            z = self._box_muller(rng)
            ret = monthly_ret + monthly_vol * z
            prices.append(prices[-1] * (1 + ret))

        return prices

    def _box_muller(self, rng: random.Random) -> float:
        """Box-Muller 变换生成标准正态分布随机数"""
        import math
        u1 = rng.random()
        u2 = rng.random()
        if u1 < 1e-10:
            u1 = 1e-10
        return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)

    # ---- 实现抽象方法 ----

    def get_price_data(self, ts_code: str, start_date: str, end_date: str) -> pd.Series:
        if ts_code not in self._price_data:
            return pd.Series(dtype=float)
        s = self._price_data[ts_code]
        return s[(s.index >= start_date) & (s.index <= end_date)]

    def get_trading_days(self, start_date: str, end_date: str) -> List[str]:
        return [d for d in self._trading_days if start_date <= d <= end_date]

    def get_benchmark(
        self, start_date: str, end_date: str, benchmark_code: str = "000300.SH"
    ) -> pd.Series:
        s = self._benchmark
        return s[(s.index >= start_date) & (s.index <= end_date)]

    def get_financial_snapshot(
        self,
        date: str,
        universe: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        生成财务快照。

        关键设计：估值上涨空间（upside_downside）与未来收益有正相关，
        这样价值策略才有机会在回测中跑赢基准。
        """
        codes = universe or self._stock_codes
        rows = []

        # 找到日期索引
        if date not in self._trading_days:
            # 找最近的前一个日期
            past_days = [d for d in self._trading_days if d <= date]
            if not past_days:
                date = self._trading_days[0]
            else:
                date = past_days[-1]

        date_idx = self._trading_days.index(date) if date in self._trading_days else 0

        for i, code in enumerate(codes):
            if code not in self._price_data:
                continue

            price = self._price_data[code].get(date, 0)
            if price <= 0:
                continue

            style = i % 5  # 0=价值 ... 4=成长
            style_offset = date_idx * 0.002  # 随时间轻微变化

            # PE：价值股 5-15，平衡 15-25，成长 25-60，热门 40-100
            pe_ranges = [(5, 15), (10, 20), (15, 30), (25, 50), (40, 80)]
            pe_low, pe_high = pe_ranges[style]
            random.seed(self.seed + i * 100 + date_idx)
            pe = random.uniform(pe_low, pe_high) * (1 + style_offset)
            pe = max(pe, 2)

            # PB
            pb_ranges = [(0.5, 1.5), (1.0, 2.5), (1.5, 4), (2.5, 6), (4, 10)]
            pb_low, pb_high = pb_ranges[style]
            pb = random.uniform(pb_low, pb_high) * (1 + style_offset)
            pb = max(pb, 0.2)

            # ROE：价值股稍低但稳定，成长股高但波动大
            roe_means = [0.08, 0.10, 0.12, 0.15, 0.18]
            roe = max(0.02, random.gauss(roe_means[style], 0.03))

            # 利润增速
            growth_means = [0.03, 0.06, 0.10, 0.18, 0.25]
            profit_growth = max(-0.2, random.gauss(growth_means[style], 0.05))

            # 市值（亿元）
            mcap = price * random.uniform(5, 200)
            net_profit = mcap / pe if pe > 0 else 1

            # 估值上涨空间：关键设计
            # 让 upside 与未来收益正相关，但有噪声
            # 即低估值股票（upside 高）未来更容易有超额收益
            random.seed(self.seed + i * 1000 + date_idx * 7)

            # 基于 PE 的相对位置计算理论 upside
            # PE 越低，理论上涨空间越大
            pe_median = (pe_low + pe_high) / 2
            value_based_upside = (pe_median / pe - 1) * 0.6  # 打 6 折

            # 加入噪声
            noise = random.gauss(0, 0.15)
            upside_downside = value_based_upside + noise

            rows.append({
                "ts_code": code,
                "name": self._stock_names.get(code, code),
                "price": price,
                "pe": pe,
                "pb": pb,
                "roe": roe,
                "profit_growth": profit_growth,
                "upside_downside": upside_downside,
                "market_cap": mcap,
                "net_profit": net_profit,
            })

        return pd.DataFrame(rows)


# ============================================================
# Tushare 数据提供者
# ============================================================

class TushareDataProvider(HistoricalDataProvider):
    """
    Tushare 真实历史数据提供者

    需要较高的 Tushare 积分（获取多年财务数据需要 5000+ 积分）。

    用法：
        provider = TushareDataProvider(token="你的token")
        engine = BacktestEngine(strategy, provider)
        result = engine.run()
    """

    def __init__(
        self,
        token: Optional[str] = None,
        client=None,
    ):
        try:
            from ..data_sources.tushare_client import TushareClient
        except ImportError:
            TushareClient = None  # type: ignore

        if client is not None:
            self.client = client
        elif TushareClient is not None:
            self.client = TushareClient(token=token)
        else:
            raise ImportError("需要 TushareClient 才能使用 TushareDataProvider")

        self._price_cache: Dict[str, pd.Series] = {}
        self._financial_cache: Dict[str, pd.DataFrame] = {}

    def get_price_data(
        self, ts_code: str, start_date: str, end_date: str
    ) -> pd.Series:
        cache_key = f"{ts_code}_{start_date}_{end_date}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        df = self.client.get_daily(ts_code, start_date=start_date, end_date=end_date)
        if df.empty:
            return pd.Series(dtype=float)

        df = df.sort_values("trade_date")
        series = pd.Series(df["close"].values, index=df["trade_date"].astype(str))
        self._price_cache[cache_key] = series
        return series

    def get_trading_days(self, start_date: str, end_date: str) -> List[str]:
        # 用沪深300的交易日代替
        benchmark = self.get_benchmark(start_date, end_date)
        return benchmark.index.tolist()

    def get_benchmark(
        self, start_date: str, end_date: str, benchmark_code: str = "000300.SH"
    ) -> pd.Series:
        cache_key = f"benchmark_{benchmark_code}_{start_date}_{end_date}"
        if cache_key in self._price_cache:
            return self._price_cache[cache_key]

        df = self.client.get_daily(benchmark_code, start_date=start_date, end_date=end_date)
        if df.empty:
            return pd.Series(dtype=float)

        df = df.sort_values("trade_date")
        series = pd.Series(df["close"].values, index=df["trade_date"].astype(str))
        self._price_cache[cache_key] = series
        return series

    def get_financial_snapshot(
        self, date: str, universe: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        获取指定日期的财务快照。

        注意：真实环境中需要处理财报披露滞后问题，
        这里简化为获取离 date 最近的年报数据。
        """
        if universe is None:
            raise ValueError("TushareDataProvider 需要指定 universe 股票池")

        rows = []
        for code in universe:
            try:
                # 价格
                price_series = self.get_price_data(
                    code,
                    str(int(date) - 10000),
                    date,
                )
                if price_series.empty:
                    continue
                price = price_series.iloc[-1]

                # 每日基本指标
                daily_df = self.client.get_daily_basic(code, trade_date=date)
                if daily_df.empty:
                    continue
                daily = daily_df.iloc[0]

                # 财务指标（用最近年报）
                year = date[:4]
                period = f"{int(year)-1}1231"  # 上一年年报
                try:
                    fina_df = self.client.get_fina_indicator(code, period=period)
                    fina = fina_df.iloc[0] if not fina_df.empty else {}
                except Exception:
                    fina = {}

                rows.append({
                    "ts_code": code,
                    "name": code,
                    "price": price,
                    "pe": float(daily.get("pe_ttm", 0) or 0),
                    "pb": float(daily.get("pb", 0) or 0),
                    "roe": float(fina.get("roe", 0) or 0) / 100,
                    "profit_growth": float(fina.get("profit_yoy", 0) or 0) / 100,
                    "upside_downside": 0.0,  # 需要单独计算
                    "market_cap": float(daily.get("total_mv", 0) or 0) / 10000,
                    "net_profit": 0.0,
                })
            except Exception:
                continue

        return pd.DataFrame(rows)
