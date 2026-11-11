"""
量化估值模型 — 使用示例
=======================

演示如何使用 quant_valuation 工具包对上市公司进行多维度估值分析。

运行方式：
    python example.py
"""

from quant_valuation import (
    FinancialData,
    DCFModel,
    RelativeValuation,
    DDMModel,
    ResidualIncomeModel,
    ValuationAnalyzer,
)


def build_sample_company() -> FinancialData:
    """
    构造一家示例公司的财务数据（模拟消费白马股特征）

    说明：以下数据为演示用的合成数据，非真实公司数据。
    """
    data = FinancialData(
        ticker="600000",
        name="示例消费公司",
        total_shares=100.0,          # 总股本 100 亿股
        current_price=50.0,          # 当前股价 50 元

        # 利润表（亿元）
        revenue=800.0,               # 营收 800 亿
        net_profit=120.0,            # 归母净利润 120 亿
        operating_profit=160.0,      # 营业利润 160 亿
        ebit=170.0,                  # EBIT 170 亿
        ebitda=220.0,                # EBITDA 220 亿
        eps=1.20,                    # 每股收益 1.2 元

        # 资产负债表
        total_assets=1500.0,         # 总资产 1500 亿
        total_equity=800.0,          # 净资产 800 亿
        cash=200.0,                  # 货币资金 200 亿
        interest_bearing_debt=100.0, # 有息负债 100 亿
        net_debt=-100.0,             # 净负债 = 100 - 200 = -100（净现金）
        bvps=8.00,                   # 每股净资产 8 元

        # 现金流量表
        operating_cash_flow=150.0,   # 经营现金流 150 亿
        capex=50.0,                  # 资本支出 50 亿
        free_cash_flow=100.0,        # 自由现金流 100 亿

        # 分红
        dividend_per_share=0.60,     # 每股分红 0.6 元
        dividend_payout_ratio=0.50,  # 分红率 50%

        # 历史数据（过去5年净利润，从远到近）
        historical_net_profit=[60.0, 72.0, 86.0, 102.0, 120.0],
        historical_revenue=[450.0, 540.0, 630.0, 720.0, 800.0],

        # 行业可比
        industry_pe=25.0,            # 行业平均 PE 25 倍
        industry_pb=4.0,             # 行业平均 PB 4 倍
    )
    return data


def demo_financial_overview(data: FinancialData):
    """演示1：财务数据概览与衍生指标"""
    print("=" * 60)
    print("【示例 1】财务数据概览")
    print("=" * 60)
    print(data.summary())
    print()
    print(f"净利润 CAGR (3年): {data.calc_profit_growth_rate(3)*100:.2f}%")
    print(f"营收 CAGR (3年): {data.calc_revenue_growth_rate(3)*100:.2f}%")
    print(f"自由现金流: {data.calc_free_cash_flow():.2f} 亿元")
    print(f"企业价值 EV: {data.calc_enterprise_value():.2f} 亿元")
    print()


def demo_dcf_valuation(data: FinancialData):
    """演示2：DCF 折现现金流估值"""
    print("=" * 60)
    print("【示例 2】DCF 折现现金流估值")
    print("=" * 60)

    model = DCFModel(data)

    # FCFF 模型
    print("--- FCFF 模型 (公司自由现金流) ---")
    fcff_result = model.fcff_valuation(
        growth_rate=0.12,        # 高速增长期年增速 12%
        high_growth_years=5,     # 高速增长 5 年
        terminal_growth=0.03,    # 永续增长 3%
        wacc=0.09,               # WACC 9%
    )
    print(fcff_result.summary(current_price=data.current_price))
    print()

    # FCFE 模型
    print("--- FCFE 模型 (股权自由现金流) ---")
    fcfe_result = model.fcfe_valuation(
        growth_rate=0.12,
        high_growth_years=5,
        terminal_growth=0.03,
        cost_of_equity=0.10,     # 股权成本 10%
    )
    print(fcfe_result.summary(current_price=data.current_price))
    print()

    # 敏感性分析
    print("--- 敏感性分析 ---")
    table = model.sensitivity_analysis(
        method="FCFF",
        growth_range=(0.06, 0.18, 5),
        wacc_range=(0.07, 0.11, 5),
        terminal_growth=0.03,
        high_growth_years=5,
    )
    print("增长率 × 折现率 → 每股内在价值")
    growth_rates = sorted(table["growth_rates"].keys())
    wacc_rates = sorted(table["growth_rates"][growth_rates[0]].keys())
    header = "g / WACC"
    print(f"{header:>10}", end=" ")
    for w in wacc_rates:
        print(f"{w*100:>7.1f}%", end=" ")
    print()
    for g in growth_rates:
        print(f"{g*100:>8.1f}%", end=" ")
        for w in wacc_rates:
            val = table["growth_rates"][g][w]
            print(f"{val:>8.2f}", end=" ")
        print()
    print()


def demo_relative_valuation(data: FinancialData):
    """演示3：相对估值"""
    print("=" * 60)
    print("【示例 3】相对估值 (PE / PB / PEG / PS / EV-EBITDA)")
    print("=" * 60)

    rv = RelativeValuation(data)
    expected_growth = data.calc_profit_growth_rate(3)

    # PE 估值
    pe_result = rv.pe_valuation(
        industry_pe=data.industry_pe,
        growth_adjusted=True,
        expected_growth=expected_growth,
    )
    print(pe_result.summary())
    print()

    # PB 估值（ROE 调整）
    pb_result = rv.pb_valuation(
        industry_pb=data.industry_pb,
        roe_adjusted=True,
    )
    print(pb_result.summary())
    print()

    # PEG 估值
    peg_result = rv.peg_valuation(
        target_peg=1.0,
        expected_growth=expected_growth,
    )
    print(peg_result.summary())
    print()

    # PS 估值
    ps_result = rv.ps_valuation(target_ps=5.0)
    print(ps_result.summary())
    print()

    # EV/EBITDA 估值
    ev_result = rv.ev_ebitda_valuation(target_ev_ebitda=15.0)
    print(ev_result.summary())
    print()

    # 综合相对估值
    print("--- 综合相对估值（等权）---")
    comp = rv.comprehensive_relative_valuation(
        methods=["PE", "PB", "PEG", "PS"],
        industry_pe=data.industry_pe,
        industry_pb=data.industry_pb,
        expected_growth=expected_growth,
        roe_adjusted=True,
    )
    for method, res in comp["results"].items():
        print(f"  {method}: {res.intrinsic_value_per_share:.2f} 元 (涨跌 {res.upside_downside*100:.1f}%)")
    print(f"  加权均值: {comp['weighted_value']:.2f} 元 (涨跌 {comp['upside_downside']*100:.1f}%)")
    print()


def demo_ddm_and_rim(data: FinancialData):
    """演示4：DDM 股息贴现模型 & 剩余收益模型"""
    print("=" * 60)
    print("【示例 4】DDM 股息贴现模型 & 剩余收益模型")
    print("=" * 60)

    ddm = DDMModel(data)

    # Gordon 增长模型
    print("--- Gordon 增长模型 ---")
    gordon = ddm.gordon_growth_ddm(
        growth_rate=0.05,      # 股息年增长 5%
        cost_of_equity=0.10,   # 股权成本 10%
    )
    print(gordon.summary(current_price=data.current_price))
    print()

    # 两阶段 DDM
    print("--- 两阶段 DDM ---")
    two_stage = ddm.two_stage_ddm(
        high_growth_rate=0.10,
        high_growth_years=5,
        stable_growth_rate=0.03,
        cost_of_equity=0.10,
    )
    print(two_stage.summary(current_price=data.current_price))
    print()

    # 剩余收益模型
    print("--- 剩余收益模型 (RIM) ---")
    rim = ResidualIncomeModel(data)
    rim_result = rim.valuation(
        high_growth_years=5,
        high_growth_roe=0.18,   # 高速增长期 ROE 18%
        terminal_roe=0.10,      # 稳定期 ROE 10%
        cost_of_equity=0.10,
        terminal_growth=0.03,
    )
    print(rim_result.summary(current_price=data.current_price))
    print()


def demo_full_analysis(data: FinancialData):
    """演示5：综合估值分析"""
    print("=" * 60)
    print("【示例 5】综合估值分析（全方法 + 评级）")
    print("=" * 60)

    analyzer = ValuationAnalyzer(data)

    # 使用成长型公司权重配置
    weights = ValuationAnalyzer.get_weights_for_company_type("growth")
    expected_growth = data.calc_profit_growth_rate(3)

    report = analyzer.full_valuation(
        weights=weights,
        dcf_params={
            "growth_rate": 0.12,
            "high_growth_years": 5,
            "terminal_growth": 0.03,
        },
        relative_params={
            "industry_pe": data.industry_pe,
            "industry_pb": data.industry_pb,
            "expected_growth": expected_growth,
            "roe_adjusted": True,
        },
        ddm_params={
            "high_growth_rate": 0.08,
            "high_growth_years": 5,
            "stable_growth_rate": 0.03,
            "cost_of_equity": 0.10,
        },
        rim_params={
            "high_growth_years": 5,
            "high_growth_roe": 0.18,
            "terminal_roe": 0.10,
            "cost_of_equity": 0.10,
        },
    )

    print(report.summary())
    print()

    # 安全边际分析
    print("--- 安全边际与估值区间 ---")
    zones = analyzer.value_zone_analysis(report.weighted_value)
    for zone, price in zones.items():
        bar_len = int((price / zones["极度高估区"]) * 40)
        bar = "█" * bar_len
        print(f"  {zone:<10} {price:>8.2f} 元 {bar}")

    # 标记当前价格位置
    current = data.current_price
    if current < zones["极度低估区"]:
        position = "远低于极度低估区 ⭐"
    elif current < zones["低估区"]:
        position = "极度低估区"
    elif current < zones["合理区下限"]:
        position = "低估区 ✅"
    elif current < zones["内在价值"]:
        position = "合理区（偏低）"
    elif current < zones["合理区上限"]:
        position = "合理区（偏高）"
    elif current < zones["高估区"]:
        position = "高估区 ⚠️"
    elif current < zones["极度高估区"]:
        position = "高估区（偏高）"
    else:
        position = "极度高估区 🚫"
    print(f"\n  当前股价 {current:.2f} 元 → 处于 {position}")
    print()

    # DCF 敏感性分析表
    print("--- DCF (FCFF) 敏感性分析 ---")
    sens_table = analyzer.dcf_sensitivity_table(
        method="FCFF",
        growth_range=(0.06, 0.18, 5),
        discount_range=(0.07, 0.11, 5),
    )
    print(sens_table)
    print()


def main():
    """主函数：依次运行所有示例"""
    print("\n" + "🎯" * 30)
    print("       量化估值模型工具 — 完整使用演示")
    print("🎯" * 30 + "\n")

    data = build_sample_company()

    demo_financial_overview(data)
    demo_dcf_valuation(data)
    demo_relative_valuation(data)
    demo_ddm_and_rim(data)
    demo_full_analysis(data)

    print("=" * 60)
    print("  演示完成！你可以修改 example.py 中的参数做更多实验")
    print("=" * 60)


if __name__ == "__main__":
    main()
