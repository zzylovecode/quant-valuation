"""快速测试 AKShare 数据接入"""
import warnings
warnings.filterwarnings('ignore')
import sys
sys.path.insert(0, '.')

from quant_valuation.data_sources import AKShareClient, AKShareDataBuilder

print('=== 测试 FinancialData 构建 ===')
builder = AKShareDataBuilder()
data = builder.build('600519.SH', years=3)
print(f'名称: {data.name}')
print(f'股票代码: {data.ticker}')
print(f'股价: {data.current_price:.2f} 元')
print(f'总股本: {data.total_shares:.2f} 亿股')
print(f'市值: {data.current_price * data.total_shares:.0f} 亿元')
print()
print(f'营收: {data.revenue:.2f} 亿元')
print(f'净利润: {data.net_profit:.2f} 亿元')
print(f'EPS: {data.eps:.2f} 元')
print(f'BVPS: {data.bvps:.2f} 元')
print()
print(f'ROE: {data.calc_roe()*100:.2f}%')
print(f'PE: {data.calc_pe():.2f}')
print(f'PB: {data.calc_pb():.2f}')
print()
print(f'历史年份: {list(range(len(data.historical_revenue)))}')
print(f'营收历史: {[f"{x:.2f}亿" for x in data.historical_revenue]}')
print(f'净利润历史: {[f"{x:.2f}亿" for x in data.historical_net_profit]}')
print()
print(f'经营现金流: {data.operating_cash_flow:.2f} 亿元')
print(f'自由现金流: {data.free_cash_flow:.2f} 亿元')
print()
print('=== 测试估值计算 ===')
from quant_valuation import ValuationAnalyzer
analyzer = ValuationAnalyzer(data)
report = analyzer.full_valuation(
    dcf_params={
        "growth_rate": 0.15,
        "high_growth_years": 5,
        "terminal_growth": 0.03,
    }
)
print(f'综合估值: {report.weighted_value:.2f} 元')
print(f'估值评级: {report.rating}')
print(f'上涨空间: {report.weighted_upside*100:.2f}%')
print()
print('构建成功！')
