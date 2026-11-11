"""快速测试"""
import warnings; warnings.filterwarnings('ignore')
import sys; sys.path.insert(0, '.')
from quant_valuation.data_sources import AKShareClient

client = AKShareClient()

print('测试 get_daily:')
daily = client.get_daily('600519.SH')
print(f'  行数: {len(daily)}')
if len(daily) > 0:
    print(f'  第一行: {daily.iloc[0][["trade_date", "close"]].to_dict()}')
    print(f'  最后行: {daily.iloc[-1][["trade_date", "close"]].to_dict()}')

print()
print('测试 get_daily_basic:')
basic = client.get_daily_basic('600519.SH')
print(f'  行数: {len(basic)}')
if len(basic) > 0:
    print(f'  内容: {basic.iloc[0].to_dict()}')
