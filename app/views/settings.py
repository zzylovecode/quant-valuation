"""
数据设置页面
Tushare Token 配置、数据源选择
"""

import streamlit as st
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from utils import get_token, set_token, has_token, get_data_mode, set_data_mode


def render():
    st.title("⚙️ 数据设置")
    st.markdown("配置数据源和 API Token")
    st.markdown("---")

    # 初始化 session state
    if "tushare_token" not in st.session_state:
        env_token = os.environ.get("TUSHARE_TOKEN", "")
        st.session_state.tushare_token = env_token
    if "data_mode" not in st.session_state:
        st.session_state.data_mode = "tushare" if has_token() else "mock"

    st.subheader("🔑 Tushare Token")
    st.info(
        "使用真实 A 股财报数据需要 Tushare Token。\n\n"
        "👉 免费注册获取：[tushare.pro](https://tushare.pro/register)"
    )

    current_token = get_token()
    token_input = st.text_input(
        "Tushare API Token",
        type="password",
        value=current_token,
        placeholder="输入你的 Tushare Token（约 32 位字符串）",
    )

    col1, col2 = st.columns(2)
    with col1:
        if st.button("💾 保存 Token", type="primary", use_container_width=True):
            set_token(token_input)
            st.success("✅ Token 已保存（当前浏览器会话有效）")
            if token_input:
                set_data_mode("tushare")
                st.rerun()
    with col2:
        if st.button("🗑️ 清除 Token", use_container_width=True):
            set_token("")
            set_data_mode("mock")
            st.rerun()

    # Token 状态指示
    if has_token():
        st.success(f"✅ 当前 Token 有效（已保存，前8位: {current_token[:8]}...）")
    else:
        st.warning("⚠️ 未设置 Token，当前使用演示数据")

    st.markdown("---")

    # 数据模式
    st.subheader("📊 数据模式")
    mode_options = [
        ("mock", "🎯 演示数据（Mock）- 内置示例数据，零成本体验"),
        ("yfinance", "🌐 Yahoo Finance - 完全免费，海外服务器直接可用（推荐云端部署）"),
        ("akshare", "🆓 AKShare 免费数据 - 真实 A 股数据，本地运行最佳"),
        ("tushare", "💎 Tushare 专业数据 - 更全面稳定，需 Token + 积分"),
    ]

    current_mode = get_data_mode()
    mode_idx_map = {"mock": 0, "yfinance": 1, "akshare": 2, "tushare": 3}
    default_idx = mode_idx_map.get(current_mode, 0)

    mode_val = st.radio(
        "选择数据模式",
        options=[m[0] for m in mode_options],
        format_func=lambda x: dict(mode_options)[x],
        index=default_idx,
    )

    if mode_val != current_mode:
        set_data_mode(mode_val)
        st.rerun()

    if mode_val == "tushare" and not has_token():
        st.error("❌ 请先设置 Tushare Token 再切换到专业数据模式")

    # 模式说明
    if mode_val == "mock":
        st.info("💡 **演示模式**：使用内置的模拟数据，可快速体验所有功能。"
                "适合先熟悉工具操作。")
    elif mode_val == "yfinance":
        st.success(
            "💡 **Yahoo Finance 模式**：从雅虎财经获取真实 A 股数据。"
            "完全免费，无需注册，海外服务器（如 Streamlit Cloud）**直接可用、绝对稳定**。"
            "\n\n⚠️ 注意："
            "\n- 合并报表口径（无「归母净利润/净资产」拆分），估值偏差约 5%"
            "\n- 中国大陆本地网络可能无法直接访问 Yahoo，需挂代理"
            "\n- A股代码自动补齐为 `.SS` (沪) / `.SZ` (深)"
        )
    elif mode_val == "akshare":
        st.success("💡 **AKShare 免费模式**：从东方财富、新浪财经等公开网站获取真实 A 股数据。"
                   "完全免费，无需注册。数据最全，但依赖国内数据源，海外服务器可能不稳定。")
    else:
        st.success("💡 **Tushare 专业模式**：从 Tushare 专业接口获取数据，质量高、稳定可靠。"
                   "需要 Token 和积分。")

    # AKShare 数据源诊断（云端排查用）
    if mode_val == "akshare":
        st.markdown("---")
        st.subheader("🔍 数据源诊断")
        st.caption("逐个测试 AKShare 各接口的连通性。云端部署在境外服务器时，"
                   "部分国内数据源可能访问受限，可用此功能定位问题。")
        if st.button("运行诊断（测试 600519 贵州茅台）"):
            # 优先用模块级函数 diagnose_akshare，独立于 AKShareClient 类，
            # 即使云端 .pyc 缓存导致类不完整也能正常调用
            import sys as _sys
            import importlib
            for _name in [
                "quant_valuation.data_sources.akshare_client",
                "quant_valuation.data_sources",
            ]:
                if _name in _sys.modules:
                    try:
                        importlib.reload(_sys.modules[_name])
                    except Exception:
                        pass
            # 直接从 akshare_client 模块 import，绕过 data_sources/__init__.py
            from quant_valuation.data_sources.akshare_client import (
                diagnose_akshare as _diag_fn,
                AKShareClient as _Fresh,
            )

            # 显示环境信息，帮助定位云端版本/网络问题
            col_ver1, col_ver2, col_ver3 = st.columns(3)
            with col_ver1:
                st.metric("工具版本", "v0.6.7")
            with col_ver2:
                st.metric("类完整性",
                          "✅ 完整" if hasattr(_Fresh, "diagnose")
                          else "❌ 不完整")
            with col_ver3:
                try:
                    import akshare as _ak
                    st.metric("akshare 版本", _ak.__version__)
                except Exception:
                    st.metric("akshare 版本", "未安装")

            # 实时进度条 + 当前接口名
            progress = st.progress(0, text="准备中...")
            status_text = st.empty()

            def _progress_cb(idx, total, name):
                progress.progress(idx / total,
                                  text=f"⏳ ({idx}/{total}) {name}")
                status_text.caption(f"正在测试: {name}")

            try:
                diag = _diag_fn(
                    "600519.SH",
                    progress_cb=_progress_cb,
                    timeout_per_call=15.0,
                )
                progress.progress(1.0, text="✅ 诊断完成")

                # 状态着色
                def _highlight(row):
                    color = {
                        "OK": "background: #d4edda; color: #155724",
                        "FAIL": "background: #f8d7da; color: #721c24",
                        "TIMEOUT": "background: #fff3cd; color: #856404",
                    }.get(row["状态"], "")
                    return [color] * len(row)

                st.dataframe(
                    diag.style.apply(_highlight, axis=1),
                    use_container_width=True, hide_index=True,
                )

                # 汇总 + 网络环境判断
                n_ok = (diag["状态"] == "OK").sum()
                n_fail = (diag["状态"].isin(["FAIL", "TIMEOUT"])).sum()
                st.markdown("---")
                if n_ok == 0 and n_fail > 0:
                    st.error(
                        "🌐 **所有接口都无法连通** — "
                        "Streamlit Cloud 美国服务器访问不了东方财富/新浪财经/巨潮等国内数据源。\n\n"
                        "**解决方案**：\n"
                        "1. **本地运行**（推荐）：`pip install -r requirements.txt` 然后 `streamlit run app/main.py`\n"
                        "2. **内网穿透**：用 ngrok / 花生壳 把本地服务暴露到公网\n"
                        "3. **改用 Tushare**（需 Token + 积分）：Tushare 有海外可访问的 API\n"
                    )
                elif n_ok > 0 and n_ok < len(diag) - 1:
                    st.warning(
                        f"⚠️ 部分接口可用（{n_ok} OK / {n_fail} 失败）。"
                        f"失败的可能是东财 push2 接口（网络限流或境外屏蔽），"
                        f"代码有新浪/腾讯回退通道，批量估值仍可工作。"
                    )
                else:
                    st.success("✅ 所有接口连通正常！")

            except Exception as e:
                import traceback as _tb
                progress.progress(0, text="❌ 诊断失败")
                st.error(f"诊断失败: {type(e).__name__}: {e}")
                with st.expander("查看完整堆栈"):
                    st.code(_tb.format_exc())

    st.markdown("---")

    # 积分要求
    with st.expander("📋 Tushare 积分要求说明", expanded=False):
        st.markdown("""
        | 功能 | 所需积分 | 说明 |
        |------|---------|------|
        | 股票基本信息、每日指标 | 0 分 | 注册即可 |
        | 单股估值（利润表/资产负债表/现金流） | 2000 分 | 需要完成个人认证 |
        | 批量估值（多只股票财务） | 2000 分 | 有频率限制 |
        | 行业分类、指数成分股 | 2000+ 分 | |
        | 历史回测（多年财务+行情） | 5000+ 分 | 数据量较大 |

        💡 **提示**：
        - 积分不足时，接口会返回错误提示
        - 可以通过分享推广链接获得积分
        - 也可以直接购买积分包
        - 建议先用演示模式熟悉工具，再考虑升级积分
        """)

    st.markdown("---")

    # 工具信息
    st.subheader("📦 工具信息")
    col1, col2 = st.columns(2)
    with col1:
        st.metric("版本", "v0.6.7")
        st.metric("估值方法", "7 种")
        st.metric("选股策略", "7 种")
    with col2:
        st.metric("调仓频率", "月/季/年")
        st.metric("绩效指标", "20+ 项")
        st.metric("数据源", "2 种")

    # 快捷测试
    st.markdown("---")
    st.subheader("🧪 连接测试")

    if has_token() and st.button("测试 Tushare 连接"):
        with st.spinner("正在测试连接..."):
            try:
                from quant_valuation.data_sources import TushareClient
                client = TushareClient(token=get_token())
                df = client.get_stock_basic("600519.SH")
                if not df.empty:
                    name = df.iloc[0].get("name", "未知")
                    st.success(f"✅ 连接成功！示例：600519.SH = {name}")
                else:
                    st.warning("⚠️ 连接正常但未获取到数据")
            except Exception as e:
                st.error(f"❌ 连接失败: {e}")
