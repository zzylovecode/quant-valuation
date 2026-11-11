"""
批量估值使用示例
=================

演示批量估值、筛选排序、结果导出的完整流程。

包含两种模式：
  1. demo 模式：用模拟数据演示功能（不需要 Tushare Token）
  2. real 模式：用 Tushare 真实数据（需要 Token）

运行方式：
    # 演示模式（推荐先运行这个看效果）
    python example_batch.py

    # 真实 Tushare 数据模式
    python example_batch.py --mode real --token 你的token
    python example_batch.py --mode real --stock 600519.SH,000858.SZ,601318.SH
"""

from __future__ import annotations

import os
import sys
import random

# 确保能导入
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from quant_valuation import FinancialData, ValuationAnalyzer
from quant_valuation.batch import (
    BatchDataFetcher,
    BatchValuator,
    ValuationScreener,
    ResultExporter,
)


def generate_mock_stock_list(count: int = 30) -> list:
    """
    生成模拟股票列表（演示用）

    模拟一批消费/科技/金融行业的公司，参数有合理分布。
    """
    random.seed(42)  # 固定种子确保可复现

    name_pool = [
        "科技龙头", "智造先锋", "消费白马", "医药王者", "新能源龙头",
        "银行巨头", "地产蓝筹", "食品饮料", "家电龙头", "汽车新势力",
        "半导体", "云计算", "生物医药", "医疗器械", "白酒龙头",
        "调味品王", "乳业龙头", "零售巨头", "电商平台", "软件服务",
        "通信设备", "化工龙头", "钢铁巨头", "有色金属", "煤炭能源",
        "电力公司", "水务环保", "建材龙头", "机械重工", "航空运输",
    ]

    data_list = []
    for i in range(count):
        # 随机生成参数，有一定分布
        base_price = random.uniform(10, 200)
        pe = random.uniform(8, 60)
        pb = random.uniform(0.8, 10)
        roe = random.uniform(0.05, 0.25)
        growth = random.uniform(-0.05, 0.30)
        payout = random.uniform(0.1, 0.6)
        size_factor = random.uniform(0.5, 5)  # 规模因子

        total_shares = round(random.uniform(5, 200), 2)  # 亿股
        eps = round(base_price / pe, 3)
        bvps = round(base_price / pb, 3)
        net_profit = round(eps * total_shares, 2)
        revenue = round(net_profit / random.uniform(0.05, 0.20), 2)
        total_equity = round(bvps * total_shares, 2)

        # 历史 5 年净利润（按增长率生成）
        historical = []
        current_profit = net_profit
        for _ in range(5):
            historical.append(round(current_profit, 2))
            current_profit /= (1 + growth)
        historical.reverse()

        # 历史营收
        hist_rev = []
        current_rev = revenue
        for _ in range(5):
            hist_rev.append(round(current_rev, 2))
            current_rev /= (1 + growth * 0.8)
        hist_rev.reverse()

        ocf = round(net_profit * random.uniform(0.8, 1.5), 2)
        capex = round(ocf * random.uniform(0.2, 0.6), 2)

        code = f"600{i+1:03d}.SH" if i < 15 else f"000{i-14:03d}.SZ"

        data = FinancialData(
            ticker=code,
            name=name_pool[i % len(name_pool)] + str(i + 1),
            total_shares=total_shares,
            current_price=round(base_price, 2),
            revenue=revenue,
            net_profit=net_profit,
            operating_profit=round(net_profit * 1.3, 2),
            ebit=round(net_profit * 1.4, 2),
            ebitda=round(net_profit * 1.8, 2),
            eps=eps,
            total_assets=round(total_equity * random.uniform(1.5, 4), 2),
            total_equity=total_equity,
            cash=round(total_equity * random.uniform(0.1, 0.4), 2),
            interest_bearing_debt=round(total_equity * random.uniform(0.05, 0.5), 2),
            net_debt=0.0,  # 后面自动算
            bvps=bvps,
            operating_cash_flow=ocf,
            capex=capex,
            free_cash_flow=ocf - capex,
            dividend_per_share=round(eps * payout, 3),
            dividend_payout_ratio=payout,
            historical_net_profit=historical,
            historical_revenue=hist_rev,
            industry_pe=round(pe * random.uniform(0.7, 1.3), 2),
            industry_pb=round(pb * random.uniform(0.7, 1.3), 2),
        )
        data.net_debt = data.calc_net_debt(force=True)
        data_list.append(data)

    return data_list


def run_demo():
    """演示模式：用模拟数据展示完整功能"""
    print("=" * 70)
    print("  批量估值功能演示（模拟数据，无需 Token）")
    print("=" * 70)
    print()

    # 1. 生成模拟数据
    print("→ 生成 30 只模拟股票数据...")
    data_list = generate_mock_stock_list(30)
    print(f"  已生成 {len(data_list)} 只股票\n")

    # 2. 批量估值
    print("→ 执行批量估值...")
    valuator = BatchValuator(
        company_type="growth",
        dcf_years=5,
        terminal_growth=0.03,
        verbose=True,
    )
    results = valuator.valuate(data_list)
    print()

    # 3. 生成完整报告
    print("→ 生成估值报告...\n")
    exporter = ResultExporter(results)
    report = exporter.generate_report(
        title="批量估值分析报告",
        subtitle="模拟 30 只股票 · 综合 7 种估值方法",
        show_top_undervalued=15,
        show_top_overvalued=10,
    )
    print(report)
    print()

    # 4. 各种筛选策略
    screener = ValuationScreener(results)

    print("=" * 70)
    print("  各种选股策略筛选")
    print("=" * 70)
    print()

    # 质优价廉
    print("【策略 1】质优价廉（ROE ≥ 15% + 上涨空间 ≥ 15% + 净利润 ≥ 5亿）")
    quality = screener.quality_value(min_roe=0.15, min_upside=0.15, min_profit=5.0, limit=10)
    print(exporter._compact_table(quality))
    print(f"  共 {len(quality)} 只符合条件\n")

    # GARP 成长合理价
    print("【策略 2】GARP 合理价格成长股（增速 ≥ 15% + 估值合理）")
    garp = screener.growth_at_reasonable_price(min_growth=0.15, limit=10)
    print(exporter._compact_table(garp))
    print(f"  共 {len(garp)} 只符合条件\n")

    # 深度价值
    print("【策略 3】深度价值（PE ≤ 15 + PB ≤ 2 + ROE ≥ 8%）")
    deep = screener.deep_value(max_pe=15, max_pb=2, min_roe=0.08, limit=10)
    print(exporter._compact_table(deep))
    print(f"  共 {len(deep)} 只符合条件\n")

    # 低 PE 榜
    print("【榜单】PE 最低 Top 10（正值）")
    low_pe = screener.lowest_pe(10)
    print(exporter._compact_table(low_pe))
    print()

    # 高 ROE 榜
    print("【榜单】ROE 最高 Top 10")
    top_roe = screener.top_by_roe(10)
    print(exporter._compact_table(top_roe))
    print()

    # 5. 导出 CSV
    csv_path = os.path.join(os.path.dirname(__file__), "batch_valuation_demo.csv")
    exporter.to_csv(csv_path)
    print(f"✅ 结果已导出到: {csv_path}")
    print()

    # 6. 涨跌空间分布
    dist = screener.upside_distribution()
    print("【涨跌空间分布】")
    total = len(results)
    for label, count in dist.items():
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        print(f"  {label:<6} {count:>3} 只 ({pct:>5.1f}%) {bar}")
    print()

    print("=" * 70)
    print("  演示完成！")
    print("=" * 70)


def run_real_mode(token: str, stock_codes: list):
    """真实 Tushare 数据模式"""
    print("=" * 70)
    print("  批量估值（真实 Tushare 数据）")
    print("=" * 70)
    print()

    # 1. 批量获取数据
    print("→ 从 Tushare 获取财务数据...\n")
    fetcher = BatchDataFetcher(token=token, years=5, verbose=True)
    data_list = fetcher.fetch_list(stock_codes)

    if not data_list:
        print("\n❌ 未获取到任何数据，请检查 Token 和股票代码")
        return

    print(f"\n成功获取 {len(data_list)} 只股票数据\n")

    # 2. 批量估值
    print("→ 执行批量估值...\n")
    valuator = BatchValuator(
        company_type="growth",
        dcf_years=5,
        terminal_growth=0.03,
        verbose=True,
    )
    results = valuator.valuate(data_list)
    print()

    # 3. 生成报告
    exporter = ResultExporter(results)
    report = exporter.generate_report(
        title="股票池估值分析报告",
        subtitle=f"共 {len(results)} 只股票 · 综合多方法估值",
        show_top_undervalued=min(20, len(results)),
        show_top_overvalued=min(10, len(results)),
    )
    print(report)
    print()

    # 4. 导出
    csv_path = os.path.join(os.path.dirname(__file__), "batch_valuation_results.csv")
    exporter.to_csv(csv_path)
    print(f"✅ CSV 结果已导出: {csv_path}")

    try:
        excel_path = os.path.join(os.path.dirname(__file__), "batch_valuation_results.xlsx")
        exporter.to_excel(excel_path)
        print(f"✅ Excel 结果已导出: {excel_path}")
    except Exception as e:
        print(f"  Excel 导出跳过（{e}）")

    print()


def parse_args():
    """简单的命令行参数解析"""
    args = {"mode": "demo", "token": "", "stocks": []}

    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--mode" and i + 1 < len(sys.argv):
            args["mode"] = sys.argv[i + 1]
            i += 2
        elif arg == "--token" and i + 1 < len(sys.argv):
            args["token"] = sys.argv[i + 1]
            i += 2
        elif arg == "--stock" and i + 1 < len(sys.argv):
            args["stocks"] = [s.strip() for s in sys.argv[i + 1].split(",")]
            i += 2
        else:
            i += 1

    # 环境变量 token
    if not args["token"]:
        args["token"] = os.environ.get("TUSHARE_TOKEN", "")

    return args


def main():
    args = parse_args()

    if args["mode"] == "demo":
        run_demo()
    elif args["mode"] == "real":
        if not args["token"]:
            print("❌ 真实模式需要 Tushare Token")
            print("  使用 --token 参数或设置 TUSHARE_TOKEN 环境变量")
            sys.exit(1)
        if not args["stocks"]:
            print("❌ 请提供股票代码，如：--stock 600519.SH,000858.SZ")
            sys.exit(1)
        run_real_mode(args["token"], args["stocks"])
    else:
        print(f"未知模式: {args['mode']}")
        print("支持: demo / real")
        sys.exit(1)


if __name__ == "__main__":
    main()
