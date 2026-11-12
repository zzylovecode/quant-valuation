"""
行业永续增长率假设
==================

不同行业的长期增长中枢差异很大，对所有股票统一用 3% 的永续增长率，
会系统性地高估衰退行业、低估成长行业。

本模块按行业给出永续增长率（terminal growth）默认值，并写明依据，
便于审阅与调整。

当前重点：白酒板块
-----------------
2025-05-18 修订版《党政机关厉行节约反对浪费条例》明确
「公务接待工作餐不得提供高档菜肴、不得提供香烟、不上酒」。
部分地区执行扩大化，波及商务与私人宴请场景，2025 年二三季度
白酒消费明显收缩，多数上市酒企营收利润同比下滑。

叠加因素：
  - 渠道去库存，飞天茅台批价由 2000 元以上回落至 1600 元附近
  - 消费代际迁移，年轻群体偏好低度酒
  - 贵州茅台 2025 年度营收 1720.54 亿元、净利 853.10 亿元，
    出现罕见的年度负增长；2026 年三季度营收/归母净利仅 +3.08%/+3.78%

结论：白酒长期增长中枢显著下移，永续增长率由默认 3% 下调至 1%，
低于长期名义 GDP 与通胀中枢。高端龙头（茅台、五粮液）若判断其
份额提升逻辑仍在，可在单股估值页手动上调至 1.5%~2%。
"""

from __future__ import annotations

from typing import Tuple

# 全局默认永续增长率
DEFAULT_TERMINAL_GROWTH = 0.03

# 白酒板块永续增长率
BAIJIU_TERMINAL_GROWTH = 0.01

BAIJIU_REASON = (
    "白酒板块：2025 年禁酒令 + 渠道去库存 + 消费代际迁移，"
    "永续增长率由 3% 下调至 1%"
)

# 主要白酒上市公司（证监会行业分类为「酒、饮料和精制茶制造业」，
# 该分类同时包含啤酒与饮料企业，故以代码清单为准，避免误伤）
_BAIJIU_CODES = frozenset({
    "600519.SH",  # 贵州茅台
    "000858.SZ",  # 五粮液
    "000568.SZ",  # 泸州老窖
    "600809.SH",  # 山西汾酒
    "002304.SZ",  # 洋河股份
    "000596.SZ",  # 古井贡酒
    "603369.SH",  # 今世缘
    "603589.SH",  # 口子窖
    "600779.SH",  # 水井坊
    "000799.SZ",  # 酒鬼酒
    "600702.SH",  # 舍得酒业
    "603198.SH",  # 迎驾贡酒
    "600559.SH",  # 老白干酒
    "600197.SH",  # 伊力特
    "603919.SH",  # 金徽酒
    "000860.SZ",  # 顺鑫农业（牛栏山）
    "000995.SZ",  # 皇台酒业
})


def resolve_terminal_growth(data) -> Tuple[float, str]:
    """
    根据股票所属行业解析永续增长率

    Args:
        data: FinancialData 对象（需含 ticker / industry 属性）

    Returns:
        (terminal_growth, note)
        note 为空字符串表示使用全局默认值，无特殊行业假设
    """
    code = getattr(data, "ticker", "") or ""
    industry = getattr(data, "industry", "") or ""

    if code in _BAIJIU_CODES or "白酒" in industry:
        return BAIJIU_TERMINAL_GROWTH, BAIJIU_REASON

    return DEFAULT_TERMINAL_GROWTH, ""
