"""
回测引擎
========

核心功能：
  - 按指定频率调仓（月频/季频）
  - 管理持仓和权重
  - 计算日度/月度组合收益
  - 记录每一期的持仓明细
  - 考虑交易成本（可选）

回测流程：
  1. 初始化：确定回测区间、初始资金、策略
  2. 每个调仓日：
     a. 获取当期财务快照
     b. 策略选股并分配权重
     c. 计算交易成本（换仓费）
     d. 更新持仓
  3. 每个交易日：
     a. 根据个股涨跌计算组合收益
     b. 记录净值
  4. 回测结束，返回 BacktestResult
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import pandas as pd

from .strategies import BaseStrategy
from .data_provider import HistoricalDataProvider


@dataclass
class Position:
    """单只持仓"""
    ts_code: str
    name: str
    weight: float       # 权重
    shares: float       # 股数（相对值）
    avg_cost: float     # 平均成本


@dataclass
class RebalanceRecord:
    """调仓记录"""
    date: str
    holdings: List[Tuple[str, float]]  # [(ts_code, weight), ...]
    portfolio_value: float  # 调仓后组合净值
    turnover_rate: float    # 换手率


@dataclass
class BacktestResult:
    """
    回测结果

    Attributes:
        strategy_name: 策略名称
        net_value: 组合净值序列（初始为 1.0）
        returns: 组合收益率序列
        benchmark_net_value: 基准净值序列
        benchmark_returns: 基准收益率序列
        excess_returns: 超额收益率序列
        rebalance_records: 调仓记录列表
        final_value: 期末净值
        total_return: 总收益率
        annual_return: 年化收益率
        annual_vol: 年化波动率
        sharpe: 夏普比率
        max_drawdown: 最大回撤
        win_rate: 胜率（月度）
        rebalance_count: 调仓次数
    """
    strategy_name: str
    net_value: pd.Series
    returns: pd.Series
    benchmark_net_value: pd.Series = field(default_factory=pd.Series)
    benchmark_returns: pd.Series = field(default_factory=pd.Series)
    excess_returns: pd.Series = field(default_factory=pd.Series)
    rebalance_records: List[RebalanceRecord] = field(default_factory=list)
    final_value: float = 0.0
    total_return: float = 0.0
    annual_return: float = 0.0
    annual_vol: float = 0.0
    sharpe: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0
    win_rate: float = 0.0
    rebalance_count: int = 0


class BacktestEngine:
    """
    回测引擎

    使用方式：
        engine = BacktestEngine(
            strategy=my_strategy,
            data_provider=provider,
            start_date="20200101",
            end_date="20241231",
            rebalance_freq="M",  # M=月, Q=季
            initial_capital=1.0,
            transaction_cost=0.003,  # 千三手续费
        )
        result = engine.run()
        print(f"总收益: {result.total_return*100:.2f}%")
    """

    def __init__(
        self,
        strategy: BaseStrategy,
        data_provider: HistoricalDataProvider,
        start_date: str,
        end_date: str,
        rebalance_freq: str = "M",
        initial_capital: float = 1.0,
        transaction_cost: float = 0.003,
        benchmark_code: str = "000300.SH",
        universe: Optional[List[str]] = None,
        verbose: bool = True,
    ):
        """
        Args:
            strategy: 选股策略实例
            data_provider: 历史数据提供者
            start_date: 回测开始日期 YYYYMMDD
            end_date: 回测结束日期 YYYYMMDD
            rebalance_freq: 调仓频率 'M'=月, 'Q'=季, 'Y'=年
            initial_capital: 初始资金（净值初始值）
            transaction_cost: 单边交易成本（比例）
            benchmark_code: 基准指数代码
            universe: 股票池，None 表示数据提供者的全部股票
            verbose: 是否打印进度
        """
        self.strategy = strategy
        self.data_provider = data_provider
        self.start_date = start_date
        self.end_date = end_date
        self.rebalance_freq = rebalance_freq
        self.initial_capital = initial_capital
        self.transaction_cost = transaction_cost
        self.benchmark_code = benchmark_code
        self.universe = universe
        self.verbose = verbose

        # 运行时状态
        self._current_value: float = initial_capital
        self._holdings: Dict[str, float] = {}  # ts_code -> weight
        self._net_values: List[Tuple[str, float]] = []
        self._rebalance_records: List[RebalanceRecord] = []

    # ---------- 主入口 ----------

    def run(self) -> BacktestResult:
        """执行回测"""
        if self.verbose:
            print(f"开始回测: {self.strategy.name}")
            print(f"  区间: {self.start_date} ~ {self.end_date}")
            print(f"  调仓频率: {self.rebalance_freq}")
            print(f"  交易成本: {self.transaction_cost*100:.2f}%")
            print()

        # 1. 获取交易日和调仓日
        trading_days = self.data_provider.get_trading_days(
            self.start_date, self.end_date
        )
        if not trading_days:
            raise ValueError("没有交易日数据")

        rebalance_dates = self._get_rebalance_dates(trading_days)

        if self.verbose:
            print(f"  交易日数: {len(trading_days)}")
            print(f"  调仓次数: {len(rebalance_dates)}")
            print()

        # 2. 获取基准数据
        benchmark = self.data_provider.get_benchmark(
            self.start_date, self.end_date, self.benchmark_code
        )
        # 归一化
        if not benchmark.empty:
            benchmark = benchmark / benchmark.iloc[0] * self.initial_capital

        # 3. 主循环
        rebalance_set = set(rebalance_dates)
        self._current_value = self.initial_capital
        self._holdings = {}

        for i, date in enumerate(trading_days):
            # 调仓日
            if date in rebalance_set or (i == 0 and not self._holdings):
                self._rebalance(date)

            # 计算当日收益
            daily_return = self._calc_daily_return(date)
            self._current_value *= (1 + daily_return)

            # 记录净值
            self._net_values.append((date, self._current_value))

            # 进度
            if self.verbose and (i + 1) % 12 == 0:
                total_ret = (self._current_value / self.initial_capital - 1) * 100
                print(f"  [{date}] 净值: {self._current_value:.4f}  收益: {total_ret:+.2f}%")

        # 4. 构建结果
        result = self._build_result(trading_days, benchmark)

        if self.verbose:
            print()
            print(f"回测完成: {self.strategy.name}")
            print(f"  总收益: {result.total_return*100:+.2f}%")
            print(f"  年化收益: {result.annual_return*100:+.2f}%")
            print(f"  夏普比率: {result.sharpe:.2f}")
            print(f"  最大回撤: {result.max_drawdown*100:.2f}%")
            print(f"  月度胜率: {result.win_rate*100:.1f}%")
            print()

        return result

    # ---------- 内部方法 ----------

    def _get_rebalance_dates(self, trading_days: List[str]) -> List[str]:
        """根据调仓频率确定调仓日"""
        if self.rebalance_freq == "D":
            return trading_days

        dates = []
        last_period = ""

        for date in trading_days:
            if self.rebalance_freq == "M":
                period = date[:6]  # YYYYMM
            elif self.rebalance_freq == "Q":
                month = int(date[4:6])
                quarter = (month - 1) // 3 + 1
                period = f"{date[:4]}Q{quarter}"
            elif self.rebalance_freq == "Y":
                period = date[:4]
            else:  # 默认月频
                period = date[:6]

            if period != last_period:
                dates.append(date)
                last_period = period

        return dates

    def _rebalance(self, date: str):
        """执行调仓"""
        # 获取当期财务快照
        snapshot = self.data_provider.get_financial_snapshot(
            date, universe=self.universe
        )
        if snapshot.empty:
            return

        # 策略选股
        new_holdings = self.strategy.select_stocks(snapshot, date)

        if not new_holdings:
            return

        # 计算换手率
        old_weights = dict(self._holdings)
        new_weights = {code: w for code, w in new_holdings}
        turnover = 0.0
        all_codes = set(old_weights.keys()) | set(new_weights.keys())
        for code in all_codes:
            old_w = old_weights.get(code, 0)
            new_w = new_weights.get(code, 0)
            turnover += abs(new_w - old_w)
        turnover = turnover / 2  # 双边转单边

        # 扣除交易成本
        cost = turnover * self.transaction_cost
        self._current_value *= (1 - cost)

        # 更新持仓
        self._holdings = dict(new_holdings)

        # 记录
        self._rebalance_records.append(
            RebalanceRecord(
                date=date,
                holdings=new_holdings,
                portfolio_value=self._current_value,
                turnover_rate=turnover,
            )
        )

    def _calc_daily_return(self, date: str) -> float:
        """计算组合日收益率（加权平均）"""
        if not self._holdings:
            return 0.0

        portfolio_return = 0.0
        for code, weight in self._holdings.items():
            price_series = self.data_provider.get_price_data(
                code, date, date
            )
            if price_series.empty:
                continue

            current_price = price_series.iloc[0]

            # 获取前一天价格
            all_trading = self.data_provider.get_trading_days(
                self.start_date, date
            )
            if len(all_trading) >= 2:
                prev_date = all_trading[-2]
                prev_series = self.data_provider.get_price_data(
                    code, prev_date, prev_date
                )
                if not prev_series.empty:
                    prev_price = prev_series.iloc[0]
                    if prev_price > 0:
                        stock_return = (current_price - prev_price) / prev_price
                        portfolio_return += weight * stock_return

        return portfolio_return

    def _build_result(
        self,
        trading_days: List[str],
        benchmark: pd.Series,
    ) -> BacktestResult:
        """构建回测结果对象并计算绩效指标"""
        # 净值序列
        dates = [d for d, _ in self._net_values]
        values = [v for _, v in self._net_values]
        net_value = pd.Series(values, index=dates, dtype=float)

        # 收益率
        returns = net_value.pct_change().fillna(0)

        # 基准
        if not benchmark.empty:
            # 对齐日期
            common_dates = [d for d in dates if d in benchmark.index]
            benchmark_aligned = benchmark.reindex(common_dates).ffill()
            # 用对齐后的长度
            if len(common_dates) > 0:
                bm_values = benchmark_aligned.values
                benchmark_net_value = pd.Series(bm_values, index=common_dates)
                benchmark_returns = benchmark_net_value.pct_change().fillna(0)
            else:
                benchmark_net_value = pd.Series(dtype=float)
                benchmark_returns = pd.Series(dtype=float)
        else:
            benchmark_net_value = pd.Series(dtype=float)
            benchmark_returns = pd.Series(dtype=float)

        # 超额收益
        if not benchmark_returns.empty and len(returns) == len(benchmark_returns):
            excess = returns.values - benchmark_returns.values
            excess_returns = pd.Series(excess, index=dates)
        else:
            excess_returns = pd.Series(dtype=float)

        # 计算绩效指标
        n_days = len(net_value)
        n_years = max(n_days / 12.0, 0.01)  # 月频数据，每年 12 期

        total_return = net_value.iloc[-1] / net_value.iloc[0] - 1 if n_days > 0 else 0
        annual_return = (1 + total_return) ** (1 / n_years) - 1

        # 年化波动率
        if len(returns) > 1:
            monthly_vol = returns.std()
            annual_vol = monthly_vol * (12 ** 0.5)  # 月频 → 年化
        else:
            annual_vol = 0

        # 夏普比率（假设无风险利率 3%）
        risk_free = 0.03
        sharpe = (annual_return - risk_free) / annual_vol if annual_vol > 0 else 0

        # 最大回撤
        max_so_far = net_value.expanding().max()
        drawdown = (net_value - max_so_far) / max_so_far
        max_drawdown = drawdown.min() if not drawdown.empty else 0

        # 最大回撤持续期
        max_dd_duration = self._calc_max_drawdown_duration(net_value)

        # 月度胜率（月频数据）
        positive_months = (returns > 0).sum()
        total_months = len(returns[returns != 0])
        win_rate = positive_months / total_months if total_months > 0 else 0

        return BacktestResult(
            strategy_name=self.strategy.name,
            net_value=net_value,
            returns=returns,
            benchmark_net_value=benchmark_net_value,
            benchmark_returns=benchmark_returns,
            excess_returns=excess_returns,
            rebalance_records=self._rebalance_records,
            final_value=net_value.iloc[-1] if n_days > 0 else self.initial_capital,
            total_return=total_return,
            annual_return=annual_return,
            annual_vol=annual_vol,
            sharpe=sharpe,
            max_drawdown=max_drawdown,
            max_drawdown_duration=max_dd_duration,
            win_rate=win_rate,
            rebalance_count=len(self._rebalance_records),
        )

    def _calc_max_drawdown_duration(self, net_value: pd.Series) -> int:
        """计算最大回撤持续期（月数）"""
        if net_value.empty:
            return 0

        peak_idx = 0
        max_duration = 0
        current_duration = 0
        peak_value = net_value.iloc[0]

        for i in range(len(net_value)):
            if net_value.iloc[i] >= peak_value:
                peak_value = net_value.iloc[i]
                peak_idx = i
                current_duration = 0
            else:
                current_duration = i - peak_idx
                max_duration = max(max_duration, current_duration)

        return max_duration
