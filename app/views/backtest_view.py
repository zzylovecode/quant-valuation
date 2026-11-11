"""
策略回测页面
历史回测结果可视化：净值曲线、绩效指标、策略对比
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import get_token, has_token, get_data_mode

from quant_valuation.backtest import (
    BacktestEngine,
    PerformanceAnalyzer,
    MockDataProvider,
    TushareDataProvider,
    ValueStrategy,
    QualityValueStrategy,
    GARPStrategy,
    DeepValueStrategy,
    LowPEStrategy,
    LowPBStrategy,
    CompositeScoreStrategy,
)


# 回测用股票池
BACKTEST_POOLS = {
    "消费龙头（10只）": [
        "600519.SH", "000858.SZ", "000333.SZ", "600887.SH", "002415.SZ",
        "603288.SH", "600690.SH", "000651.SZ", "002508.SZ", "603833.SH",
    ],
    "金融龙头（10只）": [
        "600036.SH", "601318.SH", "601398.SH", "601288.SH", "601988.SH",
        "600030.SH", "601628.SH", "000001.SZ", "601166.SH", "600000.SH",
    ],
    "科技成长（10只）": [
        "300750.SZ", "002594.SZ", "002475.SZ", "300059.SZ", "603501.SH",
        "300274.SZ", "002415.SZ", "002230.SZ", "688981.SH", "600900.SH",
    ],
}


def get_strategy_map(top_n: int) -> dict:
    """获取策略映射"""
    return {
        "价值策略": ValueStrategy(top_n=top_n, name="价值策略"),
        "质优价廉": QualityValueStrategy(top_n=top_n, name="质优价廉"),
        "GARP成长": GARPStrategy(top_n=top_n, name="GARP成长"),
        "深度价值": DeepValueStrategy(top_n=top_n, name="深度价值"),
        "低PE": LowPEStrategy(top_n=top_n, name="低PE"),
        "低PB": LowPBStrategy(top_n=top_n, name="低PB"),
        "多因子综合": CompositeScoreStrategy(top_n=top_n, name="多因子综合"),
    }


@st.cache_data(show_spinner=False)
def run_mock_backtest(strategy_name: str, top_n: int, n_stocks: int,
                      rebalance_freq: str, cost: float, seed: int = 42):
    """Mock 回测"""
    strategy_map = get_strategy_map(top_n)
    strategy = strategy_map[strategy_name]
    provider = MockDataProvider(
        num_stocks=n_stocks,
        start_date="20200101",
        end_date="20241231",
        seed=seed,
    )
    engine = BacktestEngine(
        strategy=strategy,
        data_provider=provider,
        start_date="20200101",
        end_date="20241231",
        rebalance_freq=rebalance_freq,
        transaction_cost=cost,
        verbose=False,
    )
    result = engine.run()
    return result


@st.cache_data(show_spinner="Tushare 回测运行中（数据量较大，请耐心等待）...", ttl=7200)
def run_tushare_backtest(token: str, strategy_name: str, top_n: int,
                         stock_codes: tuple, start_date: str, end_date: str,
                         rebalance_freq: str, cost: float):
    """Tushare 真实数据回测"""
    strategy_map = get_strategy_map(top_n)
    strategy = strategy_map[strategy_name]
    provider = TushareDataProvider(token=token)
    # 设置股票池
    provider.universe = list(stock_codes)

    engine = BacktestEngine(
        strategy=strategy,
        data_provider=provider,
        start_date=start_date,
        end_date=end_date,
        rebalance_freq=rebalance_freq,
        transaction_cost=cost,
        verbose=False,
    )
    result = engine.run()
    return result


@st.cache_data(show_spinner=False)
def run_mock_multi_backtest(strategies: list, top_n: int, n_stocks: int,
                            rebalance_freq: str, cost: float, seed: int = 88):
    """Mock 多策略对比回测"""
    strategy_map = get_strategy_map(top_n)
    provider = MockDataProvider(
        num_stocks=n_stocks,
        start_date="20200101",
        end_date="20241231",
        seed=seed,
    )
    results = {}
    for name in strategies:
        if name not in strategy_map:
            continue
        engine = BacktestEngine(
            strategy=strategy_map[name],
            data_provider=provider,
            start_date="20200101",
            end_date="20241231",
            rebalance_freq=rebalance_freq,
            transaction_cost=cost,
            verbose=False,
        )
        results[name] = engine.run()
    return results


@st.cache_data(show_spinner="Tushare 多策略回测中...", ttl=7200)
def run_tushare_multi_backtest(token: str, strategies: list, top_n: int,
                               stock_codes: tuple, start_date: str, end_date: str,
                               rebalance_freq: str, cost: float):
    """Tushare 多策略对比回测"""
    strategy_map = get_strategy_map(top_n)
    provider = TushareDataProvider(token=token)
    provider.universe = list(stock_codes)

    results = {}
    for name in strategies:
        if name not in strategy_map:
            continue
        engine = BacktestEngine(
            strategy=strategy_map[name],
            data_provider=provider,
            start_date=start_date,
            end_date=end_date,
            rebalance_freq=rebalance_freq,
            transaction_cost=cost,
            verbose=False,
        )
        results[name] = engine.run()
    return results


def render():
    st.title("📉 策略回测")
    st.markdown("历史回测绩效分析与多策略对比")
    st.markdown("---")

    data_mode = get_data_mode()
    if data_mode == "tushare" and has_token():
        st.success("📡 真实数据模式 (Tushare)")
        st.caption("⚠️ 真实回测需要较高 Tushare 积分（5000+），数据量较大时可能较慢")
    else:
        st.info("🎯 演示数据模式 (Mock)")
        st.caption("💡 前往「数据设置」配置 Token 后可使用真实数据")

    st.markdown("---")

    # 模式切换
    mode = st.radio(
        "回测模式",
        ["单策略深度分析", "多策略对比"],
        horizontal=True,
    )

    st.markdown("---")

    if mode == "单策略深度分析":
        render_single_backtest()
    else:
        render_multi_comparison()


def render_single_backtest():
    """单策略深度回测分析"""
    data_mode = get_data_mode()

    if data_mode == "tushare" and has_token():
        # Tushare 模式
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            strategy_name = st.selectbox("策略", [
                "价值策略", "质优价廉", "GARP成长",
                "深度价值", "低PE", "低PB", "多因子综合",
            ])
        with col2:
            top_n = st.slider("持股数量", 3, 10, 5, 1)
        with col3:
            pool_name = st.selectbox("股票池", list(BACKTEST_POOLS.keys()))
        with col4:
            cost = st.slider("交易成本", 0.0, 0.01, 0.003, 0.001, format="%.1f%%")

        col5, col6, col7 = st.columns(3)
        with col5:
            rebalance_freq = st.selectbox(
                "调仓频率",
                [("Q", "季度"), ("Y", "年度"), ("M", "月度")],
                format_func=lambda x: x[1],
            )
        with col6:
            start_year = st.number_input("起始年份", 2018, 2023, 2021, 1)
        with col7:
            end_year = st.number_input("结束年份", 2019, 2025, 2024, 1)

        stock_codes = BACKTEST_POOLS[pool_name]
        freq_code = rebalance_freq[0]
        start_date = f"{start_year}0101"
        end_date = f"{end_year}1231"

        if st.button("▶️ 开始回测", type="primary"):
            with st.spinner("回测计算中（真实数据较慢，请耐心等待）..."):
                try:
                    # 清除缓存强制重新运行
                    run_tushare_backtest.clear()
                    result = run_tushare_backtest(
                        get_token(), strategy_name, top_n, tuple(stock_codes),
                        start_date, end_date, freq_code, cost,
                    )
                    st.session_state["bt_single_result"] = result
                    st.session_state["bt_single_ready"] = True
                except Exception as e:
                    st.error(f"回测失败: {e}")
                    return

        if not st.session_state.get("bt_single_ready", False):
            st.info("👆 配置好参数后点击「开始回测」")
            return

        result = st.session_state["bt_single_result"]
    else:
        # Mock 模式
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            strategy_name = st.selectbox("策略", [
                "价值策略", "质优价廉", "GARP成长",
                "深度价值", "低PE", "低PB", "多因子综合",
            ])
        with col2:
            top_n = st.slider("持股数量", 3, 30, 10, 1)
        with col3:
            n_stocks = st.slider("股票池大小", 20, 100, 50, 10)
        with col4:
            cost = st.slider("交易成本", 0.0, 0.01, 0.003, 0.001, format="%.1f%%")

        col5, col6, _ = st.columns(3)
        with col5:
            rebalance_freq = st.selectbox(
                "调仓频率",
                [("M", "月度"), ("Q", "季度"), ("Y", "年度")],
                format_func=lambda x: x[1],
            )
        with col6:
            seed = st.number_input("随机种子", 1, 9999, 42, 1)

        freq_code = rebalance_freq[0]

        # 运行回测
        with st.spinner("回测计算中..."):
            result = run_mock_backtest(strategy_name, top_n, n_stocks, freq_code, cost, int(seed))

    # 绩效指标卡片
    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    metrics = analyzer.analyze(result)

    st.subheader("📊 绩效概览")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("总收益率", f"{metrics.total_return*100:+.2f}%")
    c2.metric("年化收益", f"{metrics.annual_return*100:+.2f}%")
    c3.metric("年化波动", f"{metrics.annual_vol*100:.2f}%")
    c4.metric("夏普比率", f"{metrics.sharpe:.2f}")

    c5, c6, c7, c8 = st.columns(4)
    c5.metric("最大回撤", f"{metrics.max_drawdown*100:.2f}%")
    c6.metric("卡玛比率", f"{metrics.calmar:.2f}")
    c7.metric("月度胜率", f"{metrics.win_rate*100:.1f}%")
    c8.metric("盈亏比", f"{metrics.profit_loss_ratio:.2f}")

    st.markdown("---")

    # 净值曲线
    st.subheader("📈 净值曲线")

    fig = go.Figure()

    # 策略净值
    fig.add_trace(go.Scatter(
        x=result.net_value.index,
        y=result.net_value.values,
        mode="lines",
        name=strategy_name,
        line=dict(color="#1f6feb", width=2.5),
        fill="tozeroy",
        fillcolor="rgba(31, 111, 235, 0.1)",
    ))

    # 基准
    if not result.benchmark_net_value.empty:
        fig.add_trace(go.Scatter(
            x=result.benchmark_net_value.index,
            y=result.benchmark_net_value.values,
            mode="lines",
            name="基准指数",
            line=dict(color="#6c757d", width=1.5, dash="dash"),
        ))

    fig.update_layout(
        height=450,
        xaxis_title="日期",
        yaxis_title="净值",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 回撤图 + 月度收益分布
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("📉 回撤曲线")
        max_so_far = result.net_value.cummax()
        drawdown = (result.net_value - max_so_far) / max_so_far * 100

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=drawdown.index, y=drawdown.values,
            mode="lines", fill="tozeroy",
            line=dict(color="#dc3545", width=1),
            fillcolor="rgba(220, 53, 69, 0.2)",
            name="回撤",
        ))
        fig.update_layout(
            height=300,
            yaxis_title="回撤 (%)",
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.subheader("📊 月度收益分布")
        monthly_returns = result.returns[result.returns != 0] * 100

        fig = go.Figure(data=[go.Histogram(
            x=monthly_returns.values,
            nbinsx=20,
            marker_color="#1f6feb",
            opacity=0.8,
        )])
        fig.add_vline(x=0, line_color="#666", line_width=1)
        fig.update_layout(
            height=300,
            xaxis_title="月度收益率 (%)",
            yaxis_title="频次",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    # 详细指标表
    st.markdown("---")
    st.subheader("📋 详细绩效指标")

    metrics_data = {
        "类别": ["收益", "收益", "收益", "收益", "收益",
                "风险", "风险", "风险", "风险",
                "风险调整", "风险调整", "风险调整",
                "分布", "分布", "分布", "分布",
                "基准对比", "基准对比", "基准对比", "基准对比", "基准对比"],
        "指标": ["总收益率", "年化收益", "月均收益", "最大单月涨幅", "最大单月跌幅",
                "年化波动率", "下行波动率", "最大回撤", "回撤持续期(月)",
                "夏普比率", "索提诺比率", "卡玛比率",
                "月度胜率", "盈亏比", "盈利月数", "亏损月数",
                "年化超额收益", "跟踪误差", "信息比率", "Alpha", "Beta"],
        "数值": [
            f"{metrics.total_return*100:+.2f}%",
            f"{metrics.annual_return*100:+.2f}%",
            f"{metrics.monthly_mean*100:+.2f}%",
            f"{metrics.best_month*100:+.2f}%",
            f"{metrics.worst_month*100:+.2f}%",
            f"{metrics.annual_vol*100:.2f}%",
            f"{metrics.downside_vol*100:.2f}%",
            f"{metrics.max_drawdown*100:.2f}%",
            f"{metrics.max_drawdown_duration}",
            f"{metrics.sharpe:.2f}",
            f"{metrics.sortino:.2f}",
            f"{metrics.calmar:.2f}",
            f"{metrics.win_rate*100:.1f}%",
            f"{metrics.profit_loss_ratio:.2f}",
            f"{metrics.positive_months}",
            f"{metrics.negative_months}",
            f"{metrics.excess_return*100:+.2f}%",
            f"{metrics.tracking_error*100:.2f}%",
            f"{metrics.information_ratio:.2f}",
            f"{metrics.alpha*100:+.2f}%",
            f"{metrics.beta:.2f}",
        ],
    }
    df = pd.DataFrame(metrics_data)
    st.dataframe(df, use_container_width=True, hide_index=True)


def render_multi_comparison():
    """多策略对比"""
    data_mode = get_data_mode()
    st.subheader("策略选择")

    strategies = st.multiselect(
        "选择要对比的策略",
        ["价值策略", "质优价廉", "GARP成长", "深度价值", "低PE", "低PB", "多因子综合"],
        default=["价值策略", "质优价廉", "深度价值", "低PB"],
    )

    if data_mode == "tushare" and has_token():
        # Tushare 模式
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            top_n = st.slider("持股数量", 3, 10, 5, 1, key="cmp_top_n")
        with col2:
            pool_name = st.selectbox("股票池", list(BACKTEST_POOLS.keys()), key="cmp_pool")
        with col3:
            cost = st.slider("交易成本", 0.0, 0.01, 0.003, 0.001, format="%.1f%%", key="cmp_cost")
        with col4:
            years = st.number_input("回测年数", 1, 5, 3, 1, key="cmp_years")

        stock_codes = BACKTEST_POOLS[pool_name]
        start_date = f"{2025-years}0101"
        end_date = "20241231"

        if st.button("▶️ 开始多策略回测", type="primary"):
            with st.spinner("多策略回测计算中（真实数据较慢，请耐心等待）..."):
                try:
                    run_tushare_multi_backtest.clear()
                    results = run_tushare_multi_backtest(
                        get_token(), strategies, top_n, tuple(stock_codes),
                        start_date, end_date, "Q", cost,
                    )
                    st.session_state["bt_multi_results"] = results
                    st.session_state["bt_multi_ready"] = True
                except Exception as e:
                    st.error(f"回测失败: {e}")
                    return

        if not st.session_state.get("bt_multi_ready", False):
            st.info("👆 配置好参数后点击「开始多策略回测」")
            return

        results = st.session_state["bt_multi_results"]
    else:
        # Mock 模式
        col1, col2, col3 = st.columns(3)
        with col1:
            top_n = st.slider("持股数量", 3, 30, 10, 1, key="cmp_top_n")
        with col2:
            n_stocks = st.slider("股票池大小", 20, 100, 60, 10, key="cmp_n")
        with col3:
            cost = st.slider("交易成本", 0.0, 0.01, 0.003, 0.001, format="%.1f%%", key="cmp_cost")

        if not strategies:
            st.warning("请至少选择一个策略")
            return

        # 运行回测
        with st.spinner("多策略回测计算中..."):
            results = run_mock_multi_backtest(strategies, top_n, n_stocks, "M", cost, seed=88)

    if not results:
        st.error("回测结果为空")
        return

    # 净值曲线对比
    st.subheader("📈 净值曲线对比")

    fig = go.Figure()
    colors = px.colors.qualitative.Plotly
    for i, (name, result) in enumerate(results.items()):
        fig.add_trace(go.Scatter(
            x=result.net_value.index,
            y=result.net_value.values,
            mode="lines",
            name=name,
            line=dict(width=2, color=colors[i % len(colors)]),
        ))

    # 基准
    first_key = list(results.keys())[0]
    bm = results[first_key].benchmark_net_value
    if not bm.empty:
        fig.add_trace(go.Scatter(
            x=bm.index, y=bm.values,
            mode="lines", name="基准",
            line=dict(color="#6c757d", width=1.5, dash="dash"),
        ))

    fig.update_layout(
        height=500,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=10, r=10, t=10, b=10),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 绩效对比表
    st.subheader("📊 绩效对比")
    analyzer = PerformanceAnalyzer(risk_free_rate=0.03)
    comparison_df = analyzer.compare_strategies(results)
    st.dataframe(comparison_df, use_container_width=True)

    # 雷达图
    st.subheader("🎯 能力雷达图")

    # 归一化指标用于雷达图
    radar_metrics = ["年化收益(%)", "夏普比率", "卡玛比率", "月度胜率(%)"]
    # 波动和回撤取反（越低越好 → 越高得分）
    # 简化：只选正向指标

    fig = go.Figure()
    for name, result in results.items():
        m = analyzer.analyze(result)
        # 归一化得分（相对于最好的）
        values = [
            m.annual_return * 100,
            m.sharpe,
            m.calmar,
            m.win_rate * 100,
        ]
        fig.add_trace(go.Scatterpolar(
            r=values,
            theta=["年化收益", "夏普比率", "卡玛比率", "月度胜率"],
            fill="toself",
            name=name,
            opacity=0.6,
        ))

    fig.update_layout(
        polar=dict(radialaxis=dict(visible=True)),
        height=450,
        margin=dict(l=20, r=20, t=20, b=20),
        legend=dict(orientation="h", yanchor="bottom", y=-0.1, xanchor="center", x=0.5),
    )
    st.plotly_chart(fig, use_container_width=True)
