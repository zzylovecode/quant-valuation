"""
界面工具函数
===========
提供页面间共享的辅助函数和默认数据。
"""

from __future__ import annotations

import random
from typing import Dict, List

import pandas as pd
import streamlit as st

from quant_valuation import FinancialData, ValuationAnalyzer
from quant_valuation.batch import BatchValuator
from quant_valuation.backtest import (
    BacktestEngine,
    MockDataProvider,
    ValueStrategy,
    QualityValueStrategy,
    GARPStrategy,
    DeepValueStrategy,
    LowPEStrategy,
    LowPBStrategy,
    CompositeScoreStrategy,
)


def get_default_stock() -> FinancialData:
    """获取默认演示股票数据"""
    random.seed(42)
    data = FinancialData(
        ticker="600519.SH",
        name="贵州茅台（示例）",
        total_shares=12.56,
        current_price=1680.0,
        revenue=1265.0,
        net_profit=727.0,
        operating_profit=912.0,
        ebit=920.0,
        ebitda=980.0,
        eps=57.88,
        total_assets=2500.0,
        total_equity=1800.0,
        cash=600.0,
        interest_bearing_debt=50.0,
        net_debt=-550.0,
        bvps=143.32,
        operating_cash_flow=680.0,
        capex=80.0,
        free_cash_flow=600.0,
        dividend_per_share=25.0,
        dividend_payout_ratio=0.43,
        historical_net_profit=[412, 467, 525, 627, 727],
        historical_revenue=[889, 980, 1095, 1241, 1265],
        industry_pe=28.0,
        industry_pb=8.5,
    )
    return data


def generate_demo_batch(n: int = 30) -> List[FinancialData]:
    """生成批量演示数据"""
    random.seed(123)
    names = [
        "贵州茅台", "五粮液", "泸州老窖", "洋河股份", "山西汾酒",
        "宁德时代", "比亚迪", "隆基绿能", "通威股份", "阳光电源",
        "招商银行", "兴业银行", "平安银行", "工商银行", "建设银行",
        "恒瑞医药", "药明康德", "迈瑞医疗", "爱尔眼科", "片仔癀",
        "海康威视", "立讯精密", "韦尔股份", "兆易创新", "北方华创",
        "美的集团", "格力电器", "海尔智家", "三花智控", "苏泊尔",
    ]
    codes = [f"600{i+1:03d}.SH" if i < 15 else f"000{i-14:03d}.SZ" for i in range(n)]

    data_list = []
    for i in range(n):
        style = i % 6  # 不同风格
        price = random.uniform(20, 300)
        pe = [15, 25, 35, 18, 8, 50][style] + random.uniform(-5, 10)
        pb = [3, 5, 8, 1.5, 0.8, 10][style] + random.uniform(-1, 3)
        roe = [0.18, 0.22, 0.15, 0.12, 0.06, 0.20][style] + random.uniform(-0.05, 0.05)
        growth = [0.15, 0.25, 0.30, 0.08, 0.02, 0.35][style] + random.uniform(-0.05, 0.1)
        total_shares = random.uniform(5, 100)
        eps = price / pe
        bvps = price / pb
        net_profit = eps * total_shares
        revenue = net_profit / random.uniform(0.08, 0.25)
        total_equity = bvps * total_shares
        ocf = net_profit * random.uniform(0.9, 1.3)
        capex = ocf * random.uniform(0.15, 0.4)

        # 历史数据
        hist_profit = []
        p = net_profit
        for _ in range(5):
            hist_profit.append(round(p, 2))
            p /= (1 + growth)
        hist_profit.reverse()

        hist_rev = []
        r = revenue
        for _ in range(5):
            hist_rev.append(round(r, 2))
            r /= (1 + growth * 0.8)
        hist_rev.reverse()

        data = FinancialData(
            ticker=codes[i],
            name=names[i] if i < len(names) else f"股票{i+1}",
            total_shares=round(total_shares, 2),
            current_price=round(price, 2),
            revenue=round(revenue, 2),
            net_profit=round(net_profit, 2),
            operating_profit=round(net_profit * 1.3, 2),
            ebit=round(net_profit * 1.4, 2),
            ebitda=round(net_profit * 1.7, 2),
            eps=round(eps, 2),
            total_assets=round(total_equity * random.uniform(1.5, 3), 2),
            total_equity=round(total_equity, 2),
            cash=round(total_equity * 0.2, 2),
            interest_bearing_debt=round(total_equity * 0.15, 2),
            bvps=round(bvps, 2),
            operating_cash_flow=round(ocf, 2),
            capex=round(capex, 2),
            free_cash_flow=round(ocf - capex, 2),
            dividend_per_share=round(eps * random.uniform(0.2, 0.5), 2),
            dividend_payout_ratio=round(random.uniform(0.2, 0.5), 2),
            historical_net_profit=hist_profit,
            historical_revenue=hist_rev,
            industry_pe=round(pe * random.uniform(0.8, 1.2), 2),
            industry_pb=round(pb * random.uniform(0.8, 1.2), 2),
        )
        data_list.append(data)

    return data_list


def format_pct(value: float, decimals: int = 2) -> str:
    """格式化百分比"""
    return f"{value * 100:.{decimals}f}%"


def valuation_gauge_color(upside: float) -> str:
    """根据涨跌空间返回颜色"""
    if upside >= 0.30:
        return "#28a745"  # 绿 - 严重低估
    elif upside >= 0.10:
        return "#95d5b2"  # 浅绿
    elif upside >= -0.10:
        return "#ffc107"  # 黄 - 合理
    elif upside >= -0.30:
        return "#f8961e"  # 橙
    else:
        return "#dc3545"  # 红 - 严重高估


def render_metric_card(label: str, value: str, sublabel: str = "", card_type: str = ""):
    """渲染指标卡片"""
    color_class = card_type
    st.markdown(
        f"""
        <div class="metric-card {color_class}">
            <div style="font-size: 0.85rem; color: #666;">{label}</div>
            <div style="font-size: 1.5rem; font-weight: bold; margin: 5px 0;">{value}</div>
            {f'<div style="font-size: 0.8rem; color: #888;">{sublabel}</div>' if sublabel else ''}
        </div>
        """,
        unsafe_allow_html=True,
    )


def run_valuation(data: FinancialData, company_type: str = "growth") -> dict:
    """执行估值并返回结果字典"""
    analyzer = ValuationAnalyzer(data)
    weights = ValuationAnalyzer.get_weights_for_company_type(company_type)
    growth_rate = data.calc_profit_growth_rate(3)

    report = analyzer.full_valuation(
        weights=weights,
        dcf_params={
            "growth_rate": min(max(growth_rate, 0.03), 0.25),
            "high_growth_years": 5,
            "terminal_growth": 0.03,
        },
        relative_params={
            "industry_pe": data.industry_pe if data.industry_pe > 0 else None,
            "industry_pb": data.industry_pb if data.industry_pb > 0 else None,
            "expected_growth": growth_rate,
            "roe_adjusted": True,
        },
    )

    return {
        "report": report,
        "analyzer": analyzer,
        "growth_rate": growth_rate,
    }


# ============================================================
# Tushare 数据加载工具
# ============================================================

def get_token() -> str:
    """获取当前 Tushare Token（优先 session_state，其次 secrets，最后环境变量）"""
    if "tushare_token" in st.session_state and st.session_state.tushare_token:
        return st.session_state.tushare_token
    try:
        if "TUSHARE_TOKEN" in st.secrets:
            return st.secrets["TUSHARE_TOKEN"]
    except Exception:
        pass
    import os
    return os.environ.get("TUSHARE_TOKEN", "")


def set_token(token: str):
    """设置 Tushare Token 到 session_state"""
    st.session_state.tushare_token = token.strip() if token else ""


def has_token() -> bool:
    """是否有有效 Token"""
    return bool(get_token())


def get_data_mode() -> str:
    """获取当前数据模式：mock / akshare / tushare"""
    return st.session_state.get("data_mode", "mock")


def set_data_mode(mode: str):
    """设置数据模式"""
    st.session_state.data_mode = mode


# ============================================================
# AKShare 数据加载工具（免费）
# ============================================================

@st.cache_data(show_spinner="正在从 AKShare 拉取数据...", ttl=3600)
def load_stock_from_akshare(ts_code: str) -> FinancialData:
    """
    从 AKShare 加载单只股票数据（带缓存，完全免费）

    Args:
        ts_code: 股票代码（Tushare 格式，如 600519.SH）

    Returns:
        FinancialData 对象
    """
    from quant_valuation.data_sources import AKShareDataBuilder

    builder = AKShareDataBuilder()
    data = builder.build(ts_code, years=5)
    return data


@st.cache_data(show_spinner=False, ttl=3600)
def load_batch_from_akshare(stock_codes: tuple) -> List[FinancialData]:
    """
    从 AKShare 批量加载股票数据（带缓存，无进度条版本）
    """
    from quant_valuation.data_sources import AKShareDataBuilder

    builder = AKShareDataBuilder()
    data_list = []
    for code in stock_codes:
        try:
            data = builder.build(code, years=3)
            data_list.append(data)
        except Exception as e:
            continue
    return data_list


def load_batch_from_akshare_with_progress(stock_codes: tuple, progress_bar=None, status_text=None) -> List[FinancialData]:
    """
    从 AKShare 批量加载股票数据（带进度条版本，不缓存）

    Args:
        stock_codes: 股票代码元组
        progress_bar: st.progress 对象
        status_text: st.empty 对象用于显示状态文字
    """
    from quant_valuation.data_sources import AKShareDataBuilder

    builder = AKShareDataBuilder()
    data_list = []
    failed = []
    total = len(stock_codes)

    for i, code in enumerate(stock_codes, 1):
        try:
            if status_text:
                status_text.text(f"⏳ 正在加载 {i}/{total}: {code} ...")
            data = builder.build(code, years=3)
            data_list.append(data)
        except Exception as e:
            failed.append(f"{code}: {str(e)[:50]}")
            continue
        if progress_bar:
            progress_bar.progress(i / total)

    if status_text:
        if failed:
            status_text.text(f"✅ 完成：成功 {len(data_list)} 只，失败 {len(failed)} 只")
        else:
            status_text.text(f"✅ 完成：成功加载 {len(data_list)} 只股票")

    return data_list


@st.cache_data(show_spinner="正在从 Tushare 拉取数据...", ttl=3600)
def load_stock_from_tushare(token: str, ts_code: str) -> FinancialData:
    """
    从 Tushare 加载单只股票数据（带缓存）

    Args:
        token: Tushare Token
        ts_code: 股票代码

    Returns:
        FinancialData 对象
    """
    from quant_valuation.data_sources import TushareDataBuilder

    builder = TushareDataBuilder(token=token)
    data = builder.build(ts_code, years=5, include_industry=False)
    return data


@st.cache_data(show_spinner="正在批量拉取 Tushare 数据...", ttl=3600)
def load_batch_from_tushare(token: str, stock_codes: List[str]) -> List[FinancialData]:
    """
    从 Tushare 批量加载股票数据（带缓存）
    """
    from quant_valuation.batch import BatchDataFetcher
    from quant_valuation.data_sources import TushareClient

    client = TushareClient(token=token)
    fetcher = BatchDataFetcher(client=client, years=5, verbose=False)
    data_list = fetcher.fetch_list(stock_codes)
    return data_list


def load_stock_smart(ts_code: str = "") -> FinancialData:
    """
    智能加载股票数据：
    - akshare 模式 → 从 AKShare 加载（免费）
    - tushare 模式且有 Token → 从 Tushare 加载
    - 否则 → 返回默认演示数据
    """
    mode = get_data_mode()
    token = get_token()

    if mode == "akshare" and ts_code:
        try:
            return load_stock_from_akshare(ts_code)
        except Exception as e:
            st.warning(f"AKShare 数据加载失败: {e}，已切换到演示数据")
            set_data_mode("mock")
    elif mode == "tushare" and token and ts_code:
        try:
            return load_stock_from_tushare(token, ts_code)
        except Exception as e:
            st.warning(f"Tushare 数据加载失败: {e}，已切换到演示数据")
            set_data_mode("mock")

    return get_default_stock()


def get_stock_name_smart(ts_code: str = "") -> str:
    """获取股票名称（智能）"""
    mode = get_data_mode()
    if mode == "akshare" and ts_code:
        try:
            data = load_stock_from_akshare(ts_code)
            return data.name
        except Exception:
            pass
    elif mode == "tushare" and has_token() and ts_code:
        try:
            data = load_stock_from_tushare(get_token(), ts_code)
            return data.name
        except Exception:
            pass
    return get_default_stock().name
