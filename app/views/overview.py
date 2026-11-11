"""
概览页面
展示工具功能总览和快速入口
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

from utils import get_default_stock, run_valuation, format_pct


def render():
    st.title("📊 量化估值分析工具")
    st.markdown("---")

    # 功能卡片
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.info("### 📈 单股估值\n\nDCF/PE/PB/PEG/DDM/RIM\n7种方法综合估值")
    with col2:
        st.success("### 🔥 敏感性分析\n\nDCF 增长率 × 折现率\n热力图实时计算")
    with col3:
        st.warning("### 📋 批量估值\n\n多股票排行榜\n多种策略筛选")
    with col4:
        st.error("### 📉 策略回测\n\n历史回测绩效\n净值曲线对比")

    st.markdown("---")

    # 快速演示
    st.subheader("⚡ 快速预览")

    data = get_default_stock()
    result = run_valuation(data, "growth")
    report = result["report"]

    # 核心指标卡片
    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.metric(
            "当前股价",
            f"¥{data.current_price:.2f}",
            delta=None,
        )
    with c2:
        upside = report.weighted_upside
        delta_color = "normal" if upside > 0 else "inverse"
        st.metric(
            "内在价值",
            f"¥{report.weighted_value:.2f}",
            delta=f"{upside*100:+.1f}%",
            delta_color=delta_color,
        )
    with c3:
        st.metric(
            "估值评级",
            report.rating,
            delta=f"可信度: {report.confidence}",
        )
    with c4:
        st.metric(
            "估值区间",
            f"¥{report.low_value:.0f} ~ ¥{report.high_value:.0f}",
            delta=f"中位数 ¥{report.median_value:.0f}",
        )

    st.markdown("---")

    # 各方法估值对比图
    st.subheader("📊 各估值方法对比")

    method_df = pd.DataFrame({
        "方法": list(report.method_values.keys()),
        "内在价值(元)": list(report.method_values.values()),
        "涨跌空间(%)": [v * 100 for v in report.method_upsides.values()],
        "权重(%)": [report.weights.get(m, 0) * 100 for m in report.method_values.keys()],
    })

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=method_df["方法"],
        y=method_df["内在价值(元)"],
        name="内在价值",
        marker_color="#1f6feb",
        opacity=0.8,
        text=[f"¥{v:.0f}" for v in method_df["内在价值(元)"]],
        textposition="outside",
    ))
    fig.add_hline(
        y=data.current_price,
        line_dash="dash",
        line_color="#dc3545",
        annotation_text=f"当前价 ¥{data.current_price:.0f}",
        annotation_position="right",
    )
    fig.update_layout(
        title="各方法估值结果对比",
        xaxis_title="估值方法",
        yaxis_title="每股内在价值 (元)",
        height=450,
        hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)

    # 估值区间带
    st.subheader("🎯 估值区间定位")
    zones = result["analyzer"].value_zone_analysis(report.weighted_value)

    zone_colors = [
        ("极度低估区", "#28a745"),
        ("低估区", "#95d5b2"),
        ("合理区下限", "#ffe66d"),
        ("内在价值", "#1f6feb"),
        ("合理区上限", "#ffe66d"),
        ("高估区", "#f8961e"),
        ("极度高估区", "#dc3545"),
    ]

    fig = go.Figure()
    max_val = zones["极度高估区"] * 1.1

    # 绘制区间色块
    zone_bounds = [
        (0, zones["极度低估区"], "#28a745", 0.3),
        (zones["极度低估区"], zones["低估区"], "#52b788", 0.25),
        (zones["低估区"], zones["合理区下限"], "#b7e4c7", 0.2),
        (zones["合理区下限"], zones["内在价值"], "#e8f5e9", 0.1),
        (zones["内在价值"], zones["合理区上限"], "#fff3cd", 0.1),
        (zones["合理区上限"], zones["高估区"], "#ffe5b4", 0.2),
        (zones["高估区"], zones["极度高估区"], "#f8961e", 0.25),
        (zones["极度高估区"], max_val, "#dc3545", 0.3),
    ]

    for i, (x0, x1, color, opacity) in enumerate(zone_bounds):
        fig.add_shape(
            type="rect",
            x0=x0, x1=x1, y0=0, y1=1,
            fillcolor=color, opacity=opacity, line_width=0,
        )

    # 当前价格标记
    fig.add_vline(
        x=data.current_price,
        line_width=3, line_color="#1a1a2e",
        annotation_text=f"当前价 ¥{data.current_price:.0f}",
        annotation_position="top",
        annotation_font_size=14,
    )

    # 内在价值标记
    fig.add_vline(
        x=report.weighted_value,
        line_width=2, line_color="#1f6feb", line_dash="dash",
        annotation_text=f"内在价值 ¥{report.weighted_value:.0f}",
        annotation_position="bottom",
        annotation_font_size=12,
    )

    fig.update_xaxes(range=[0, max_val], title="股价 (元)")
    fig.update_yaxes(showticklabels=False, showgrid=False)
    fig.update_layout(
        height=180,
        margin=dict(l=10, r=10, t=10, b=10),
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 安全边际
    st.info(
        f"💡 **安全边际建议**：25%安全边际买入价 = "
        f"¥{report.weighted_value * 0.75:.2f} "
        f"（当前价 ¥{data.current_price:.2f}）"
    )
