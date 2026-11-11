"""
绩效分析模块
============

提供详细的绩效评估和对比分析：
  - 收益率指标：总收益、年化、月均
  - 风险指标：波动率、最大回撤、下行风险
  - 风险调整收益：夏普、索提诺、卡玛比率
  - 基准对比：超额收益、信息比率、跟踪误差
  - 收益分布：胜率、盈亏比、最大单月涨跌
  - 多策略对比：并排展示多个策略的绩效
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pandas as pd

from .backtest_engine import BacktestResult


@dataclass
class PerformanceMetrics:
    """
    详细绩效指标

    收益类：
      total_return: 累计收益率
      annual_return: 年化收益率
      monthly_mean: 月均收益率
      best_month: 最大单月涨幅
      worst_month: 最大单月跌幅

    风险类：
      annual_vol: 年化波动率
      downside_vol: 下行波动率（只统计负收益）
      max_drawdown: 最大回撤
      max_drawdown_duration: 最大回撤持续期（月）

    风险调整：
      sharpe: 夏普比率
      sortino: 索提诺比率
      calmar: 卡玛比率（年化收益/最大回撤）

    收益分布：
      win_rate: 月度胜率
      profit_loss_ratio: 盈亏比（平均盈利/平均亏损绝对值）
      positive_months: 盈利月数
      negative_months: 亏损月数

    基准对比：
      excess_return: 年化超额收益
      tracking_error: 跟踪误差
      information_ratio: 信息比率
      alpha: 詹森阿尔法
      beta: 贝塔系数
    """
    # 收益
    total_return: float = 0.0
    annual_return: float = 0.0
    monthly_mean: float = 0.0
    best_month: float = 0.0
    worst_month: float = 0.0

    # 风险
    annual_vol: float = 0.0
    downside_vol: float = 0.0
    max_drawdown: float = 0.0
    max_drawdown_duration: int = 0

    # 风险调整
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0

    # 收益分布
    win_rate: float = 0.0
    profit_loss_ratio: float = 0.0
    positive_months: int = 0
    negative_months: int = 0

    # 基准对比
    excess_return: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0


class PerformanceAnalyzer:
    """
    绩效分析器

    功能：
      - 计算单策略详细绩效
      - 多策略横向对比
      - 生成文本报告
    """

    def __init__(self, risk_free_rate: float = 0.03):
        """
        Args:
            risk_free_rate: 无风险利率（年化）
        """
        self.risk_free_rate = risk_free_rate
        self.monthly_rf = (1 + risk_free_rate) ** (1 / 12) - 1

    def analyze(self, result: BacktestResult) -> PerformanceMetrics:
        """
        计算详细绩效指标

        Args:
            result: 回测结果

        Returns:
            PerformanceMetrics 详细指标
        """
        returns = result.returns
        if returns.empty:
            return PerformanceMetrics()

        # 过滤掉 0 收益（首期）
        nonzero_returns = returns[returns != 0]
        n = len(nonzero_returns)
        n_years = max(n / 12.0, 0.01)

        # ---- 收益 ----
        total_ret = result.total_return
        annual_ret = result.annual_return
        monthly_mean = nonzero_returns.mean() if n > 0 else 0
        best_month = nonzero_returns.max() if n > 0 else 0
        worst_month = nonzero_returns.min() if n > 0 else 0

        # ---- 风险 ----
        monthly_vol = nonzero_returns.std() if n > 1 else 0
        annual_vol = monthly_vol * (12 ** 0.5)

        # 下行波动率
        negative_returns = nonzero_returns[nonzero_returns < 0]
        downside_monthly = negative_returns.std() if len(negative_returns) > 1 else 0
        downside_vol = downside_monthly * (12 ** 0.5)

        max_dd = result.max_drawdown
        max_dd_dur = result.max_drawdown_duration

        # ---- 风险调整 ----
        sharpe = (annual_ret - self.risk_free_rate) / annual_vol if annual_vol > 0 else 0
        sortino = (annual_ret - self.risk_free_rate) / downside_vol if downside_vol > 0 else 0
        calmar = annual_ret / abs(max_dd) if max_dd != 0 else 0

        # ---- 收益分布 ----
        pos = (nonzero_returns > 0).sum()
        neg = (nonzero_returns < 0).sum()
        win_rate = pos / n if n > 0 else 0

        avg_profit = nonzero_returns[nonzero_returns > 0].mean() if pos > 0 else 0
        avg_loss = abs(nonzero_returns[nonzero_returns < 0].mean()) if neg > 0 else 0
        pl_ratio = avg_profit / avg_loss if avg_loss > 0 else 0

        # ---- 基准对比 ----
        excess_annual = 0.0
        tracking_err = 0.0
        info_ratio = 0.0
        alpha = 0.0
        beta = 0.0

        if not result.benchmark_returns.empty and len(result.benchmark_returns) == len(returns):
            bm_nonzero = result.benchmark_returns[returns != 0]
            excess = nonzero_returns.values - bm_nonzero.values
            excess_series = pd.Series(excess)

            # 年化超额
            excess_total = (1 + excess_series).prod() - 1
            excess_annual = (1 + excess_total) ** (1 / n_years) - 1

            # 跟踪误差
            tracking_err = excess_series.std() * (12 ** 0.5) if len(excess_series) > 1 else 0
            info_ratio = excess_annual / tracking_err if tracking_err > 0 else 0

            # Beta & Alpha
            bm_ret = bm_nonzero.values
            strat_ret = nonzero_returns.values
            if len(bm_ret) > 2 and bm_ret.std() > 0:
                cov = ((strat_ret - strat_ret.mean()) * (bm_ret - bm_ret.mean())).mean()
                var = bm_ret.var()
                beta = cov / var if var > 0 else 0
                alpha = annual_ret - (self.risk_free_rate + beta * (
                    (1 + bm_ret.mean()) ** 12 - 1 - self.risk_free_rate
                ))

        return PerformanceMetrics(
            # 收益
            total_return=total_ret,
            annual_return=annual_ret,
            monthly_mean=monthly_mean,
            best_month=best_month,
            worst_month=worst_month,
            # 风险
            annual_vol=annual_vol,
            downside_vol=downside_vol,
            max_drawdown=max_dd,
            max_drawdown_duration=max_dd_dur,
            # 风险调整
            sharpe=sharpe,
            sortino=sortino,
            calmar=calmar,
            # 分布
            win_rate=win_rate,
            profit_loss_ratio=pl_ratio,
            positive_months=int(pos),
            negative_months=int(neg),
            # 基准
            excess_return=excess_annual,
            tracking_error=tracking_err,
            information_ratio=info_ratio,
            alpha=alpha,
            beta=beta,
        )

    # ---------- 多策略对比 ----------

    def compare_strategies(
        self,
        results: Dict[str, BacktestResult],
    ) -> pd.DataFrame:
        """
        多策略横向对比

        Args:
            results: {策略名: BacktestResult} 字典

        Returns:
            DataFrame，行为策略，列为绩效指标
        """
        rows = {}
        for name, result in results.items():
            metrics = self.analyze(result)
            rows[name] = {
                "总收益(%)": round(metrics.total_return * 100, 2),
                "年化收益(%)": round(metrics.annual_return * 100, 2),
                "年化波动(%)": round(metrics.annual_vol * 100, 2),
                "夏普比率": round(metrics.sharpe, 2),
                "索提诺": round(metrics.sortino, 2),
                "卡玛比率": round(metrics.calmar, 2),
                "最大回撤(%)": round(metrics.max_drawdown * 100, 2),
                "回撤期(月)": metrics.max_drawdown_duration,
                "月度胜率(%)": round(metrics.win_rate * 100, 1),
                "盈亏比": round(metrics.profit_loss_ratio, 2),
                "超额收益(%)": round(metrics.excess_return * 100, 2),
                "信息比率": round(metrics.information_ratio, 2),
                "Alpha(%)": round(metrics.alpha * 100, 2),
                "Beta": round(metrics.beta, 2),
            }

        return pd.DataFrame(rows).T

    # ---------- 报告生成 ----------

    def generate_report(
        self,
        result: BacktestResult,
        title: Optional[str] = None,
    ) -> str:
        """生成详细的绩效报告文本"""
        m = self.analyze(result)
        name = title or result.strategy_name

        lines = [
            "=" * 60,
            f"  绩效分析报告 — {name}",
            "=" * 60,
            "",
            "【收益指标】",
            f"  累计收益率:   {m.total_return*100:>+10.2f}%",
            f"  年化收益率:   {m.annual_return*100:>+10.2f}%",
            f"  月均收益率:   {m.monthly_mean*100:>+10.2f}%",
            f"  最大单月涨幅:  {m.best_month*100:>+9.2f}%",
            f"  最大单月跌幅:  {m.worst_month*100:>+9.2f}%",
            "",
            "【风险指标】",
            f"  年化波动率:   {m.annual_vol*100:>10.2f}%",
            f"  下行波动率:   {m.downside_vol*100:>10.2f}%",
            f"  最大回撤:     {m.max_drawdown*100:>10.2f}%",
            f"  回撤持续期:   {m.max_drawdown_duration:>7d} 个月",
            "",
            "【风险调整收益】",
            f"  夏普比率:     {m.sharpe:>10.2f}",
            f"  索提诺比率:   {m.sortino:>10.2f}",
            f"  卡玛比率:     {m.calmar:>10.2f}",
            "",
            "【收益分布】",
            f"  月度胜率:     {m.win_rate*100:>10.1f}%",
            f"  盈亏比:       {m.profit_loss_ratio:>10.2f}",
            f"  盈利月数:     {m.positive_months:>7d} 个月",
            f"  亏损月数:     {m.negative_months:>7d} 个月",
            "",
        ]

        if m.tracking_error > 0 or m.excess_return != 0:
            lines += [
                "【基准对比】",
                f"  年化超额收益: {m.excess_return*100:>+10.2f}%",
                f"  跟踪误差:     {m.tracking_error*100:>10.2f}%",
                f"  信息比率:     {m.information_ratio:>10.2f}",
                f"  Alpha:        {m.alpha*100:>+10.2f}%",
                f"  Beta:         {m.beta:>10.2f}",
                "",
            ]

        lines.append("=" * 60)
        return "\n".join(lines)

    def generate_comparison_report(
        self,
        results: Dict[str, BacktestResult],
        title: str = "多策略对比",
    ) -> str:
        """生成多策略对比报告"""
        df = self.compare_strategies(results)

        lines = [
            "=" * 80,
            f"  {title}",
            "=" * 80,
            "",
        ]

        # 表格
        # 策略名列宽
        name_w = max(len(str(idx)) for idx in df.index) + 2
        name_w = max(name_w, 10)

        header = f"{'策略':<{name_w}}"
        for col in df.columns:
            header += f" {col:>10}"
        lines.append(header)
        lines.append("-" * len(header))

        for idx in df.index:
            row = f"{str(idx):<{name_w}}"
            for col in df.columns:
                val = df.loc[idx, col]
                row += f" {val:>10}"
            lines.append(row)

        lines += [
            "",
            "=" * 80,
            "  指标说明:",
            "    夏普 = (年化收益 - 无风险利率) / 年化波动",
            "    索提诺 = (年化收益 - 无风险利率) / 下行波动",
            "    卡玛 = 年化收益 / |最大回撤|",
            "    信息比率 = 年化超额收益 / 跟踪误差",
            "=" * 80,
        ]

        return "\n".join(lines)

    # ---------- 净值曲线文本图 ----------

    def plot_net_value_text(
        self,
        results: Dict[str, BacktestResult],
        height: int = 20,
        width: int = 70,
    ) -> str:
        """
        生成文本格式的净值曲线对比图

        Args:
            results: {策略名: BacktestResult}
            height: 图形高度（行数）
            width: 图形宽度（列数）
        """
        if not results:
            return "无数据"

        # 找到所有策略共有的日期和长度
        # 简化：取第一个策略的长度
        first_key = list(results.keys())[0]
        n_points = len(results[first_key].net_value)
        if n_points == 0:
            return "无数据"

        # 降采样到 width 个点
        step = max(1, n_points // width)
        sampled_indices = list(range(0, n_points, step))

        # 收集所有策略的采样值
        series_data = {}
        all_values = []
        for name, result in results.items():
            vals = result.net_value.values
            sampled = [vals[i] for i in sampled_indices if i < len(vals)]
            series_data[name] = sampled
            all_values.extend(sampled)

        # 加入基准
        if not results[first_key].benchmark_net_value.empty:
            bm_vals = results[first_key].benchmark_net_value.values
            bm_sampled = [bm_vals[i] for i in sampled_indices if i < len(bm_vals)]
            series_data["基准"] = bm_sampled
            all_values.extend(bm_sampled)

        if not all_values:
            return "无数据"

        v_min = min(all_values)
        v_max = max(all_values)
        v_range = v_max - v_min or 1

        # 符号映射
        symbols = list("█▓▒░●◆▲■")
        name_to_sym = {}
        for i, name in enumerate(series_data.keys()):
            name_to_sym[name] = symbols[i % len(symbols)]

        # 构建图表
        lines = []
        chart_width = len(sampled_indices)

        for row in range(height, -1, -1):
            # Y轴刻度
            val = v_min + (row / height) * v_range
            y_label = f"{val:>6.2f} │"
            chart_line = [" "] * chart_width

            # 在每列找到对应行的策略
            for col in range(chart_width):
                for name, values in series_data.items():
                    if col >= len(values):
                        continue
                    v = values[col]
                    pos = (v - v_min) / v_range * height
                    if abs(pos - row) < 0.5:
                        chart_line[col] = name_to_sym[name]
                        break  # 同一列只显示最前面的

            lines.append(y_label + "".join(chart_line))

        # X 轴
        lines.append("       └" + "─" * chart_width)

        # 图例
        legend = "       "
        for name, sym in name_to_sym.items():
            legend += f" {sym} {name}"
        lines.append(legend)

        return "\n".join(lines)
