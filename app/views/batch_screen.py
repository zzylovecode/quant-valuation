"""
批量估值排行页面（优化版）
多股票估值结果排行、筛选、搜索、详情展开、导出
"""

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import io

from utils import (
    generate_demo_batch,
    get_token,
    has_token,
    get_data_mode,
    load_batch_from_tushare,
    load_batch_from_akshare,
    load_batch_from_akshare_with_progress,
)
from quant_valuation.batch import BatchValuator, ValuationScreener


@st.cache_data(show_spinner=False)
def get_mock_batch_results(n_stocks: int = 30):
    """获取 Mock 批量估值结果"""
    data_list = generate_demo_batch(n_stocks)
    valuator = BatchValuator(
        company_type="growth",
        verbose=False,
    )
    results = valuator.valuate(data_list)
    return results


@st.cache_data(show_spinner="正在批量估值...", ttl=3600)
def get_tushare_batch_results(token: str, stock_codes: tuple):
    """从 Tushare 获取批量估值结果"""
    data_list = load_batch_from_tushare(token, list(stock_codes))
    valuator = BatchValuator(
        company_type="growth",
        verbose=False,
    )
    results = valuator.valuate(data_list)
    return results


@st.cache_data(show_spinner="正在批量加载并估值（免费数据）...", ttl=0)
def get_akshare_batch_results(stock_codes: tuple, _force: int = 0):
    """从 AKShare 获取批量估值结果（免费）"""
    data_list = load_batch_from_akshare(stock_codes)
    valuator = BatchValuator(
        company_type="growth",
        verbose=False,
    )
    results = valuator.valuate(data_list)
    return results


def _load_akshare_batch_with_progress(stock_codes: tuple, progress_bar):
    """
    带进度条加载 AKShare 批量数据

    Args:
        stock_codes: 股票代码元组
        progress_bar: st.progress 对象
    """
    import sys as _sys
    import importlib

    # 强制 reload 所有相关模块，绕过 data_sources/__init__.py 里
    # 可能残留的旧 AKShareClient 类缓存（云端 Reboot 后第一次运行就 OK）
    for _name in [
        "quant_valuation.data_sources.akshare_client",
        "quant_valuation.data_sources.akshare_builder",
        "quant_valuation.data_sources",
    ]:
        if _name in _sys.modules:
            try:
                importlib.reload(_sys.modules[_name])
            except Exception:
                pass

    # 直接从模块 import，彻底绕过 __init__.py 缓存
    from quant_valuation.data_sources.akshare_builder import AKShareDataBuilder

    builder = AKShareDataBuilder()
    data_list = []
    failed = []
    total = len(stock_codes)

    for i, code in enumerate(stock_codes):
        progress_pct = i / total
        progress_bar.progress(
            progress_pct,
            text=f"⏳ 正在加载 {i+1}/{total}: {code} ..."
        )
        try:
            data = builder.build(code, years=3)
            data_list.append(data)
        except Exception as e:
            import traceback as _tb
            short_msg = f"{type(e).__name__}: {str(e)[:120]}"
            failed.append(f"{code}: {short_msg}\n  {_tb.format_exc().strip()[-300:]}")
            continue

    # 收集客户端记录的接口级错误，便于排查
    client_errors = getattr(builder.client, "errors", {})

    # 完成
    if failed:
        progress_bar.progress(
            1.0,
            text=f"✅ 完成：成功 {len(data_list)} 只，失败 {len(failed)} 只"
        )
    else:
        progress_bar.progress(
            1.0,
            text=f"✅ 完成：成功加载 {len(data_list)} 只股票"
        )

    # 保存失败详情，供界面展示排查
    st.session_state["akshare_load_failures"] = failed[:10]
    st.session_state["akshare_client_errors"] = dict(list(client_errors.items())[:20])

    return data_list


# 预设股票池（按规模分类：精选10只 / 行业20只 / 核心50只）
PRESET_POOLS = {
    # === 精选池（10只，快速体验） ===
    "⭐ 精选10只（各行业龙头）": [
        "600519.SH", "600036.SH", "000333.SZ", "601318.SH",
        "300750.SZ", "002594.SZ", "000858.SZ", "600276.SH",
        "600900.SH", "002415.SZ",
    ],

    # === 行业池（约20只/行业） ===
    "🍷 消费龙头（20只）": [
        "600519.SH", "000858.SZ", "000568.SZ", "600809.SH",
        "600887.SH", "603288.SH", "002714.SZ", "600690.SH",
        "000333.SZ", "000651.SZ", "002508.SZ", "603833.SH",
        "002415.SZ", "300760.SZ", "600276.SH", "300015.SZ",
        "000333.SZ", "600887.SH", "600585.SH", "601012.SH",
    ],

    "🏦 金融龙头（15只）": [
        "600036.SH", "601318.SH", "601398.SH", "601288.SH",
        "601988.SH", "600000.SH", "000001.SZ", "601166.SH",
        "600030.SH", "601628.SH", "601601.SH", "601336.SH",
        "601066.SH", "000776.SZ", "000166.SZ",
    ],

    "🔬 科技成长（20只）": [
        "300750.SZ", "002594.SZ", "600900.SH", "002475.SZ",
        "300059.SZ", "603501.SH", "688981.SH", "300274.SZ",
        "002415.SZ", "002230.SZ", "000977.SZ", "600570.SH",
        "300450.SZ", "002371.SZ", "603259.SH", "300033.SZ",
        "002049.SZ", "600703.SH", "002463.SZ", "300223.SZ",
    ],

    "💊 医药生物（20只）": [
        "600276.SH", "300760.SZ", "300015.SZ", "603259.SH",
        "000538.SZ", "600196.SH", "002007.SZ", "002001.SZ",
        "600436.SH", "300347.SZ", "300142.SZ", "000661.SZ",
        "600511.SH", "002001.SZ", "600867.SH", "002252.SZ",
        "300436.SZ", "300558.SZ", "603392.SH", "002821.SZ",
    ],

    "⚡ 新能源（20只）": [
        "300750.SZ", "002594.SZ", "601012.SH", "300274.SZ",
        "002459.SZ", "600089.SH", "600438.SH", "002129.SZ",
        "300014.SZ", "002709.SZ", "300763.SZ", "603799.SH",
        "002240.SZ", "688599.SH", "300568.SZ", "600522.SH",
        "002074.SZ", "600732.SH", "002531.SZ", "300450.SZ",
    ],

    "💰 高股息龙头（20只）": [
        "601398.SH", "601288.SH", "601988.SH", "600036.SH",
        "601318.SH", "600028.SH", "601857.SH", "600900.SH",
        "601088.SH", "601899.SH", "600585.SH", "600309.SH",
        "601668.SH", "601600.SH", "000895.SZ", "600660.SH",
        "600066.SH", "600985.SH", "000961.SZ", "601225.SH",
    ],

    # === 核心池（50只，较全） ===
    "🏆 沪深300核心（50只）": [
        "600519.SH", "601318.SH", "600036.SH", "000858.SZ",
        "000333.SZ", "300750.SZ", "002594.SZ", "601166.SH",
        "601398.SH", "601288.SH", "601988.SH", "600000.SH",
        "000001.SZ", "600030.SH", "601628.SH", "600276.SH",
        "300760.SZ", "002415.SZ", "600887.SH", "603288.SH",
        "000651.SZ", "600690.SH", "600900.SH", "601012.SH",
        "300274.SZ", "002230.SZ", "300059.SZ", "603501.SH",
        "002475.SZ", "600585.SH", "600309.SH", "601899.SH",
        "002714.SZ", "002007.SZ", "300015.SZ", "603259.SH",
        "000538.SZ", "600196.SH", "600089.SH", "600438.SH",
        "601857.SH", "600028.SH", "601088.SH", "601668.SH",
        "600050.SH", "000002.SZ", "000725.SZ", "000100.SZ",
        "601600.SH", "600741.SH",
    ],
}

# 全市场扫描（从约 5000 只 A 股中按 PE/PB 粗筛，再做完整估值）
MARKET_SCAN_KEY = "🔎 全市场扫描（低估值粗筛）"


@st.cache_data(show_spinner="正在拉取全市场行情快照并粗筛...", ttl=1800)
def get_market_candidates(max_pe: float, max_pb: float, min_mv: float, limit: int):
    """
    从全 A 股快照中按 PE / PB / 市值粗筛低估值候选。

    Returns:
        (codes, preview_rows, errors)
        codes: 候选 ts_code 列表；preview_rows: 展示用明细；errors: 接口错误
    """
    from quant_valuation.data_sources import AKShareClient

    client = AKShareClient()
    snap = client.get_market_snapshot()
    errors = dict(getattr(client, "errors", {}))

    if snap.empty:
        return [], [], errors

    df = snap.copy()
    df["pe"] = pd.to_numeric(df["pe"], errors="coerce")
    df["pb"] = pd.to_numeric(df["pb"], errors="coerce")
    df["total_mv"] = pd.to_numeric(df["total_mv"], errors="coerce")

    total_count = len(df)

    df = df[
        (df["pe"] > 0) & (df["pe"] <= max_pe)
        & (df["pb"] > 0) & (df["pb"] <= max_pb)
        & (df["total_mv"] >= min_mv)
    ].copy()

    if df.empty:
        return [], [{"提示": f"全市场 {total_count} 只中没有符合 PE≤{max_pe} / PB≤{max_pb} / 市值≥{min_mv}亿 的标的"}], errors

    # 综合分：PE 与 PB 分位数越低越好
    df["pe_rank"] = df["pe"].rank(pct=True)
    df["pb_rank"] = df["pb"].rank(pct=True)
    df["score"] = 1 - (df["pe_rank"] + df["pb_rank"]) / 2
    df = df.sort_values("score", ascending=False).head(limit)

    preview = [{
        "代码": r["ts_code"],
        "名称": r["name"],
        "现价": round(float(r["price"]), 2) if pd.notna(r["price"]) else None,
        "PE": round(float(r["pe"]), 1),
        "PB": round(float(r["pb"]), 2),
        "市值(亿)": round(float(r["total_mv"]), 0),
    } for _, r in df.iterrows()]

    return df["ts_code"].tolist(), preview, errors


# 评级颜色配置
RATING_COLORS = {
    "严重低估": {"bg": "#1b5e20", "text": "#ffffff", "emoji": "🟢"},
    "低估":     {"bg": "#66bb6a", "text": "#ffffff", "emoji": "🟢"},
    "合理":     {"bg": "#ffca28", "text": "#5d4037", "emoji": "🟡"},
    "高估":     {"bg": "#ff8a65", "text": "#ffffff", "emoji": "🟠"},
    "严重高估": {"bg": "#c62828", "text": "#ffffff", "emoji": "🔴"},
}


def render_rating_badge(rating: str) -> str:
    """生成评级彩色标签的 HTML"""
    cfg = RATING_COLORS.get(rating, {"bg": "#999", "text": "#fff", "emoji": "⚪"})
    return (
        f'<span style="background-color:{cfg["bg"]};color:{cfg["text"]};'
        f'padding:3px 10px;border-radius:12px;font-size:12px;font-weight:600;'
        f'display:inline-block;text-align:center;min-width:70px;">'
        f'{rating}</span>'
    )


def render_upside_bar(upside: float) -> str:
    """生成涨跌空间进度条 HTML"""
    pct = upside * 100
    # 颜色
    if pct > 30:
        color = "#2e7d32"
        bg = "#e8f5e9"
    elif pct > 10:
        color = "#66bb6a"
        bg = "#f1f8e9"
    elif pct > -10:
        color = "#ffca28"
        bg = "#fff8e1"
    elif pct > -30:
        color = "#ff8a65"
        bg = "#fbe9e7"
    else:
        color = "#c62828"
        bg = "#ffebee"

    # 进度条宽度（限制在 -50% ~ +50% 范围内映射到 0~100%）
    bar_pct = max(0, min(100, (pct + 50)))  # -50→0, 0→50, +50→100

    sign = "+" if pct >= 0 else ""
    return (
        f'<div style="background-color:{bg};border-radius:6px;padding:2px;'
        f'position:relative;height:22px;display:flex;align-items:center;">'
        f'<div style="background-color:{color};height:18px;border-radius:4px;'
        f'width:{bar_pct}%;position:absolute;left:2px;top:2px;"></div>'
        f'<span style="position:relative;z-index:1;color:#333;font-size:12px;'
        f'font-weight:600;width:100%;text-align:center;">{sign}{pct:.1f}%</span>'
        f'</div>'
    )


def render_price_metric(price: float, intrinsic: float) -> str:
    """生成价格对比展示"""
    ratio = price / intrinsic if intrinsic > 0 else 1
    pct_diff = (ratio - 1) * 100
    if ratio < 0.8:
        color = "#2e7d32"
    elif ratio < 1.0:
        color = "#66bb6a"
    elif ratio < 1.2:
        color = "#ffca28"
    else:
        color = "#ef5350"
    return (
        f'<div style="text-align:center;">'
        f'<div style="font-size:16px;font-weight:700;color:#333;">¥{price:.2f}</div>'
        f'<div style="font-size:11px;color:{color};font-weight:600;">'
        f'{"低估" if ratio < 1 else "高估"} {abs(pct_diff):.1f}%</div>'
        f'</div>'
    )


def build_results_dataframe(results: list) -> pd.DataFrame:
    """构建排行榜 DataFrame"""
    table_data = []
    for i, r in enumerate(results, 1):
        table_data.append({
            "排名": i,
            "代码": r.ts_code,
            "名称": r.name,
            "现价": round(r.current_price, 2),
            "内在价值": round(r.intrinsic_value, 2),
            "涨跌空间(%)": round(r.upside_downside * 100, 1),
            "PE": round(r.pe, 1) if r.pe > 0 else None,
            "PB": round(r.pb, 2) if r.pb > 0 else None,
            "ROE(%)": round(r.roe * 100, 1),
            "增速(%)": round(r.profit_growth * 100, 1),
            "市值(亿)": round(r.market_cap, 1),
            "评级": r.rating,
            "评级排序": _rating_sort_key(r.rating),
        })
    return pd.DataFrame(table_data)


def _rating_sort_key(rating: str) -> int:
    """评级排序键：低估在前，高估在后"""
    order = {"严重低估": 0, "低估": 1, "合理": 2, "高估": 3, "严重高估": 4}
    return order.get(rating, 5)


def export_to_csv(results: list) -> bytes:
    """导出为 CSV"""
    df = pd.DataFrame([r.to_dict() for r in results])
    csv_buffer = io.StringIO()
    df.to_csv(csv_buffer, index=False, encoding="utf-8-sig")
    return csv_buffer.getvalue().encode("utf-8-sig")


def render():
    st.title("📋 批量估值排行")
    st.markdown("多股票估值结果与策略筛选")
    st.markdown("---")

    mode = get_data_mode()

    # ========== 顶部：数据源 + 股票池选择 ==========
    col_mode, col_pool, col_custom = st.columns([1, 1, 2])
    with col_mode:
        if mode == "tushare" and has_token():
            st.success("💎 Tushare 专业")
        elif mode == "akshare":
            st.success("🆓 AKShare 免费")
        else:
            st.info("🎯 演示数据")

    is_real_mode = (mode in ("akshare", "yfinance")) or (mode == "tushare" and has_token())

    if is_real_mode:
        with col_pool:
            pool_name = st.selectbox(
                "股票池",
                [MARKET_SCAN_KEY] + list(PRESET_POOLS.keys()) + ["自定义"],
                index=1,
                label_visibility="collapsed",
            )

        if pool_name == MARKET_SCAN_KEY:
            with col_custom:
                st.caption("🔎 先按 PE/PB 从全 A 股粗筛，再逐只做完整估值")
            mf1, mf2, mf3, mf4 = st.columns(4)
            max_pe = mf1.slider("PE 上限", 5.0, 40.0, 20.0, 1.0)
            max_pb = mf2.slider("PB 上限", 0.5, 5.0, 2.0, 0.1)
            min_mv = mf3.slider("市值下限(亿)", 0.0, 500.0, 50.0, 10.0)
            scan_limit = mf4.slider("候选数量", 10, 60, 20, 10)

            scan_codes, scan_preview, scan_errors = get_market_candidates(
                float(max_pe), float(max_pb), float(min_mv), int(scan_limit)
            )
            pool_key = f"scan_{max_pe}_{max_pb}_{min_mv}_{scan_limit}"
            if not scan_codes:
                stock_codes = []
                if scan_errors:
                    st.error("全市场快照获取失败（云端可能限制东财 push2 接口）：")
                    st.code("\n".join(f"{k} → {v}" for k, v in scan_errors.items()),
                            language="text")
                    st.caption("💡 可改用预设股票池；或在本地运行后使用全市场扫描。")
                elif scan_preview:
                    st.warning(scan_preview[0].get("提示", "粗筛无结果，请放宽条件"))
            else:
                stock_codes = scan_codes
                with st.expander(f"📋 粗筛候选明细（{len(stock_codes)} 只，点击展开）",
                                 expanded=False):
                    st.dataframe(pd.DataFrame(scan_preview),
                                 use_container_width=True, hide_index=True)
                    st.caption("💡 粗筛只是缩小范围；点下面「批量加载估值」才会做完整估值并给出低估评级。")
        elif pool_name == "自定义":
            pool_key = "custom"
            with col_custom:
                custom_codes = st.text_area(
                    "自定义代码",
                    height=50,
                    placeholder="每行一个代码，如：600519.SH",
                    label_visibility="collapsed",
                )
            stock_codes = [c.strip() for c in custom_codes.strip().split("\n") if c.strip()]
        else:
            pool_key = pool_name
            stock_codes = PRESET_POOLS[pool_name]
            with col_custom:
                st.caption(f"已选 **{len(stock_codes)}** 只：{', '.join(stock_codes[:5])}...")

        mode_name = {
            "akshare": "AKShare",
            "yfinance": "Yahoo Finance",
            "tushare": "Tushare",
        }.get(mode, "真实数据")
        col_btn1, col_btn2 = st.columns([1, 3])
        with col_btn1:
            if st.button(f"📥 批量加载估值 ({mode_name})", type="primary", disabled=len(stock_codes) < 1):
                st.session_state.force_refresh = True
                for key in list(st.session_state.keys()):
                    if key.startswith("batch_"):
                        del st.session_state[key]
                st.rerun()
        with col_btn2:
            st.caption("💡 数据会自动缓存，点击按钮可强制重新加载")
    else:
        with col_pool:
            n_stocks = st.slider("股票数量", 10, 60, 30, 5, label_visibility="collapsed")
        with col_custom:
            st.caption("💡 演示模式，前往「数据设置」切换为免费真实数据")

    # ========== 获取数据 ==========
    if is_real_mode:
        if stock_codes:
            cache_key = f"batch_{mode}_{pool_key}_{len(stock_codes)}"
            refresh = st.session_state.get("force_refresh", False)

            if not refresh and cache_key in st.session_state:
                results = st.session_state[cache_key]
            elif mode == "yfinance":
                from utils import load_batch_from_yfinance_with_progress
                progress_bar = st.progress(0.0, text="准备加载...")
                try:
                    data_list = load_batch_from_yfinance_with_progress(
                        tuple(stock_codes), progress_bar
                    )
                    if not data_list:
                        st.error("没有成功加载任何股票，下面是具体失败原因：")
                        failures = st.session_state.get("yfinance_load_failures", [])
                        client_errors = st.session_state.get("yfinance_client_errors", {})
                        if failures:
                            st.code("\n".join(failures), language="text")
                        if client_errors:
                            st.markdown("**接口级错误：**")
                            st.code("\n".join(f"{k} → {v}" for k, v in client_errors.items()),
                                    language="text")
                        st.caption(
                            "💡 YFinance 海外服务器一般能连通。如果这里也失败，"
                            "大概率是 yfinance 自身限流，可以稍后重试。"
                        )
                        results = []
                    else:
                        valuator = BatchValuator(company_type="growth", verbose=False)
                        results = valuator.valuate(data_list)
                        st.session_state[cache_key] = results
                except Exception as e:
                    import traceback as _tb
                    st.error(f"加载失败: {type(e).__name__}: {e}")
                    with st.expander("完整堆栈"):
                        st.code(_tb.format_exc())
                    results = []
                finally:
                    st.session_state.force_refresh = False
            elif mode == "akshare":
                progress_bar = st.progress(0.0, text="准备加载...")
                try:
                    data_list = _load_akshare_batch_with_progress(
                        tuple(stock_codes), progress_bar
                    )
                    if not data_list:
                        st.error("没有成功加载任何股票，下面是具体失败原因：")
                        failures = st.session_state.get("akshare_load_failures", [])
                        client_errors = st.session_state.get("akshare_client_errors", {})
                        if failures:
                            st.code("\n".join(failures), language="text")
                        if client_errors:
                            st.markdown("**接口级错误：**")
                            st.code("\n".join(f"{k} → {v}" for k, v in client_errors.items()),
                                    language="text")
                        st.caption("💡 海外服务器请改用 Yahoo Finance 模式，本地运行用 AKShare。")
                        results = []
                    else:
                        valuator = BatchValuator(company_type="growth", verbose=False)
                        results = valuator.valuate(data_list)
                        st.session_state[cache_key] = results
                except Exception as e:
                    st.error(f"加载失败: {e}")
                    results = []
                finally:
                    st.session_state.force_refresh = False
            else:
                # Tushare 模式
                with st.spinner(f"正在加载并估值 {len(stock_codes)} 只股票..."):
                    try:
                        results = get_tushare_batch_results(get_token(), tuple(stock_codes))
                        st.session_state[cache_key] = results
                    except Exception as e:
                        st.error(f"加载失败: {e}")
                        results = []
        else:
            results = []
            st.info("请选择股票池或输入股票代码")
    else:
        with st.spinner("计算中..."):
            results = get_mock_batch_results(n_stocks)

    if not results:
        st.warning("暂无数据")
        return

    # ========== 筛选面板（可折叠） ==========
    with st.expander("🔍 筛选与排序", expanded=True):
        screener = ValuationScreener(results)
        dist = screener.rating_distribution()

        fcol1, fcol2, fcol3, fcol4 = st.columns(4)

        with fcol1:
            strategy = st.selectbox(
                "排序方式",
                ["综合估值上涨空间", "低 PE", "低 PB", "高 ROE", "高增长", "质优价廉得分"],
            )

        with fcol2:
            search = st.text_input("搜索名称/代码", "")

        with fcol3:
            all_ratings = ["严重低估", "低估", "合理", "高估", "严重高估"]
            only_undervalued = st.checkbox(
                "只看低估标的",
                value=True,
                help="勾选后仅显示「严重低估 + 低估」，取消勾选可自行组合评级",
            )
            if only_undervalued:
                rating_filter = ["严重低估", "低估"]
                st.caption("🟢 严重低估（空间 ≥50%）+ 低估（20%~50%）")
            else:
                rating_filter = st.multiselect(
                    "估值评级",
                    all_ratings,
                    default=all_ratings,
                    format_func=lambda x: f"{RATING_COLORS[x]['emoji']} {x}",
                )

        with fcol4:
            upside_range = st.slider(
                "涨跌空间范围",
                -0.8, 1.0, (0.0, 1.0) if only_undervalued else (-0.8, 1.0), 0.05,
                format="%.0f%%",
            )

        pcol1, pcol2, pcol3, pcol4 = st.columns(4)
        with pcol1:
            pe_range = st.slider("PE 范围", 0, 100, (0, 100), 1)
        with pcol2:
            pb_range = st.slider("PB 范围", 0.0, 20.0, (0.0, 20.0), 0.1)
        with pcol3:
            roe_min = st.slider("最低 ROE", -0.2, 0.5, -0.2, 0.01, format="%.0f%%")
        with pcol4:
            growth_min = st.slider("最低增速", -0.5, 0.8, -0.5, 0.02, format="%.0f%%")

    # ========== 执行筛选排序 ==========
    filtered = results

    # 搜索
    if search:
        filtered = [r for r in filtered
                    if search.lower() in r.name.lower()
                    or search.lower() in r.ts_code.lower()]

    # 评级筛选
    if rating_filter and len(rating_filter) < 5:
        filtered = [r for r in filtered if r.rating in rating_filter]

    # 涨跌空间
    filtered = [r for r in filtered
                if upside_range[0] <= r.upside_downside <= upside_range[1]]

    # PE
    filtered = [r for r in filtered
                if pe_range[0] <= r.pe <= pe_range[1] or r.pe <= 0]

    # PB
    filtered = [r for r in filtered
                if pb_range[0] <= r.pb <= pb_range[1] or r.pb <= 0]

    # ROE
    filtered = [r for r in filtered if r.roe >= roe_min]

    # 增速
    filtered = [r for r in filtered if r.profit_growth >= growth_min]

    # 排序
    if strategy == "综合估值上涨空间":
        filtered.sort(key=lambda r: r.upside_downside, reverse=True)
    elif strategy == "低 PE":
        filtered = sorted([r for r in filtered if r.pe > 0], key=lambda r: r.pe)
    elif strategy == "低 PB":
        filtered = sorted([r for r in filtered if r.pb > 0], key=lambda r: r.pb)
    elif strategy == "高 ROE":
        filtered.sort(key=lambda r: r.roe, reverse=True)
    elif strategy == "高增长":
        filtered.sort(key=lambda r: r.profit_growth, reverse=True)
    elif strategy == "质优价廉得分":
        import numpy as np
        if filtered:
            roes = [r.roe for r in filtered]
            upsides = [r.upside_downside for r in filtered]
            roe_std = np.std(roes) or 1
            up_std = np.std(upsides) or 1
            roe_mean = np.mean(roes)
            up_mean = np.mean(upsides)
            scored = []
            for r in filtered:
                score = (r.roe - roe_mean) / roe_std * 0.5 + (r.upside_downside - up_mean) / up_std * 0.5
                scored.append((score, r))
            scored.sort(key=lambda x: x[0], reverse=True)
            filtered = [r for _, r in scored]

    # ========== 统计概览卡片 ==========
    if filtered:
        avg_upside = sum(r.upside_downside for r in filtered) / len(filtered)
        avg_roe = sum(r.roe for r in filtered) / len(filtered)
        avg_pe = sum(r.pe for r in filtered if r.pe > 0) / max(len([r for r in filtered if r.pe > 0]), 1)
        low_count = dist.get("严重低估", 0) + dist.get("低估", 0)
        high_count = dist.get("严重高估", 0) + dist.get("高估", 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric(
            "🎯 筛选后数量",
            f"{len(filtered)} / {len(results)}",
            delta=f"占比 {len(filtered)/len(results)*100:.0f}%",
        )
        c2.metric(
            "📈 平均上涨空间",
            f"{avg_upside*100:+.1f}%",
            delta=f"ROE 均值 {avg_roe*100:.1f}%",
            delta_color="normal" if avg_upside > 0 else "inverse",
        )
        c3.metric(
            "🟢 低估数量",
            f"{dist.get('严重低估', 0) + dist.get('低估', 0)} 只",
            delta=f"严重低估 {dist.get('严重低估', 0)} 只",
            delta_color="normal",
        )
        c4.metric(
            "🔴 高估数量",
            f"{dist.get('严重高估', 0) + dist.get('高估', 0)} 只",
            delta=f"严重高估 {dist.get('严重高估', 0)} 只",
            delta_color="inverse",
        )
    else:
        if only_undervalued and results:
            st.warning(
                "⚠️ 当前股票池没有「低估/严重低估」标的，市场整体估值偏高。"
                "下面按上涨空间从高到低列出最接近低估的前 5 只，供参考："
            )
            top5 = sorted(results, key=lambda r: r.upside_downside, reverse=True)[:5]
            st.dataframe(
                pd.DataFrame([{
                    "代码": r.ts_code,
                    "名称": r.name,
                    "现价": round(r.current_price, 2),
                    "内在价值": round(r.intrinsic_value, 2),
                    "涨跌空间(%)": round(r.upside_downside * 100, 1),
                    "评级": r.rating,
                } for r in top5]),
                use_container_width=True, hide_index=True,
            )
            st.caption("💡 可取消「只看低估标的」查看全部评级，或换个股票池再试。")
        else:
            st.warning("⚠️ 筛选后没有符合条件的股票，请调整筛选条件")
        return

    st.markdown("---")

    # ========== 图表区 ==========
    chart_col1, chart_col2, chart_col3 = st.columns([2, 1, 1])

    with chart_col1:
        st.subheader("🎯 PE-ROE 估值散点图")
        df_plot = pd.DataFrame([{
            "名称": r.name,
            "PE": round(r.pe, 1),
            "ROE(%)": round(r.roe * 100, 1),
            "涨跌空间(%)": round(r.upside_downside * 100, 1),
            "市值(亿)": round(r.market_cap, 1),
            "评级": r.rating,
        } for r in filtered if r.pe > 0 and r.pe < 100])

        if not df_plot.empty:
            fig = px.scatter(
                df_plot, x="PE", y="ROE(%)",
                size="市值(亿)", color="涨跌空间(%)",
                hover_name="名称",
                hover_data={"PE": True, "ROE(%)": True, "涨跌空间(%)": True, "评级": True, "市值(亿)": True},
                color_continuous_scale="RdYlGn_r",  # 反向：绿色（正空间）在右边，红色在左边
                size_max=30,
            )
            fig.update_layout(
                height=380,
                margin=dict(l=10, r=10, t=10, b=10),
                coloraxis_colorbar=dict(title="涨跌空间(%)"),
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("暂无数据")

    with chart_col2:
        st.subheader("📊 评级分布")
        ratings = ["严重低估", "低估", "合理", "高估", "严重高估"]
        counts = [dist.get(r, 0) for r in ratings]
        colors = ["#1b5e20", "#66bb6a", "#ffca28", "#ff8a65", "#c62828"]

        fig = go.Figure(data=[go.Pie(
            labels=ratings, values=counts,
            marker_colors=colors,
            hole=0.6,
            textinfo="value+percent",
            textfont_size=12,
        )])
        fig.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
            showlegend=True,
            legend=dict(orientation="h", yanchor="bottom", y=-0.1),
        )
        st.plotly_chart(fig, use_container_width=True)

    with chart_col3:
        st.subheader("📉 涨跌空间分布")
        upside_values = [r.upside_downside * 100 for r in filtered]
        fig = go.Figure(data=[go.Histogram(
            x=upside_values,
            nbinsx=15,
            marker_color="#42a5f5",
            marker_line_color="#1565c0",
            marker_line_width=1,
        )])
        fig.add_vline(x=0, line_dash="dash", line_color="red", line_width=2,
                      annotation_text="现价", annotation_position="top right")
        fig.update_layout(
            height=380,
            margin=dict(l=10, r=10, t=10, b=10),
            xaxis_title="涨跌空间(%)",
            yaxis_title="股票数量",
            bargap=0.1,
        )
        st.plotly_chart(fig, use_container_width=True)

    st.markdown("---")

    # ========== 排行榜 ==========
    list_header_col1, list_header_col2, list_header_col3 = st.columns([2, 1, 1])
    with list_header_col1:
        st.subheader("🏆 估值排行榜")
    with list_header_col2:
        st.caption(f"显示 {len(filtered)} 只股票")
    with list_header_col3:
        # 导出按钮
        csv_data = export_to_csv(filtered)
        st.download_button(
            "📥 导出 CSV",
            data=csv_data,
            file_name="valuation_rankings.csv",
            mime="text/csv",
            use_container_width=True,
        )

    # 构建展示用的 DataFrame（带 HTML 格式）
    display_rows = []
    for i, r in enumerate(filtered, 1):
        # 估值区间
        range_str = f"¥{r.low_value:.0f} ~ ¥{r.high_value:.0f}"

        display_rows.append({
            "排名": f'<div style="text-align:center;font-weight:700;color:#666;">#{i}</div>',
            "名称": f'<div style="font-weight:600;">{r.name}</div>'
                    f'<div style="font-size:11px;color:#999;">{r.ts_code}</div>',
            "现价(元)": f'<div style="text-align:right;font-weight:600;">¥{r.current_price:.2f}</div>',
            "内在价值(元)": f'<div style="text-align:right;font-weight:600;color:#1565c0;">¥{r.intrinsic_value:.2f}</div>'
                          f'<div style="font-size:11px;color:#999;text-align:right;">{range_str}</div>',
            "涨跌空间": render_upside_bar(r.upside_downside),
            "PE": f'<div style="text-align:center;">{r.pe:.1f}x</div>' if r.pe > 0 else '<div style="text-align:center;color:#ccc;">-</div>',
            "PB": f'<div style="text-align:center;">{r.pb:.2f}x</div>' if r.pb > 0 else '<div style="text-align:center;color:#ccc;">-</div>',
            "ROE": f'<div style="text-align:center;font-weight:600;">{r.roe*100:.1f}%</div>',
            "增速": f'<div style="text-align:center;color:{"#2e7d32" if r.profit_growth >= 0 else "#c62828"};">{r.profit_growth*100:+.1f}%</div>',
            "市值(亿)": f'<div style="text-align:right;">{r.market_cap:.0f}</div>',
            "评级": f'<div style="text-align:center;">{render_rating_badge(r.rating)}</div>',
        })

    display_df = pd.DataFrame(display_rows)

    # 使用 HTML 表格展示（更美观）
    html_table = _build_html_table(display_df)
    st.components.v1.html(html_table, height=520, scrolling=True)

    # ========== 详情展开 ==========
    st.markdown("---")
    st.subheader("🔍 个股估值详情")

    # 选择股票
    stock_names = [f"{r.name} ({r.ts_code})" for r in filtered]
    if stock_names:
        selected_idx = st.selectbox(
            "选择股票查看详细估值",
            range(len(stock_names)),
            format_func=lambda i: stock_names[i],
        )
        selected = filtered[selected_idx]
        _render_stock_detail(selected)


def _build_html_table(df: pd.DataFrame) -> str:
    """构建美观的 HTML 表格"""
    columns = df.columns.tolist()
    html = """
    <style>
        .rank-table-wrap { width: 100%; overflow-x: auto; -webkit-overflow-scrolling: touch; }
        .rank-table { width: 100%; min-width: 900px; border-collapse: collapse; font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; font-size: 13px; }
        .rank-table thead th {
            position: sticky; top: 0; z-index: 10;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white; padding: 10px 8px; font-weight: 600;
            text-align: center; border: none;
            white-space: nowrap;
        }
        .rank-table tbody tr { border-bottom: 1px solid #eef1f6; transition: background 0.2s; }
        .rank-table tbody tr:hover { background-color: #f5f7fa; }
        .rank-table tbody td { padding: 8px 6px; border: none; }
        .rank-table tbody tr:nth-child(odd) { background-color: #fafbfc; }
        .rank-table tbody tr:nth-child(odd):hover { background-color: #f0f4f8; }
        @media (max-width: 768px) {
            .rank-table { font-size: 12px; min-width: 860px; }
            .rank-table thead th { padding: 8px 6px; }
            .rank-table tbody td { padding: 6px 5px; }
        }
    </style>
    <div class="rank-table-wrap">
    <table class="rank-table">
        <thead><tr>
    """
    for col in columns:
        html += f"<th>{col}</th>"
    html += "</tr></thead><tbody>"

    for _, row in df.iterrows():
        html += "<tr>"
        for col in columns:
            html += f"<td>{row[col]}</td>"
        html += "</tr>"

    html += "</tbody></table></div>"
    return html


def _render_stock_detail(r):
    """渲染个股估值详情"""
    st.markdown(f"### {r.name}（{r.ts_code}）")

    # 关键指标卡片
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("当前价格", f"¥{r.current_price:.2f}")
    c2.metric("内在价值", f"¥{r.intrinsic_value:.2f}")
    c3.metric("上涨空间", f"{r.upside_downside*100:+.1f}%",
              delta=r.rating, delta_color="off")
    c4.metric("PE", f"{r.pe:.1f}x" if r.pe > 0 else "N/A")
    c5.metric("ROE", f"{r.roe*100:.1f}%")

    st.markdown("#### 📊 各方法估值对比")

    # 各方法估值柱状图
    methods = list(r.method_values.keys())
    values = [r.method_values[m] for m in methods]
    upsides = [r.method_upsides.get(m, 0) * 100 for m in methods]

    colors = []
    for u in upsides:
        if u > 30:
            colors.append("#2e7d32")
        elif u > 10:
            colors.append("#66bb6a")
        elif u > -10:
            colors.append("#ffca28")
        elif u > -30:
            colors.append("#ff8a65")
        else:
            colors.append("#c62828")

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=methods, y=values,
        marker_color=colors,
        text=[f"¥{v:.0f}<br>{u:+.1f}%" for v, u in zip(values, upsides)],
        textposition="outside",
        textfont=dict(size=11, color="#333"),
    ))
    # 当前价格参考线
    fig.add_hline(y=r.current_price, line_dash="dash", line_color="#1565c0", line_width=2,
                  annotation_text=f"现价 ¥{r.current_price:.2f}",
                  annotation_position="top right")
    fig.update_layout(
        height=350,
        margin=dict(l=10, r=10, t=10, b=10),
        yaxis_title="估值 (元)",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True)

    # 估值区间
    col_low, col_med, col_high = st.columns(3)
    col_low.metric("保守估值", f"¥{r.low_value:.2f}",
                   delta=f"{(r.low_value/r.current_price-1)*100:+.1f}%",
                   delta_color="normal")
    col_med.metric("中位估值", f"¥{r.median_value:.2f}",
                   delta=f"{(r.median_value/r.current_price-1)*100:+.1f}%",
                   delta_color="normal")
    col_high.metric("乐观估值", f"¥{r.high_value:.2f}",
                    delta=f"{(r.high_value/r.current_price-1)*100:+.1f}%",
                    delta_color="normal")
