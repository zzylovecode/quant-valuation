"""
结果导出
========

将批量估值结果导出为多种格式：
  - CSV 文件
  - Excel 文件（需安装 openpyxl）
  - 文本报告
  - 控制台表格
"""

from __future__ import annotations

import os
from typing import List, Optional

from .batch_valuator import StockValuationResult


class ResultExporter:
    """
    结果导出器

    使用方式：
        exporter = ResultExporter(results)
        exporter.to_csv("valuation_results.csv")
        exporter.to_excel("valuation_results.xlsx")
        print(exporter.to_text_table())
        print(exporter.generate_report(title="低估榜"))
    """

    # 默认列配置
    DEFAULT_COLUMNS = [
        ("股票代码", "ts_code", 10),
        ("股票名称", "name", 10),
        ("当前价", "current_price", 8),
        ("内在价值", "intrinsic_value", 10),
        ("涨跌空间%", "upside_downside_pct", 10),
        ("评级", "rating", 8),
        ("可信度", "confidence", 6),
        ("PE", "pe", 8),
        ("PB", "pb", 8),
        ("ROE%", "roe_pct", 8),
        ("净利润亿", "net_profit", 10),
        ("市值亿", "market_cap", 10),
        ("增速%", "profit_growth_pct", 8),
    ]

    def __init__(self, results: List[StockValuationResult]):
        self.results = results

    # ---------- 核心导出 ----------

    def to_csv(self, filepath: str, columns: Optional[List[tuple]] = None) -> str:
        """
        导出为 CSV 文件

        Args:
            filepath: 输出文件路径
            columns: 列配置 [(中文列名, 字段名, 宽度)]

        Returns:
            文件路径
        """
        import csv

        if columns is None:
            columns = self.DEFAULT_COLUMNS

        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            # 表头
            writer.writerow([col[0] for col in columns])
            # 数据行
            for r in self.results:
                row = []
                for _, field, _ in columns:
                    row.append(self._get_field(r, field))
                writer.writerow(row)

        return filepath

    def to_excel(self, filepath: str, sheet_name: str = "估值结果") -> str:
        """
        导出为 Excel 文件（需要 openpyxl）

        Returns:
            文件路径
        """
        try:
            import pandas as pd
        except ImportError:
            raise ImportError("导出 Excel 需要 pandas，请先安装: pip install pandas openpyxl")

        rows = [r.to_dict() for r in self.results]
        df = pd.DataFrame(rows)

        # 按涨跌空间降序
        if "涨跌空间" in df.columns:
            df = df.sort_values("涨跌空间", ascending=False)

        df.to_excel(filepath, sheet_name=sheet_name, index=False)
        return filepath

    # ---------- 文本格式 ----------

    def to_text_table(
        self,
        columns: Optional[List[tuple]] = None,
        max_rows: int = 50,
    ) -> str:
        """
        生成文本格式的表格

        Args:
            columns: 列配置
            max_rows: 最大行数
        """
        if columns is None:
            columns = self.DEFAULT_COLUMNS

        lines = []
        results = self.results[:max_rows]

        # 表头
        header = ""
        for name, _, width in columns:
            header += f"{name:>{width}} "
        lines.append(header)
        lines.append("-" * len(header))

        # 数据行
        for r in results:
            row = ""
            for _, field, width in columns:
                val = self._get_field(r, field)
                row += f"{val:>{width}} "
            lines.append(row)

        if len(self.results) > max_rows:
            lines.append(f"\n... 共 {len(self.results)} 条，仅显示前 {max_rows} 条")

        return "\n".join(lines)

    def generate_report(
        self,
        title: str = "批量估值报告",
        subtitle: str = "",
        show_summary: bool = True,
        show_top_undervalued: int = 20,
        show_top_overvalued: int = 10,
        show_rating_dist: bool = True,
    ) -> str:
        """
        生成完整的估值报告

        Args:
            title: 报告标题
            subtitle: 副标题
            show_summary: 是否显示统计摘要
            show_top_undervalued: 显示低估榜前 N 名
            show_top_overvalued: 显示高估榜前 N 名
            show_rating_dist: 是否显示评级分布
        """
        from .screeners import ValuationScreener

        screener = ValuationScreener(self.results)
        lines = []

        # 标题
        lines.append("=" * 70)
        lines.append(f"  {title}")
        if subtitle:
            lines.append(f"  {subtitle}")
        lines.append("=" * 70)
        lines.append("")

        # 摘要
        if show_summary:
            summary = self._summary_dict()
            lines.append("【整体统计】")
            lines.append(f"  股票总数: {summary['total']}")
            lines.append(f"  平均涨跌空间: {summary['avg_upside']:+.2f}%")
            lines.append(f"  中位涨跌空间: {summary['median_upside']:+.2f}%")
            lines.append(f"  最大上涨空间: {summary['max_upside']:+.2f}%")
            lines.append(f"  最大下跌空间: {summary['min_upside']:+.2f}%")
            lines.append(f"  低估数量(>20%): {summary['undervalued_count']}")
            lines.append(f"  高估数量(<-20%): {summary['overvalued_count']}")
            lines.append("")

        # 评级分布
        if show_rating_dist:
            dist = screener.rating_distribution()
            lines.append("【评级分布】")
            total = len(self.results)
            for rating in ["严重低估", "低估", "合理", "高估", "严重高估"]:
                count = dist.get(rating, 0)
                pct = count / total * 100 if total > 0 else 0
                bar = "█" * int(pct / 2)
                lines.append(f"  {rating:<6} {count:>4} 只 ({pct:>5.1f}%) {bar}")
            lines.append("")

        # 低估榜
        if show_top_undervalued > 0:
            top_under = screener.top_by_upside(show_top_undervalued)
            lines.append(f"【低估榜 Top {len(top_under)}】")
            lines.append(self._compact_table(top_under, show_rank=True))
            lines.append("")

        # 高估榜
        if show_top_overvalued > 0:
            top_over = screener.bottom_by_upside(show_top_overvalued)
            lines.append(f"【高估榜 Top {len(top_over)}】")
            lines.append(self._compact_table(top_over, show_rank=True))
            lines.append("")

        lines.append("=" * 70)
        return "\n".join(lines)

    # ---------- 内部工具 ----------

    def _get_field(self, result: StockValuationResult, field: str):
        """获取字段值，支持格式化字段名"""
        # 百分比字段
        if field == "upside_downside_pct":
            return f"{result.upside_downside*100:+.2f}%"
        if field == "roe_pct":
            return f"{result.roe*100:.2f}%"
        if field == "profit_growth_pct":
            return f"{result.profit_growth*100:.2f}%"

        # 数值格式化
        val = getattr(result, field, "")
        if isinstance(val, float):
            if abs(val) >= 100:
                return f"{val:.2f}"
            else:
                return f"{val:.2f}"
        return val

    def _compact_table(
        self,
        results: List[StockValuationResult],
        show_rank: bool = True,
    ) -> str:
        """生成紧凑表格（排行榜用）"""
        lines = []
        rank_w = 4
        code_w = 10
        name_w = 10
        price_w = 8
        value_w = 10
        upside_w = 10
        pe_w = 8
        roe_w = 8

        # 表头
        header = ""
        if show_rank:
            header += f"{'排名':>{rank_w}} "
        header += (
            f"{'代码':>{code_w}} "
            f"{'名称':>{name_w}} "
            f"{'现价':>{price_w}} "
            f"{'内在价值':>{value_w}} "
            f"{'涨跌空间':>{upside_w}} "
            f"{'PE':>{pe_w}} "
            f"{'ROE':>{roe_w}}"
        )
        lines.append(header)
        lines.append("-" * len(header))

        for i, r in enumerate(results, 1):
            row = ""
            if show_rank:
                row += f"{i:>{rank_w}} "
            upside_str = f"{r.upside_downside*100:+.2f}%"
            roe_str = f"{r.roe*100:.2f}%"
            row += (
                f"{r.ts_code:>{code_w}} "
                f"{r.name:>{name_w}} "
                f"{r.current_price:>{price_w}.2f} "
                f"{r.intrinsic_value:>{value_w}.2f} "
                f"{upside_str:>{upside_w}} "
                f"{r.pe:>{pe_w}.2f} "
                f"{roe_str:>{roe_w}}"
            )
            lines.append(row)

        return "\n".join(lines)

    def _summary_dict(self) -> dict:
        """统计摘要"""
        if not self.results:
            return {"total": 0, "avg_upside": 0, "median_upside": 0,
                    "max_upside": 0, "min_upside": 0,
                    "undervalued_count": 0, "overvalued_count": 0}

        upsides = [r.upside_downside * 100 for r in self.results]
        upsides_sorted = sorted(upsides)

        return {
            "total": len(self.results),
            "avg_upside": sum(upsides) / len(upsides),
            "median_upside": upsides_sorted[len(upsides_sorted) // 2],
            "max_upside": max(upsides),
            "min_upside": min(upsides),
            "undervalued_count": sum(1 for u in upsides if u > 20),
            "overvalued_count": sum(1 for u in upsides if u < -20),
        }
