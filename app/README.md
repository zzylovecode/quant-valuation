# 量化估值分析工具 — 可视化界面

基于 Streamlit 的交互式量化估值分析 Web 应用。

## 🚀 快速启动

```bash
# 进入项目目录
cd 你的项目目录

# 安装依赖（如果还没装）
pip install streamlit plotly pandas tushare

# 启动应用
streamlit run app/main.py
```

启动后浏览器会自动打开，默认地址：`http://localhost:8501`

## 📱 功能页面

| 页面 | 功能 |
|------|------|
| 🏠 概览 | 工具总览、快速估值预览、估值区间定位 |
| 📈 单股估值 | 交互式调整参数，实时查看7种方法估值结果 |
| 🔥 敏感性分析 | DCF 增长率 × 折现率热力图，实时计算 |
| 📋 批量估值排行 | 多股票排行榜、多种策略筛选、散点图 |
| 📉 策略回测 | 历史回测净值曲线、绩效指标、雷达图对比 |
| ⚙️ 数据设置 | Tushare Token 配置、数据源选择 |

## ⚙️ 配置 Tushare 真实数据

1. 注册 Tushare 账号：https://tushare.pro/register
2. 获取你的 API Token
3. 在应用的「数据设置」页面输入 Token，或设置环境变量：
   ```bash
   # Windows
   set TUSHARE_TOKEN=你的token

   # 然后再启动
   streamlit run app/main.py
   ```

## 📁 目录结构

```
app/
├── main.py              # 应用入口
├── utils.py             # 共享工具函数
└── pages/
    ├── overview.py      # 概览页
    ├── single_valuation.py  # 单股估值
    ├── sensitivity.py   # 敏感性分析
    ├── batch_screen.py  # 批量估值排行
    ├── backtest_view.py # 策略回测
    └── settings.py      # 数据设置
```

## 🎯 技术栈

- **前端框架**：Streamlit
- **图表**：Plotly
- **数据处理**：Pandas
- **估值引擎**：自有 quant_valuation 包
