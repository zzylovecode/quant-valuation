"""
单股估值页面
交互调整财务参数和估值假设，实时查看估值结果变化
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go

from utils import (
    get_default_stock,
    run_valuation,
    format_pct,
    get_token,
    has_token,
    get_data_mode,
    load_stock_from_tushare,
    load_stock_from_akshare,
)
from quant_valuation import ValuationAnalyzer


def render():
    st.title("📈 单股估值分析")
    st.markdown("---")

    # 初始化 session state
    if "stock_data" not in st.session_state:
        st.session_state.stock_data = get_default_stock()
    if "current_ts_code" not in st.session_state:
        st.session_state.current_ts_code = "600519.SH"

    data = st.session_state.stock_data

    # 两栏布局：左侧参数，右侧结果
    with st.sidebar:
        # 股票选择
        st.subheader("🔍 股票选择")

        mode = get_data_mode()
        mode_labels = {
            "mock": "演示数据",
            "akshare": "AKShare 免费数据",
            "tushare": "Tushare 专业数据",
        }
        st.caption(f"当前模式：{mode_labels.get(mode, '演示数据')}")

        if mode in ("tushare", "akshare"):
            # 真实数据模式（Tushare 或 AKShare）
            if mode == "tushare" and not has_token():
                st.warning("⚠️ 请先在「数据设置」页配置 Tushare Token")
            else:
                ts_code = st.text_input(
                    "股票代码",
                    value=st.session_state.current_ts_code,
                    placeholder="如：600519.SH / 000001.SZ",
                    help="格式：6位代码.市场后缀（SH=上海, SZ=深圳）",
                )

                # 常用股票快捷选择
                quick_codes = {
                    "贵州茅台": "600519.SH",
                    "招商银行": "600036.SH",
                    "宁德时代": "300750.SZ",
                    "美的集团": "000333.SZ",
                    "比亚迪": "002594.SZ",
                    "中国平安": "601318.SH",
                }
                with st.expander("⚡ 快捷选择", expanded=False):
                    cols = st.columns(2)
                    for i, (name, code) in enumerate(quick_codes.items()):
                        with cols[i % 2]:
                            if st.button(name, key=f"quick_{code}", use_container_width=True):
                                st.session_state.current_ts_code = code
                                st.rerun()

                btn_label = "📥 加载数据" if mode == "akshare" else "📥 从 Tushare 加载"
                if st.button(btn_label, type="primary", use_container_width=True):
                    try:
                        with st.spinner(f"正在加载 {ts_code} ..."):
                            if mode == "akshare":
                                load_stock_from_akshare.clear()
                                new_data = load_stock_from_akshare(ts_code)
                            else:
                                load_stock_from_tushare.clear()
                                new_data = load_stock_from_tushare(get_token(), ts_code)
                            st.session_state.stock_data = new_data
                            st.session_state.current_ts_code = ts_code
                            st.success(f"✅ 已加载 {new_data.name}")
                            st.rerun()
                    except Exception as e:
                        st.error(f"加载失败: {e}")
        else:
            st.info("💡 当前为演示模式，使用内置示例数据。\n\n"
                    "前往「数据设置」页可切换到免费真实数据模式。")

        st.markdown("---")
        st.subheader("⚙️ 估值参数")

        company_type = st.selectbox(
            "公司类型",
            ["growth", "value", "mature", "cyclical", "high_tech", "financial"],
            format_func=lambda x: {
                "growth": "🌱 成长型",
                "value": "💰 价值型",
                "mature": "🏢 成熟型",
                "cyclical": "📊 周期型",
                "high_tech": "🚀 高科技",
                "financial": "🏦 金融",
            }[x],
            index=0,
        )

        st.markdown("#### DCF 参数")
        dcf_growth = st.slider("高速增长期增速", 0.0, 0.30, float(data.calc_profit_growth_rate(3)), 0.01,
                               format="%.0%%")
        dcf_years = st.slider("高速增长期年数", 3, 10, 5, 1)
        terminal_growth = st.slider("永续增长率", 0.0, 0.06, 0.03, 0.005,
                                    format="%.1f%%")
        wacc = st.slider("折现率 (WACC)", 0.05, 0.15, 0.09, 0.005,
                         format="%.1f%%")

        st.markdown("#### 相对估值参数")
        use_industry = st.checkbox("使用行业倍数", value=True)
        industry_pe = st.number_input("行业 PE", 0.0, 100.0, float(data.industry_pe), 1.0)
        industry_pb = st.number_input("行业 PB", 0.0, 30.0, float(data.industry_pb), 0.5)

        recalc = st.button("🔄 重新计算", type="primary", use_container_width=True)

    # 主内容区
    col1, col2 = st.columns([3, 2])

    with col1:
        # 公司基本信息
        st.subheader(f"🏢 {data.name}")
        st.caption(f"股票代码：{data.ticker}")

        # 关键价格指标
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("当前股价", f"¥{data.current_price:.2f}")
        c2.metric("总市值", f"{data.calc_market_cap():.1f}亿")
        c3.metric("PE (TTM)", f"{data.calc_pe():.1f}")
        c4.metric("PB", f"{data.calc_pb():.2f}")

        st.markdown("---")

        # 估值结果
        st.subheader("📊 综合估值结果")

        # 用自定义参数重新估值
        if recalc or "valuation_result" not in st.session_state:
            analyzer = ValuationAnalyzer(data)
            weights = ValuationAnalyzer.get_weights_for_company_type(company_type)
            growth_rate = dcf_growth

            report = analyzer.full_valuation(
                weights=weights,
                dcf_params={
                    "growth_rate": growth_rate,
                    "high_growth_years": dcf_years,
                    "terminal_growth": terminal_growth,
                    "wacc": wacc,
                },
                relative_params={
                    "industry_pe": industry_pe if use_industry else None,
                    "industry_pb": industry_pb if use_industry else None,
                    "expected_growth": growth_rate,
                    "roe_adjusted": True,
                },
            )
            st.session_state.valuation_result = {
                "report": report,
                "analyzer": analyzer,
            }

        result = st.session_state.valuation_result
        report = result["report"]

        # 估值评级大字显示
        upside = report.weighted_upside
        color = "#28a745" if upside > 0 else "#dc3545"
        st.markdown(
            f"""
            <div style="text-align: center; padding: 30px; background: linear-gradient(135deg, #f5f7fa 0%, #e4e8ec 100%); border-radius: 15px; margin: 15px 0;">
                <div style="font-size: 1rem; color: #666; margin-bottom: 10px;">综合内在价值</div>
                <div style="font-size: 3rem; font-weight: bold; color: #1f6feb;">¥{report.weighted_value:.2f}</div>
                <div style="font-size: 1.5rem; color: {color}; margin-top: 10px;">
                    {'📈' if upside > 0 else '📉'} {upside*100:+.2f}%
                </div>
                <div style="font-size: 1.1rem; margin-top: 15px;">
                    估值评级：<strong>{report.rating}</strong>
                    <span style="color: #888; margin-left: 20px;">可信度：{report.confidence}</span>
                </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # 各方法估值柱状图
        st.markdown("#### 各方法估值对比")
        method_data = []
        for method, val in report.method_values.items():
            method_data.append({
                "方法": method,
                "内在价值(元)": round(val, 2),
                "涨跌空间(%)": round(report.method_upsides.get(method, 0) * 100, 1),
                "权重(%)": round(report.weights.get(method, 0) * 100, 1),
            })

        df = pd.DataFrame(method_data)
        df = df.sort_values("内在价值(元)", ascending=True)

        fig = go.Figure()
        colors = ["#28a745" if v > data.current_price else "#dc3545" for v in df["内在价值(元)"]]
        fig.add_trace(go.Bar(
            y=df["方法"],
            x=df["内在价值(元)"],
            orientation="h",
            marker_color=colors,
            text=[f"¥{v:.1f} ({p:+.1f}%)" for v, p in zip(df["内在价值(元)"], df["涨跌空间(%)"])],
            textposition="outside",
        ))
        fig.add_vline(
            x=data.current_price,
            line_dash="dash", line_color="#333", line_width=2,
            annotation_text=f"当前价 ¥{data.current_price:.0f}",
            annotation_position="top right",
        )
        fig.update_layout(
            height=400,
            xaxis_title="每股内在价值 (元)",
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        # 财务指标卡片
        st.subheader("📋 核心财务指标")

        with st.expander("盈利能力", expanded=True):
            st.metric("净利润", f"{data.net_profit:.1f} 亿")
            st.metric("ROE", f"{data.calc_roe()*100:.2f}%")
            st.metric("净利率", f"{data.calc_net_margin()*100:.2f}%")
            st.metric("营收", f"{data.revenue:.1f} 亿")

        with st.expander("资产与现金流"):
            st.metric("净资产", f"{data.total_equity:.1f} 亿")
            st.metric("每股净资产", f"¥{data.bvps:.2f}")
            st.metric("经营现金流", f"{data.operating_cash_flow:.1f} 亿")
            st.metric("自由现金流", f"{data.calc_free_cash_flow():.1f} 亿")

        with st.expander("分红与增长"):
            st.metric("每股分红", f"¥{data.dividend_per_share:.2f}")
            st.metric("分红率", f"{data.dividend_payout_ratio*100:.1f}%")
            st.metric("净利润 CAGR", f"{data.calc_profit_growth_rate(3)*100:.2f}%")
            st.metric("营收 CAGR", f"{data.calc_revenue_growth_rate(3)*100:.2f}%")

        with st.expander("估值区间明细"):
            zones = result["analyzer"].value_zone_analysis(report.weighted_value)
            for zone, price in zones.items():
                pct = (price / zones["极度高估区"]) * 100
                st.markdown(
                    f"<div style='display: flex; justify-content: space-between; margin: 4px 0;'>"
                    f"<span>{zone}</span>"
                    f"<span style='font-weight: bold;'>¥{price:.2f}</span>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

    # 底部：历史财务数据
    st.markdown("---")
    st.subheader("📈 历史财务数据")

    hist_df = pd.DataFrame({
        "年份": [f"第{i+1}年" for i in range(len(data.historical_net_profit))],
        "净利润(亿)": data.historical_net_profit,
        "营收(亿)": data.historical_revenue,
    })

    c1, c2 = st.columns(2)
    with c1:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=hist_df["年份"], y=hist_df["净利润(亿)"],
            name="净利润", marker_color="#1f6feb",
        ))
        fig.update_layout(title="净利润趋势", height=300)
        st.plotly_chart(fig, use_container_width=True)

    with c2:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=hist_df["年份"], y=hist_df["营收(亿)"],
            name="营收", marker_color="#28a745",
        ))
        fig.update_layout(title="营收趋势", height=300)
        st.plotly_chart(fig, use_container_width=True)
