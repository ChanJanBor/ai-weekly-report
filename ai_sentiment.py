#!/usr/bin/env python3
"""
AI News Sentiment Analyzer
情感分析模块 — 对AI行业新闻自动标注利好/利空/中性
====================================================
基于多维度关键词权重 + 上下文语义规则：
  🟢 利好  — 新产品发布、融资成功、政策支持、技术突破
  🔴 利空  — 监管收紧、安全事故、裁员、竞争失利
  🟡 中性  — 行业报告、学术研究、日常动态

用法:
    python ai_sentiment.py                      # 分析 ai_weekly_data.json
    python ai_sentiment.py --text "新闻标题"      # 分析单条文本
    python ai_sentiment.py --batch input.json    # 批量分析
"""

import json
import re
import sys
import argparse
from pathlib import Path
from typing import Dict, List, Tuple, Optional


# ============================================================
# 情感词典 (多维度加权)
# ============================================================

class SentimentLexicon:
    """中英双语 AI 行业情感词典"""

    # ── 利好信号词 (每项: 关键词, 权重) ──
    BULLISH = [
        # 产品与发布
        (r'发布|推出|上线|开源|release|launch|unveil|announce|roll.?out', 0.6),
        (r'突破|超越|领先|第一|首创|首款|breakthrough|surpass|leading|first|state.of.the.art', 0.8),
        (r'升级|更新|增强|优化|upgrade|enhance|improve|boost', 0.5),
        # 融资与资本
        (r'融资|募资|投资|估值|上市|IPO|funding|invest|valuation|raise.*\$', 0.9),
        (r'收购|并购|acquire|acquisition|merger?', 0.6),
        (r'营收增长|利润|盈利|收入翻|revenue.*grow|profit|beat.*expect', 0.8),
        # 技术与性能
        (r'性能提升|性能翻倍|成本降低|效率提升|performance.*improve|cost.*reduce|accuracy.*boost', 0.7),
        (r'SOTA|state-of-the-art|刷新.*记录|刷新.*榜单|benchmark.*top', 0.8),
        (r'参数.*万亿|万亿参数|trillion.*parameter', 0.6),
        (r'开源.*免费|free.*open|MIT.*license|Apache.*license', 0.5),
        # 政策与生态
        (r'政策支持|扶持|补贴|鼓励|利好|policy.*support|subsid|encourage', 0.7),
        (r'合作|签约|战略合作|partnership|collaboration|alliance|joint.*venture', 0.5),
        (r'市场份额.*增长|占有率.*提升|market.*share.*grow', 0.7),
        (r'需求旺盛|供不应求|订单.*增长|Surging.*demand|sold.*out', 0.7),
        # 用户与采用
        (r'用户.*突破|注册.*突破|日活.*增长|user.*million|DAU.*grow|adoption.*surge', 0.7),
        (r'企业客户|部署|落地|deploy|enterprise.*adopt|commercialize', 0.5),
    ]

    # ── 利空信号词 ──
    BEARISH = [
        # 监管与合规
        (r'调查|处罚|罚款|禁令|限制|监管.*收紧|investigation|fine|penalty|ban|restrict|regulation.*tighten', 0.8),
        (r'诉讼|起诉|侵犯|侵权|lawsuit|sue|infringement|violat', 0.9),
        (r'合规风险|不合规|违规|non.?compli|violation', 0.8),
        # 安全与事故
        (r'泄露|数据泄露|隐私.*泄露|安全.*漏洞|breach|leak|data.*exposure|vulnerability', 0.9),
        (r'宕机|中断|故障|崩溃|outage|downtime|crash|failure', 0.7),
        (r'偏见|歧视|幻觉|有害|bias|discriminat|hallucin|harmful|toxic', 0.7),
        # 财务与市场
        (r'亏损|裁员|裁员.*%|关闭|破产|lost|loss|layoff|shut.*down|bankrupt', 0.9),
        (r'营收下滑|收入.*下降|利润.*下滑|revenue.*decline|profit.*drop', 0.8),
        (r'股价暴跌|股价下跌|市值蒸发|stock.*plunge|share.*crash', 0.9),
        (r'推迟|延期|取消|delay|postpone|cancel|scrap', 0.6),
        # 竞争与市场
        (r'失去.*客户|客户流失|churn|lose.*customer|defect', 0.7),
        (r'落后|掉队|边缘化|fall.*behind|lag.*behind|lose.*edge', 0.6),
        (r'价格战|补贴.*烧钱|price.*war|burn.*cash', 0.5),
        # 技术与质量
        (r'质疑|争议|批评|翻车|question|controversy|critici|backlash', 0.6),
        (r'准确率.*低|效果不佳|表现.*差|accuracy.*low|poor.*performance', 0.7),
    ]

    # ── 行业/公司特定信号 ──
    ENTITY_SIGNALS = {
        # 巨头利好消息
        "OpenAI": [
            (r'(OpenAI|openai).*(发布|推出|GPT|o\d)', 0.7),
            (r'(OpenAI|openai).*(融资|估值|营收)', 0.8),
        ],
        "Anthropic": [
            (r'(Anthropic|anthropic).*(发布|推出|Claude)', 0.7),
            (r'(Anthropic|anthropic).*(融资|收购)', 0.8),
        ],
        "Google": [
            (r'(Google|谷歌|google).*(Gemini|发布|推出)', 0.7),
        ],
        "DeepSeek": [
            (r'(DeepSeek|deepseek).*(发布|开源|V\d|R\d)', 0.8),
            (r'(DeepSeek|deepseek).*(超越|领先|突破)', 0.8),
        ],
        # 中国公司
        "百度/文心": [
            (r'(百度|文心).*(发布|升级|超越)', 0.6),
        ],
        "字节/豆包": [
            (r'(字节|豆包|ByteDance).*(发布|上线|增长)', 0.6),
        ],
        "阿里/通义": [
            (r'(阿里|通义|Qwen).*(发布|开源|增长)', 0.6),
        ],
    }

    # ── 程度副词增强/减弱 ──
    INTENSIFIERS = {
        'strong': [
            r'重大|历史性|里程碑|前所未有|惊人|爆炸|井喷',
            r'massive|historic|milestone|unprecedented|stunning|explosive',
        ],
        'weak': [
            r'小幅|略微|可能|传闻|据传|猜测',
            r'slight|minor|possibly|rumored|reportedly|speculated',
        ],
    }


class SentimentAnalyzer:
    """AI 新闻情感分析器"""

    def __init__(self, lexicon: SentimentLexicon = None):
        self.lexicon = lexicon or SentimentLexicon()
        self._compile_patterns()

    def _compile_patterns(self):
        """预编译正则提高性能"""
        self._bullish = [(re.compile(p, re.IGNORECASE), w) for p, w in self.lexicon.BULLISH]
        self._bearish = [(re.compile(p, re.IGNORECASE), w) for p, w in self.lexicon.BEARISH]
        self._entity = {}
        for entity, patterns in self.lexicon.ENTITY_SIGNALS.items():
            self._entity[entity] = [(re.compile(p, re.IGNORECASE), w) for p, w in patterns]

    def analyze(self, title: str, summary: str = "") -> Dict:
        """
        分析单条新闻的情感倾向
        返回: {sentiment, score, confidence, signals, ...}
        """
        text = f"{title} {summary}"

        # 1. 计算基础分数
        bull_score, bull_signals = self._score(text, self._bullish)
        bear_score, bear_signals = self._score(text, self._bearish)

        # 2. 实体特定信号
        entity_boost = 0
        for entity, patterns in self._entity.items():
            if re.search(re.escape(entity), text, re.IGNORECASE):
                e_score, e_signals = self._score(text, patterns)
                if e_score > 0:
                    bull_score += e_score
                    bull_signals.extend(e_signals)

        # 3. 程度副词调整
        intensifier = self._get_intensifier(text)
        if intensifier == 'strong':
            bull_score *= 1.2
            bear_score *= 1.2
        elif intensifier == 'weak':
            bull_score *= 0.8
            bear_score *= 0.8

        # 4. 净得分 & 判定
        net_score = bull_score - bear_score

        if net_score >= 1.5:
            sentiment = "🟢 利好"
            confidence = min(0.95, 0.5 + net_score * 0.1)
        elif net_score >= 0.5:
            sentiment = "🟢 偏多"
            confidence = min(0.85, 0.5 + net_score * 0.15)
        elif net_score <= -1.5:
            sentiment = "🔴 利空"
            confidence = min(0.95, 0.5 + abs(net_score) * 0.1)
        elif net_score <= -0.5:
            sentiment = "🔴 偏空"
            confidence = min(0.85, 0.5 + abs(net_score) * 0.15)
        else:
            sentiment = "🟡 中性"
            confidence = 0.5 + abs(net_score) * 0.1

        return {
            "sentiment": sentiment,
            "sentiment_en": sentiment.split()[-1] if " " in sentiment else sentiment,
            "score": round(net_score, 2),
            "confidence": round(confidence, 2),
            "bullish_signals": bull_signals[:5],
            "bearish_signals": bear_signals[:5],
            "bull_score": round(bull_score, 2),
            "bear_score": round(bear_score, 2),
        }

    def _score(self, text: str, patterns: list) -> Tuple[float, List[str]]:
        """计算匹配分数"""
        total = 0.0
        signals = []
        for pattern, weight in patterns:
            match = pattern.search(text)
            if match:
                total += weight
                signals.append(match.group(0)[:40])
        return total, signals

    def _get_intensifier(self, text: str) -> Optional[str]:
        """检测程度副词"""
        for kw in self.lexicon.INTENSIFIERS['strong']:
            if re.search(kw, text, re.IGNORECASE):
                return 'strong'
        for kw in self.lexicon.INTENSIFIERS['weak']:
            if re.search(kw, text, re.IGNORECASE):
                return 'weak'
        return None

    def analyze_batch(self, articles: List[dict]) -> List[dict]:
        """批量分析"""
        results = []
        for article in articles:
            analysis = self.analyze(
                article.get("title", ""),
                article.get("summary", "")
            )
            article["sentiment"] = analysis
            results.append(article)
        return results

    def summary_stats(self, articles: List[dict]) -> dict:
        """生成整体情感统计"""
        counts = {"🟢 利好": 0, "🟢 偏多": 0, "🟡 中性": 0, "🔴 偏空": 0, "🔴 利空": 0}
        for a in articles:
            s = a.get("sentiment", {}).get("sentiment", "🟡 中性")
            counts[s] = counts.get(s, 0) + 1

        total = len(articles) or 1
        bull_ratio = (counts.get("🟢 利好", 0) + counts.get("🟢 偏多", 0)) / total
        bear_ratio = (counts.get("🔴 利空", 0) + counts.get("🔴 偏空", 0)) / total

        return {
            "total": total,
            "distribution": counts,
            "bullish_ratio": round(bull_ratio, 3),
            "bearish_ratio": round(bear_ratio, 3),
            "overall_sentiment": (
                "🟢 整体偏乐观" if bull_ratio > 0.5
                else "🔴 整体偏悲观" if bear_ratio > 0.4
                else "🟡 整体中性"
            ),
        }


# ============================================================
# 与 Scraper 集成
# ============================================================

def run_sentiment_on_file(data_file: str, output_file: str = None):
    """读取抓取数据，跑情感分析，写回"""
    path = Path(data_file)
    if not path.exists():
        print(f"❌ 文件不存在: {data_file}")
        return

    data = json.loads(path.read_text(encoding="utf-8"))
    articles = data.get("articles", [])
    print(f"📊 正在分析 {len(articles)} 条新闻...")

    analyzer = SentimentAnalyzer()
    analyzed = analyzer.analyze_batch(articles)
    stats = analyzer.summary_stats(analyzed)

    data["articles"] = analyzed
    data["sentiment_stats"] = stats

    out = Path(output_file or data_file)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n{'='*50}")
    print(f"  情感分析完成")
    print(f"{'='*50}")
    print(f"  总计: {stats['total']} 条")
    for label, count in stats["distribution"].items():
        bar = "█" * (count * 30 // max(stats['total'], 1))
        print(f"  {label}: {count} {bar}")
    print(f"  看多率: {stats['bullish_ratio']:.0%}")
    print(f"  看空率: {stats['bearish_ratio']:.0%}")
    print(f"  总体: {stats['overall_sentiment']}")
    print(f"\n📁 已保存: {out}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI News Sentiment Analyzer")
    parser.add_argument("--file", default=None, help="输入JSON文件 (默认: ai_weekly_data.json)")
    parser.add_argument("--text", default=None, help="直接分析文本")
    parser.add_argument("--batch", default=None, help="批量分析JSON文件")
    parser.add_argument("--output", default=None, help="输出文件路径")
    args = parser.parse_args()

    analyzer = SentimentAnalyzer()

    if args.text:
        result = analyzer.analyze(args.text)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if args.batch:
        run_sentiment_on_file(args.batch, args.output)
        return

    # 默认: 分析抓取结果
    data_file = args.file or str(Path(__file__).parent / "ai_weekly_data.json")
    run_sentiment_on_file(data_file, args.output)


if __name__ == "__main__":
    main()
