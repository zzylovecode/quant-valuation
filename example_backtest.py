"""
回测框架使用示例
=================

演示多种估值选股策略的历史回测效果，包含：
  1. 单策略回测 + 详细绩效
  2. 多策略横向对比
  3. 净值曲线可视化（文本图）
  4. 参数敏感性测试

运行方式：
    python example_backtest.py
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant_valuation.backtest import (
    BacktestEngine,
    PerformanceAnalyzer,
    MockDataProvider,
    ValueStrategy,
    QualityValueStrategy,
    GARPStrategy,
    DeepValueStrategy,
    LowPEStrategy,
    LowPBStrategy,
    CompositeScoreStrategy,
)


def demo_single_strategy():
    """演示1：单策略回测 + 详细绩效分析"""
    print("=" * 60)
    print("  演示 1：单策略回测（质优价廉策略）")
    print("=" * 60)
    print()

    # 1. 准备数据
    print("→ 生成模拟历史数据（50只股票 × 5年月度数据）...")
    provider = MockDataProvider(
        num_stocks=50,
        start_date="20200101",
        end_date="20241231",
        seed=42,
    )
    print(f"  股票数: {provider.num_stocks}")
    print(f"  区间: 2020-01 ~ 2024-12 ({len(provider._trading_days)} 个月)")
    print()

    # 2. 定义策略
    strategy = QualityValueStrategy(
        top_n=10,
        min_roe=0.12,
        min_upside=0.10,
        min_profit=1.0,
    )

    # 3. 回测
    print("→ 开始回测...\n")
    engine = BacktestEngine(
        strategy=strategy,
        data_provider=provider,
        start_date="20200101",
        end_date="20241231",
        rebalance_freq="M",
        transaction_cost=0.003,
        verbose=True,
    )
    result = engine.run()

    # 4. 详细绩效分析
    print("→ 详细绩效分析...\n")
    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    report = analyzer.generate_report(result)
    print(report)
    print()

    # 5. 调仓记录（前3次）
    print("→ 调仓记录（前 3 次）:")
    for i, record in enumerate(result.rebalance_records[:3]):
        holdings_str = ", ".join(
            f"{code}({w*100:.1f}%)" for code, w in record.holdings[:5]
        )
        if len(record.holdings) > 5:
            holdings_str += f" ... 共{len(record.holdings)}只"
        print(f"  [{record.date}] 换手: {record.turnover_rate*100:.1f}%  持仓: {holdings_str}")
    print()

    return result, provider


def demo_multi_strategy():
    """演示2：多策略横向对比"""
    print("=" * 60)
    print("  演示 2：多策略横向对比")
    print("=" * 60)
    print()

    # 数据
    provider = MockDataProvider(
        num_stocks=60,
        start_date="20200101",
        end_date="20241231",
        seed=88,
    )

    # 定义多个策略
    strategies = [
        ValueStrategy(top_n=10, name="价值策略"),
        QualityValueStrategy(top_n=10, name="质优价廉"),
        GARPStrategy(top_n=10, name="GARP成长"),
        DeepValueStrategy(top_n=10, name="深度价值"),
        LowPEStrategy(top_n=10, name="低PE"),
        LowPBStrategy(top_n=10, name="低PB"),
        CompositeScoreStrategy(top_n=10, name="多因子综合"),
    ]

    # 逐个回测
    print("→ 运行所有策略回测...\n")
    results = {}
    for strategy in strategies:
        print(f"  运行: {strategy.name}...", end=" ", flush=True)
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            start_date="20200101",
            end_date="20241231",
            rebalance_freq="M",
            transaction_cost=0.003,
            verbose=False,
        )
        result = engine.run()
        results[strategy.name] = result
        print(f"总收益 {result.total_return*100:+.1f}% | 夏普 {result.sharpe:.2f}")

    print()

    # 对比报告
    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    comparison = analyzer.generate_comparison_report(
        results, title="7 种选股策略对比（2020-2024）"
    )
    print(comparison)
    print()

    # 净值曲线图
    print("→ 净值曲线对比（文本图）")
    print()
    # 只展示前 4 个策略，避免太乱
    top_results = dict(list(results.items())[:4])
    chart = analyzer.plot_net_value_text(top_results, height=18, width=60)
    print(chart)
    print()

    return results, analyzer


def demo_parameter_sensitivity():
    """演示3：参数敏感性分析（选股数量对策略的影响）"""
    print("=" * 60)
    print("  演示 3：参数敏感性分析（选股数量 vs 收益/波动）")
    print("=" * 60)
    print()

    provider = MockDataProvider(
        num_stocks=80,
        start_date="20200101",
        end_date="20241231",
        seed=123,
    )

    top_n_list = [5, 10, 15, 20, 30, 50]
    results = {}

    print("→ 测试不同选股数量...\n")
    for top_n in top_n_list:
        strategy = QualityValueStrategy(top_n=top_n, name=f"Top{top_n}")
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            start_date="20200101",
            end_date="20241231",
            rebalance_freq="M",
            transaction_cost=0.003,
            verbose=False,
        )
        result = engine.run()
        results[f"Top {top_n:>2} 只"] = result
        print(f"  Top {top_n:>2} 只 → 年化 {result.annual_return*100:+.1f}% | "
              f"波动 {result.annual_vol*100:.1f}% | 夏普 {result.sharpe:.2f}")

    print()

    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    df = analyzer.compare_strategies(results)

    # 显示关键指标
    key_cols = ["年化收益(%)", "年化波动(%)", "夏普比率", "最大回撤(%)", "月度胜率(%)"]
    print("【选股数量敏感性】")
    print(f"{'选股数量':<10}", end="")
    for col in key_cols:
        print(f" {col:>10}", end="")
    print()
    print("-" * (10 + len(key_cols) * 11))
    for idx in df.index:
        print(f"{idx:<10}", end="")
        for col in key_cols:
            print(f" {df.loc[idx, col]:>10}", end="")
        print()
    print()

    print("💡 结论参考：")
    print("  - 选股数量越少，集中度越高，收益和波动通常都更大")
    print("  - 选股数量增加，分散化提升，波动下降，但超额收益可能被稀释")
    print("  - 最优的选股数量取决于策略的信号强度和交易成本")
    print()


def demo_holding_analysis():
    """演示4：持仓分析"""
    print("=" * 60)
    print("  演示 4：持仓与换手分析")
    print("=" * 60)
    print()

    provider = MockDataProvider(
        num_stocks=40,
        start_date="20200101",
        end_date="20241231",
        seed=2024,
    )

    strategies = {
        "价值策略(月调)": ValueStrategy(top_n=10),
        "深度价值(季调)": DeepValueStrategy(top_n=10),
    }

    freq_map = {
        "价值策略(月调)": "M",
        "深度价值(季调)": "Q",
    }

    print("→ 运行策略...\n")
    results = {}
    turnover_stats = {}

    for name, strategy in strategies.items():
        engine = BacktestEngine(
            strategy=strategy,
            data_provider=provider,
            start_date="20200101",
            end_date="20241231",
            rebalance_freq=freq_map[name],
            transaction_cost=0.003,
            verbose=False,
        )
        result = engine.run()
        results[name] = result

        # 换手统计
        turnovers = [r.turnover_rate for r in result.rebalance_records]
        avg_turnover = sum(turnovers) / len(turnovers) if turnovers else 0
        total_cost = sum(t * 0.003 for t in turnovers)
        turnover_stats[name] = {
            "调仓次数": len(result.rebalance_records),
            "平均单次换手": avg_turnover,
            "累计交易成本": total_cost,
        }

        print(f"  {name}:")
        print(f"    调仓 {len(result.rebalance_records)} 次 | "
              f"平均换手 {avg_turnover*100:.1f}% | "
              f"累计成本 {total_cost*100:.2f}%")

    print()

    # 对比
    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    comparison = analyzer.generate_comparison_report(
        results, title="调仓频率对比"
    )
    print(comparison)
    print()

    print("💡 说明：")
    print("  - 调仓频率越高，换手率越高，交易成本越大")
    print("  - 但更低的调仓频率可能导致持仓偏离最优解")
    print("  - 需要在信息时效性和交易成本之间取得平衡")
    print()


def main():
    print("\n" + "📊" * 30)
    print("       量化估值回测框架 — 完整演示")
    print("📊" * 30 + "\n")

    # 演示 1：单策略
    demo_single_strategy()

    # 演示 2：多策略对比
    demo_multi_strategy()

    # 演示 3：参数敏感性
    demo_parameter_sensitivity()

    # 演示 4：持仓分析
    demo_holding_analysis()

    print("=" * 60)
    print("  所有演示完成！")
    print("=" * 60)
    print()
    print("下一步：")
    print("  - 接入 Tushare 真实数据：使用 TushareDataProvider")
    print("  - 自定义策略：继承 BaseStrategy 实现 select_stocks")
    print("  - 导出结果：PerformanceAnalyzer.generate_report()")
    print()


if __name__ == "__main__":
    main()
