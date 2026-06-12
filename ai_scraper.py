#!/usr/bin/env python3
"""
AI Weekly Report Scraper Engine
多源聚合抓取引擎 — RSS + API 自动化采集
============================================
用法:
    python ai_scraper.py              # 抓取本周新闻
    python ai_scraper.py --week -1    # 抓取上周新闻
    python ai_scraper.py --output json  # 输出JSON格式
    python ai_scraper.py --daemon       # 守护进程模式(定时抓取)
"""

import feedparser
import requests
import json
import hashlib
import re
import os
import sys
import time
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional, Tuple

# ============================================================
# 配置区
# ============================================================

CONFIG = {
    "output_dir": os.path.dirname(os.path.abspath(__file__)),
    "cache_file": "ai_news_cache.json",
    "output_file": "ai_weekly_data.json",
    "max_articles_per_source": 20,
    "request_timeout": 15,
    "user_agent": "AI-Weekly-Report-Scraper/2.0 (research aggregator)",
    "fetch_interval_hours": 6,  # daemon mode polling interval
}

# ── RSS 订阅源 ──
RSS_FEEDS = [
    # 国际科技媒体
    {"url": "https://feeds.feedburner.com/TechCrunch/artificial-intelligence", "source": "TechCrunch", "lang": "en", "category": "AI"},
    {"url": "https://www.theverge.com/rss/ai-artificial-intelligence/index.xml", "source": "The Verge", "lang": "en", "category": "AI"},
    {"url": "https://www.wired.com/feed/tag/ai/latest/rss", "source": "Wired", "lang": "en", "category": "AI"},
    {"url": "https://venturebeat.com/category/ai/feed/", "source": "VentureBeat", "lang": "en", "category": "AI"},
    {"url": "https://www.artificialintelligence-news.com/feed/", "source": "AI News", "lang": "en", "category": "AI"},
    # 中国科技媒体
    {"url": "https://www.ithome.com/rss/", "source": "IT之家", "lang": "zh", "category": "科技"},
    {"url": "https://rsshub.app/36kr/motif/ai", "source": "36氪AI", "lang": "zh", "category": "AI"},
    {"url": "https://www.jiqizhixin.com/rss", "source": "机器之心", "lang": "zh", "category": "AI"},
    {"url": "https://rsshub.app/huxiu/channel/ai", "source": "虎嗅AI", "lang": "zh", "category": "AI"},
    # 学术
    {"url": "https://arxiv.org/rss/cs.AI", "source": "arXiv AI", "lang": "en", "category": "学术"},
    {"url": "https://rsshub.app/openai/research", "source": "OpenAI Blog", "lang": "en", "category": "研究"},
    {"url": "https://www.anthropic.com/research/feed", "source": "Anthropic Research", "lang": "en", "category": "研究"},
    {"url": "https://blog.google/technology/ai/rss/", "source": "Google AI Blog", "lang": "en", "category": "研究"},
]

# ── API 数据源 (需要 Key 的留空则跳过) ──
API_SOURCES = [
    # NewsAPI — 需配置 API Key
    {"name": "NewsAPI", "url": "https://newsapi.org/v2/everything", "params": {
        "q": "(artificial intelligence OR AI OR machine learning OR LLM OR 人工智能 OR 大模型)",
        "from": "",       # 动态填充
        "to": "",         # 动态填充
        "sortBy": "publishedAt",
        "language": "en",
        "pageSize": 30,
        "apiKey": "",     # 填入你的 NewsAPI Key
    }, "enabled": False},
]

# ── 关键词增强 (提高相关性) ──
RELEVANCE_KEYWORDS = [
    r'\bAI\b', r'\bGPT\b', r'\bLLM\b', r'\bClaude\b', r'\bGemini\b', r'\bDeepSeek\b',
    r'\bOpenAI\b', r'\bAnthropic\b', r'\bGoogle\b', r'\bagent\b', r'\b智能体\b',
    r'大模型', r'人工智能', r'深度学习', r'机器学习', r'神经网络', r'生成式',
    r'\bfine-?tun', r'\btransformer\b', r'\bMoE\b', r'\bRAG\b', r'\bRLHF\b',
    r'AI芯片', r'GPU', r'算力', r'数据中心', r'融资', r'收购', r'上市',
    r'百川', r'智谱', r'月之暗面', r'Kimi', r'文心', r'通义', r'豆包',
]


# ============================================================
# 核心抓取引擎
# ============================================================

class AINewsScraper:
    """多源 AI 新闻抓取引擎"""

    def __init__(self, config: dict = None):
        self.config = config or CONFIG
        self.cache_path = Path(self.config["output_dir"]) / self.config["cache_file"]
        self.output_path = Path(self.config["output_dir"]) / self.config["output_file"]
        self.cache = self._load_cache()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config["user_agent"]})

    def _load_cache(self) -> dict:
        if self.cache_path.exists():
            try:
                return json.loads(self.cache_path.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_cache(self):
        self.cache_path.write_text(json.dumps(self.cache, ensure_ascii=False, indent=2), encoding="utf-8")

    def _hash_url(self, url: str) -> str:
        return hashlib.md5(url.encode()).hexdigest()[:12]

    def _is_relevant(self, text: str) -> bool:
        """关键词相关性过滤"""
        combined = " ".join([text] if isinstance(text, str) else text)
        score = sum(1 for kw in RELEVANCE_KEYWORDS if re.search(kw, combined, re.IGNORECASE))
        return score >= 1

    def _parse_feed_item(self, entry, source_info: dict) -> Optional[dict]:
        """解析单条 RSS 条目"""
        title = getattr(entry, 'title', '') or ''
        summary = getattr(entry, 'summary', '') or getattr(entry, 'description', '') or ''
        link = getattr(entry, 'link', '') or ''
        published = getattr(entry, 'published', '') or getattr(entry, 'updated', '') or ''

        # 清理 HTML 标签
        summary_clean = re.sub(r'<[^>]+>', '', summary)[:500]

        full_text = f"{title} {summary_clean}"
        if not self._is_relevant(full_text):
            return None

        url_hash = self._hash_url(link)
        if url_hash in self.cache:
            return None  # 已抓取过

        self.cache[url_hash] = datetime.now().isoformat()

        # 分类标签
        tags = self._classify_tags(title + " " + summary_clean)

        return {
            "id": url_hash,
            "title": title.strip(),
            "summary": summary_clean.strip(),
            "url": link,
            "source": source_info.get("source", "Unknown"),
            "lang": source_info.get("lang", "en"),
            "category": source_info.get("category", "AI"),
            "tags": tags,
            "published": published,
            "fetched_at": datetime.now().isoformat(),
        }

    def _classify_tags(self, text: str) -> List[str]:
        """自动分类标签"""
        tags = []
        rules = [
            (r'\b(模型|model|GPT|Claude|Gemini|DeepSeek|文心|通义|发布|release|launch)\b', '模型发布'),
            (r'\b(融资|funding|invest|估值|收购|acquisition|IPO|上市)\b', '投融资'),
            (r'\b(监管|policy|regulation|法案|act|立法|合规)\b', '监管政策'),
            (r'\b(agent|智能体|Agent|自动化|autonomous)\b', 'AI Agent'),
            (r'\b(芯片|GPU|算力|compute|infrastructure|数据中心|datacenter)\b', '基础设施'),
            (r'\b(中国|China|国产|华为|百度|阿里|腾讯|字节)\b', '中国动态'),
            (r'\b(开源|open.source|benchmark|评测)\b', '开源/评测'),
        ]
        for pattern, tag in rules:
            if re.search(pattern, text, re.IGNORECASE):
                tags.append(tag)
        return tags[:3]  # 最多3个标签

    def fetch_rss(self, feed_info: dict) -> List[dict]:
        """抓取单个 RSS 源"""
        results = []
        try:
            feed = feedparser.parse(feed_info["url"])
            if feed.bozo and not feed.entries:
                print(f"  ⚠ RSS 解析警告 [{feed_info['source']}]: {feed.bozo_exception}")
                return results

            for entry in feed.entries[:self.config["max_articles_per_source"]]:
                article = self._parse_feed_item(entry, feed_info)
                if article:
                    results.append(article)

            print(f"  ✓ [{feed_info['source']}] 抓取 {len(results)} 条相关新闻")
        except Exception as e:
            print(f"  ✗ [{feed_info['source']}] 抓取失败: {e}")
        return results

    def fetch_api(self, api_source: dict, week_start: str, week_end: str) -> List[dict]:
        """调用 API 源抓取"""
        if not api_source.get("enabled"):
            return []
        results = []
        try:
            params = dict(api_source.get("params", {}))
            params["from"] = week_start
            params["to"] = week_end
            if not params.get("apiKey"):
                print(f"  ⚠ [{api_source['name']}] 未配置 API Key，跳过")
                return results

            resp = self.session.get(api_source["url"], params=params, timeout=self.config["request_timeout"])
            resp.raise_for_status()
            data = resp.json()

            for article in data.get("articles", [])[:self.config["max_articles_per_source"]]:
                title = article.get("title", "")
                desc = article.get("description", "") or ""
                url = article.get("url", "")

                if not self._is_relevant(f"{title} {desc}"):
                    continue

                url_hash = self._hash_url(url)
                if url_hash in self.cache:
                    continue
                self.cache[url_hash] = datetime.now().isoformat()

                tags = self._classify_tags(f"{title} {desc}")
                results.append({
                    "id": url_hash,
                    "title": title,
                    "summary": desc[:500],
                    "url": url,
                    "source": api_source["name"],
                    "lang": "en",
                    "category": "AI",
                    "tags": tags,
                    "published": article.get("publishedAt", ""),
                    "fetched_at": datetime.now().isoformat(),
                })
            print(f"  ✓ [{api_source['name']}] 抓取 {len(results)} 条新闻")
        except Exception as e:
            print(f"  ✗ [{api_source['name']}] API 调用失败: {e}")
        return results

    def run(self, week_offset: int = 0) -> Dict:
        """
        执行全量抓取
        week_offset: 0=本周, -1=上周, 以此类推
        """
        today = datetime.now()
        # 计算本周一
        monday = today - timedelta(days=today.weekday())
        monday = monday.replace(hour=0, minute=0, second=0, microsecond=0)
        # 应用偏移
        target_monday = monday + timedelta(weeks=week_offset)
        target_sunday = target_monday + timedelta(days=6, hours=23, minutes=59, seconds=59)

        week_start = target_monday.strftime("%Y-%m-%d")
        week_end = target_sunday.strftime("%Y-%m-%d")

        print(f"\n{'='*60}")
        print(f"  AI Weekly Report Scraper v2.0")
        print(f"  抓取周期: {week_start} → {week_end}")
        print(f"{'='*60}\n")

        all_articles = []
        start_time = time.time()

        # Phase 1: 并发抓取 RSS
        print("📡 Phase 1: RSS 源并发抓取")
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(self.fetch_rss, feed): feed for feed in RSS_FEEDS}
            for future in as_completed(futures):
                try:
                    all_articles.extend(future.result())
                except Exception as e:
                    print(f"  ✗ 线程异常: {e}")

        # Phase 2: API 源
        print("\n🔌 Phase 2: API 源抓取")
        for api_src in API_SOURCES:
            all_articles.extend(self.fetch_api(api_src, week_start, week_end))

        # Phase 3: 去重 & 排序
        print(f"\n📊 Phase 3: 后处理")
        seen = set()
        unique = []
        for a in all_articles:
            if a["id"] not in seen:
                seen.add(a["id"])
                unique.append(a)

        # 按发布时间排序
        unique.sort(key=lambda x: x.get("published", ""), reverse=True)

        # Phase 4: 统计
        stats = self._compute_stats(unique)

        elapsed = time.time() - start_time
        print(f"\n✅ 抓取完成: {len(unique)} 条去重新闻 | 耗时 {elapsed:.1f}s")
        print(f"   来源: {stats['source_count']} 个 | 命中率: {len(unique)}/{len(all_articles)}")
        print(f"   缓存条目: {len(self.cache)}")

        # 保存缓存 & 输出
        self._save_cache()

        result = {
            "meta": {
                "generated_at": datetime.now().isoformat(),
                "week_start": week_start,
                "week_end": week_end,
                "total_articles": len(unique),
                "fetch_duration_seconds": round(elapsed, 1),
            },
            "stats": stats,
            "articles": unique,
        }

        # 输出JSON
        self.output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n📁 数据已保存: {self.output_path}")

        return result

    def _compute_stats(self, articles: List[dict]) -> dict:
        """聚合统计"""
        sources = {}
        tags_count = {}
        daily_count = {}
        for a in articles:
            src = a["source"]
            sources[src] = sources.get(src, 0) + 1
            for t in a.get("tags", []):
                tags_count[t] = tags_count.get(t, 0) + 1
            date_key = a.get("published", "")[:10] if a.get("published") else "unknown"
            daily_count[date_key] = daily_count.get(date_key, 0) + 1

        return {
            "source_count": len(sources),
            "sources": dict(sorted(sources.items(), key=lambda x: -x[1])[:15]),
            "top_tags": dict(sorted(tags_count.items(), key=lambda x: -x[1])[:10]),
            "daily_distribution": dict(sorted(daily_count.items())),
        }


def daemon_mode(scraper: AINewsScraper, interval_hours: int = 6):
    """守护进程模式 — 定时自动抓取"""
    print(f"🔄 守护进程已启动，每 {interval_hours} 小时抓取一次")
    print(f"   按 Ctrl+C 停止\n")
    try:
        while True:
            scraper.run()
            next_run = datetime.now() + timedelta(hours=interval_hours)
            print(f"\n⏰ 下次抓取: {next_run.strftime('%Y-%m-%d %H:%M:%S')}")
            time.sleep(interval_hours * 3600)
    except KeyboardInterrupt:
        print("\n👋 守护进程已停止")


# ============================================================
# CLI Entry
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI Weekly Report Scraper Engine")
    parser.add_argument("--week", type=int, default=0, help="周偏移: 0=本周, -1=上周")
    parser.add_argument("--output", choices=["json", "text"], default="json", help="输出格式")
    parser.add_argument("--daemon", action="store_true", help="守护进程模式")
    parser.add_argument("--interval", type=int, default=6, help="守护进程抓取间隔(小时)")
    parser.add_argument("--clear-cache", action="store_true", help="清除抓取缓存")
    args = parser.parse_args()

    scraper = AINewsScraper()

    if args.clear_cache:
        scraper.cache = {}
        scraper._save_cache()
        print("✅ 缓存已清除")
        return

    if args.daemon:
        daemon_mode(scraper, args.interval)
        return

    result = scraper.run(week_offset=args.week)

    if args.output == "text":
        print(f"\n{'='*60}")
        print(f"  TOP 10 新闻摘要")
        print(f"{'='*60}")
        for i, a in enumerate(result["articles"][:10], 1):
            print(f"\n{i}. [{', '.join(a['tags'])}] {a['title']}")
            print(f"   来源: {a['source']} | {a.get('published', '')[:10]}")
            print(f"   {a['summary'][:120]}...")


if __name__ == "__main__":
    main()
