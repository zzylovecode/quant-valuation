"""
Tushare 数据源使用示例
=======================

演示如何通过 Tushare 获取真实财报数据并进行估值分析。

使用前准备：
  1. 注册 Tushare 账号获取 Token: https://tushare.pro/register
  2. 设置 Token（三选一）：
     - 直接传入: builder = TushareDataBuilder(token="你的token")
     - 环境变量: set TUSHARE_TOKEN=你的token
     - 配置文件: 在用户目录创建 .tushare_token 文件

运行方式：
    python example_tushare.py 600519.SH
    python example_tushare.py 000858  (自动识别)
"""

from __future__ import annotations

import sys
import os

from quant_valuation.data_sources import TushareDataBuilder
from quant_valuation import ValuationAnalyzer


def get_token() -> str:
    """获取 Tushare Token，优先从环境变量或命令行参数"""
    # 命令行参数: --token xxx
    if "--token" in sys.argv:
        idx = sys.argv.index("--token")
        if idx + 1 < len(sys.argv):
            return sys.argv[idx + 1]

    # 环境变量
    token = os.environ.get("TUSHARE_TOKEN", "").strip()
    if token:
        return token

    # 交互式输入（仅当直接运行时）
    token = input("请输入你的 Tushare Token: ").strip()
    if token:
        return token

    raise ValueError("未提供 Tushare Token")


def get_target_stock() -> str:
    """从命令行获取目标股票代码"""
    # 找第一个看起来像股票代码的参数
    for arg in sys.argv[1:]:
        if arg.startswith("--"):
            continue
        if len(arg) >= 6:  # 股票代码至少 6 位
            return arg
    return "600519.SH"  # 默认：贵州茅台


def main():
    print("=" * 60)
    print("  Tushare 数据源 + 量化估值 完整演示")
    print("=" * 60)
    print()

    # 1. 获取 Token 和股票代码
    try:
        token = get_token()
    except ValueError as e:
        print(f"错误: {e}")
        print("\n请通过以下方式之一提供 Token：")
        print("  1. 命令行: python example_tushare.py 600519.SH --token 你的token")
        print("  2. 环境变量: set TUSHARE_TOKEN=你的token")
        print("  3. 配置文件: 在用户目录创建 .tushare_token 文件")
        sys.exit(1)

    ts_code = get_target_stock()
    print(f"目标股票: {ts_code}")
    print()

    # 2. 构建数据
    print("→ 正在从 Tushare 获取财务数据...")
    print()
    try:
        builder = TushareDataBuilder(token=token)
        data = builder.build(ts_code, years=5, include_industry=True)
    except Exception as e:
        print(f"\n❌ 获取数据失败: {e}")
        print("\n可能的原因：")
        print("  - Token 无效")
        print("  - 积分不足（部分接口需要 2000+ 积分）")
        print("  - 股票代码不正确")
        print("  - 网络连接问题")
        sys.exit(1)

    print()
    print("✅ 数据获取完成！")
    print()

    # 3. 财务概览
    print(data.summary())
    print()
    print(f"净利润 CAGR (3年): {data.calc_profit_growth_rate(3)*100:.2f}%")
    print(f"营收 CAGR (3年): {data.calc_revenue_growth_rate(3)*100:.2f}%")
    print(f"自由现金流: {data.calc_free_cash_flow():.2f} 亿元")
    print(f"行业平均 PE: {data.industry_pe:.2f}")
    print(f"行业平均 PB: {data.industry_pb:.2f}")
    print()

    # 4. 综合估值
    print("→ 正在执行多方法综合估值...")
    print()

    analyzer = ValuationAnalyzer(data)

    # 估算增长率
    growth_rate = data.calc_profit_growth_rate(3)
    if growth_rate <= 0:
        growth_rate = 0.05  # 默认 5%

    # 根据公司特征选择权重模板
    roe = data.calc_roe()
    if roe > 0.15 and growth_rate > 0.15:
        company_type = "growth"
        type_desc = "成长型（高 ROE + 高增长）"
    elif data.dividend_payout_ratio > 0.4 and growth_rate < 0.08:
        company_type = "mature"
        type_desc = "成熟型（高分红 + 低增长）"
    elif roe < 0.08:
        company_type = "value"
        type_desc = "价值型（低 ROE）"
    else:
        company_type = "growth"
        type_desc = "成长型"

    print(f"公司类型判定: {type_desc}")
    weights = ValuationAnalyzer.get_weights_for_company_type(company_type)

    try:
        report = analyzer.full_valuation(
            weights=weights,
            dcf_params={
                "growth_rate": min(growth_rate, 0.20),  # 不超过 20%
                "high_growth_years": 5,
                "terminal_growth": 0.03,
            },
            relative_params={
                "industry_pe": data.industry_pe if data.industry_pe > 0 else None,
                "industry_pb": data.industry_pb if data.industry_pb > 0 else None,
                "expected_growth": growth_rate,
                "roe_adjusted": True,
            },
            ddm_params={
                "high_growth_rate": min(growth_rate * 0.7, 0.10),
                "high_growth_years": 5,
                "stable_growth_rate": 0.03,
            },
            rim_params={
                "high_growth_years": 5,
                "high_growth_roe": min(roe, 0.25),
                "terminal_roe": 0.10,
            },
            enable_ddm=data.dividend_per_share > 0,
        )

        print()
        print(report.summary())
        print()

        # 5. 安全边际分析
        print("--- 安全边际与估值区间 ---")
        zones = analyzer.value_zone_analysis(report.weighted_value)
        max_price = zones["极度高估区"]
        for zone, price in zones.items():
            bar_len = int((price / max_price) * 36)
            bar = "█" * bar_len
            print(f"  {zone:<10} {price:>8.2f} 元 {bar}")

        # 当前价格位置
        current = data.current_price
        if current < zones["极度低估区"]:
            position = "⭐ 远低于极度低估区（极佳买点）"
        elif current < zones["低估区"]:
            position = "🟢 极度低估区（建议买入）"
        elif current < zones["合理区下限"]:
            position = "🟢 低估区（可分批建仓）"
        elif current < zones["内在价值"]:
            position = "🟡 合理区（偏低，可持有）"
        elif current < zones["合理区上限"]:
            position = "🟡 合理区（偏高，谨慎）"
        elif current < zones["高估区"]:
            position = "🔴 高估区（考虑减仓）"
        elif current < zones["极度高估区"]:
            position = "🔴 高估区（偏高）"
        else:
            position = "🚫 极度高估区（建议卖出）"

        print(f"\n  当前股价 {current:.2f} 元 → {position}")
        print()

        # 6. 安全边际买入价
        for margin in [0.25, 0.30, 0.40]:
            buy_price = analyzer.margin_of_safety(report.weighted_value, margin)
            print(f"  {int(margin*100)}% 安全边际买入价: {buy_price:.2f} 元")
        print()

        # 7. DCF 敏感性分析
        if data.free_cash_flow > 0 or data.operating_cash_flow > 0:
            print("--- DCF (FCFF) 敏感性分析 ---")
            g_min = max(growth_rate - 0.08, 0.02)
            g_max = min(growth_rate + 0.08, 0.25)
            sens_table = analyzer.dcf_sensitivity_table(
                method="FCFF",
                growth_range=(g_min, g_max, 5),
                discount_range=(0.07, 0.12, 5),
                terminal_growth=0.03,
                high_growth_years=5,
            )
            print(sens_table)
            print()

    except Exception as e:
        print(f"\n❌ 估值分析失败: {e}")
        import traceback
        traceback.print_exc()

    print("=" * 60)
    print("  分析完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
