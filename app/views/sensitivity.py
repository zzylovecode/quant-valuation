"""
敏感性分析页面
DCF 模型增长率 × 折现率 热力图
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import numpy as np

from utils import get_default_stock
from quant_valuation import DCFModel


def render():
    st.title("🔥 DCF 敏感性分析")
    st.markdown("分析增长率和折现率变化对内在价值的影响")
    st.markdown("---")

    data = get_default_stock()

    # 参数控制
    col1, col2, col3 = st.columns(3)
    with col1:
        method = st.radio("DCF 方法", ["FCFF", "FCFE"], horizontal=True)
    with col2:
        terminal_g = st.slider("永续增长率", 0.0, 0.06, 0.03, 0.005, format="%.1f%%")
    with col3:
        high_years = st.slider("高速增长期", 3, 10, 5, 1, format="%d 年")

    st.markdown(" ")

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("#### 增长率范围")
        g_min = st.slider("最低增长率", 0.0, 0.20, 0.05, 0.01, format="%.0f%%", key="g_min")
        g_max = st.slider("最高增长率", 0.0, 0.30, 0.20, 0.01, format="%.0f%%", key="g_max")
        g_steps = st.slider("增长率步数", 5, 15, 9, 1, key="g_steps")

    with col2:
        st.markdown("#### 折现率范围")
        w_min = st.slider("最低折现率", 0.05, 0.12, 0.07, 0.005, format="%.1f%%", key="w_min")
        w_max = st.slider("最高折现率", 0.08, 0.18, 0.13, 0.005, format="%.1f%%", key="w_max")
        w_steps = st.slider("折现率步数", 5, 15, 9, 1, key="w_steps")

    st.markdown("---")

    # 计算敏感性矩阵
    dcf = DCFModel(data)

    growth_rates = np.linspace(g_min, g_max, g_steps)
    wacc_rates = np.linspace(w_min, w_max, w_steps)

    # 构建结果矩阵
    values = np.zeros((len(growth_rates), len(wacc_rates)))
    for i, g in enumerate(growth_rates):
        for j, w in enumerate(wacc_rates):
            try:
                if method == "FCFF":
                    res = dcf.fcff_valuation(
                        growth_rate=g, high_growth_years=high_years,
                        terminal_growth=terminal_g, wacc=w,
                    )
                else:
                    res = dcf.fcfe_valuation(
                        growth_rate=g, high_growth_years=high_years,
                        terminal_growth=terminal_g, cost_of_equity=w,
                    )
                values[i, j] = res.intrinsic_value_per_share
            except Exception:
                values[i, j] = np.nan

    # 热力图
    current_price = data.current_price
    upside_pct = (values - current_price) / current_price * 100

    fig = go.Figure(data=go.Heatmap(
        z=upside_pct,
        x=[f"{w*100:.1f}%" for w in wacc_rates],
        y=[f"{g*100:.1f}%" for g in growth_rates],
        colorscale="RdYlGn",
        zmid=0,
        text=[[f"¥{v:.1f}<br>({u:+.1f}%)" for v, u in zip(row_v, row_u)]
              for row_v, row_u in zip(values, upside_pct)],
        texttemplate="%{text}",
        textfont={"size": 10},
        hovertemplate="增长率: %{y}<br>折现率: %{x}<br>%{text}<extra></extra>",
        colorbar=dict(
            title="涨跌空间(%)",
            tickformat=".0f",
        ),
    ))

    fig.update_layout(
        title=f"DCF ({method}) 敏感性分析 — 每股内在价值涨跌空间",
        xaxis_title="折现率 (WACC)",
        yaxis_title="增长率 (g)",
        height=600,
        margin=dict(l=20, r=20, t=60, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

    # 数据表
    with st.expander("📋 查看数值表格"):
        df = pd.DataFrame(
            values,
            index=[f"g={g*100:.1f}%" for g in growth_rates],
            columns=[f"WACC={w*100:.1f}%" for w in wacc_rates],
        )
        df = df.round(2)
        st.dataframe(df, use_container_width=True)

    # 关键参考点
    st.markdown("---")
    st.subheader("📌 关键参考")

    c1, c2, c3 = st.columns(3)
    current_val = values[g_steps//2, w_steps//2]
    c1.metric("中间情形", f"¥{current_val:.2f}",
              delta=f"{(current_val-current_price)/current_price*100:+.1f}%")

    best_val = values[-1, 0]
    c2.metric("乐观情形", f"¥{best_val:.2f}",
              delta=f"{(best_val-current_price)/current_price*100:+.1f}%",
              delta_color="normal")

    worst_val = values[0, -1]
    c3.metric("悲观情形", f"¥{worst_val:.2f}",
              delta=f"{(worst_val-current_price)/current_price*100:+.1f}%",
              delta_color="inverse")

    st.info(
        f"💡 **解读**：当前股价 ¥{current_price:.2f}，"
        f"在最乐观假设下上涨空间 {(best_val-current_price)/current_price*100:+.1f}%，"
        f"最悲观假设下下跌空间 {(worst_val-current_price)/current_price*100:+.1f}%。"
        f"估值区间 ¥{worst_val:.0f} ~ ¥{best_val:.0f}。"
    )
