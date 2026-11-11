"""快速测试 AKShare 接口"""
import warnings; warnings.filterwarnings('ignore')
import akshare as ak

print('测试1: 日线行情')
df = ak.stock_zh_a_hist(symbol='600519', period='daily', start_date='20240101', end_date='20251231', adjust='qfq')
print(f'  行数: {len(df)}')
print(f'  列: {df.columns.tolist()}')
if len(df) > 0:
    print(f'  最新收盘价: {df.iloc[-1]["收盘"]}')

print()
print('测试2: 寻找 PE/PB 接口')
# 试试 stock_individual_info_em 里有没有市值
df2 = ak.stock_individual_info_em(symbol='600519')
print(f'  基本信息: ')
print(df2.to_string())

print()
print('测试3: 财务指标')
df3 = ak.stock_financial_analysis_indicator(symbol='600519')
print(f'  行数: {len(df3)}')
print(f'  列: {df3.columns.tolist()[:20]}')
