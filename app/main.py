"""
量化估值可视化界面
=================

基于 Streamlit 的交互式估值分析工具。

启动方式：
    streamlit run app/main.py

功能模块：
  1. 单股估值 - 调整参数实时查看各估值方法结果
  2. 敏感性分析 - DCF 增长率 × 折现率热力图
  3. 批量估值 - 多股票估值排行榜
  4. 策略回测 - 历史回测绩效可视化
"""

import sys
import os

# 确保能导入 quant_valuation 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st

st.set_page_config(
    page_title="量化估值分析工具",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 自定义样式
st.markdown("""
<style>
    .main .block-container { padding-top: 2rem; }
    h1, h2, h3 { color: #1f6feb; }
    .metric-card {
        background: #f0f6ff;
        border-radius: 10px;
        padding: 15px;
        margin: 5px 0;
        border-left: 4px solid #1f6feb;
    }
    .metric-card.green { border-left-color: #28a745; background: #f0fff4; }
    .metric-card.red { border-left-color: #dc3545; background: #fff0f0; }
    .metric-card.orange { border-left-color: #fd7e14; background: #fff8f0; }
    .stProgress > div > div > div { background-color: #1f6feb; }
</style>
""", unsafe_allow_html=True)

# 侧边栏导航
with st.sidebar:
    st.title("📊 量化估值工具")
    st.markdown("---")

    page = st.radio(
        "功能导航",
        [
            "🏠 概览",
            "📈 单股估值",
            "🔥 敏感性分析",
            "📋 批量估值排行",
            "📉 策略回测",
            "⚙️ 数据设置",
        ],
        index=0,
    )

    st.markdown("---")
    st.caption("量化估值模型 v0.6.5")
    st.caption("支持 DCF / PE / PB / PEG / DDM / RIM")

# 页面路由
if "概览" in page:
    from views import overview
    overview.render()
elif "单股估值" in page:
    from views import single_valuation
    single_valuation.render()
elif "敏感性分析" in page:
    from views import sensitivity
    sensitivity.render()
elif "批量估值" in page:
    from views import batch_screen
    batch_screen.render()
elif "策略回测" in page:
    from views import backtest_view
    backtest_view.render()
elif "数据设置" in page:
    from views import settings
    settings.render()
