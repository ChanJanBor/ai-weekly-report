# 🤖 AI 行业周报 — 自动生成系统

多源聚合 · 真实数据 · 情感分析 · 周度对比 · 传导链 · 数据看板 · PDF/PPT 导出

## ✨ 功能特性

| 功能 | 说明 |
|------|------|
| 📡 多源数据采集 | IT之家 · 机器之心 · TechCrunch · The Verge · Wired · AI News |
| 🧠 情感分析 | 多维度关键词权重 + 上下文语义规则，自动标注利好/利空/中性 |
| 📊 周度对比 | 本周 vs 上周情感变化、话题热度迁移 |
| 🔗 市场传导链 | 政策 → 产业 → 资本市场的传导路径分析 |
| 📈 趋势信号 | 综合本周新闻提炼的核心趋势判断 |
| 💰 模型价格对比 | 主流大模型 API 价格一览表 |
| 📊 数据看板 | 情感环形图、来源分布、关键词云、标签分布 |
| 🌐 翻译 | 中英互译（Google Translate + MyMemory 双源备选） |
| 📄 PDF 导出 | Playwright 渲染完整页面，保存到桌面 |
| 📊 PPT 导出 | python-pptx 生成专业演示文稿，保存到桌面 |
| 🔄 一键更新 | 双击启动，页面自动抓取最近 7 天数据 |

## 🚀 快速开始

### 环境要求

- Python 3.8+
- Node.js（可选，用于翻译代理）

### 安装依赖

```bash
pip install feedparser requests python-pptx playwright
python -m playwright install chromium
```

### 一键启动（Windows）

双击 `启动周报.bat`，浏览器自动打开 `http://localhost:8899`。

### 手动启动

```bash
python server.py --port 8899
```

### 启动参数

```bash
python server.py --port 8899          # 指定端口
python server.py --no-open            # 不自动打开浏览器
python server.py --fetch-now          # 启动时立即抓取数据
```

## 📁 项目结构

```
ai_weekly_report/
├── server.py                # Python HTTP 服务器（核心）
├── report.html              # 报告页面（全内容展示）
├── ai_scraper.py            # 多源 RSS 数据采集器
├── ai_sentiment.py          # 情感分析引擎
├── ai_export.py             # PDF/Word 导出引擎
├── ai_scheduler.py          # 定时任务 & 邮件/飞书推送
├── translate_proxy.js       # Node.js 翻译代理（可选）
├── 启动周报.bat              # Windows 一键启动
├── ai_weekly_report.html    # 原始版本（Tab 切换）
├── ai_weekly_report_v2.html # V2 版本
├── ai_weekly_report_v3.html # V3 版本
└── README.md
```

## 🔧 架构设计

```
┌─────────────┐     ┌──────────────┐     ┌─────────────┐
│  RSS 数据源  │────▶│  Python 服务器 │────▶│  浏览器页面   │
│  6+ sources │     │  server.py   │     │ report.html  │
└─────────────┘     └──────┬───────┘     └──────┬──────┘
                           │                     │
                    ┌──────┴───────┐     ┌───────┴──────┐
                    │ API Endpoints │     │ 导出功能      │
                    │ /api/fetch    │     │ PDF (Playwright)│
                    │ /api/translate│     │ PPT (pptx)    │
                    │ /api/export/* │     └──────────────┘
                    └──────────────┘
```

### API 接口

| 接口 | 说明 |
|------|------|
| `GET /` | 报告页面 |
| `GET /api/fetch` | 触发数据采集 |
| `GET /api/status` | 采集状态 |
| `GET /api/translate?text=...&tl=zh-CN` | 翻译代理 |
| `GET /api/export/pdf` | 导出 PDF 到桌面 |
| `GET /api/export/ppt` | 导出 PPT 到桌面 |
| `GET /ai_weekly_data.json` | 获取数据 |

## 📊 数据来源

| 来源 | 语言 | 类型 |
|------|------|------|
| IT之家 | 中文 | 科技新闻 RSS |
| 机器之心 | 中文 | AI 专业媒体 RSS |
| TechCrunch | 英文 | 科技媒体 RSS |
| The Verge | 英文 | 科技媒体 RSS |
| Wired | 英文 | 科技媒体 RSS |
| AI News | 英文 | AI 新闻 RSS |

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License
