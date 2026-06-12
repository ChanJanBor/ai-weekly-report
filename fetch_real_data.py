#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_real_data.py — 多源 RSS 抓取 + 中英翻译 + 情感分析
用法:  python fetch_real_data.py
"""

import json, re, hashlib, time, urllib.request, urllib.parse
from pathlib import Path
from datetime import datetime
from html.parser import HTMLParser

OUT_DIR = Path(r"C:\Users\Administrator\Desktop\ai_weekly_report_v2")

FEEDS = [
    {"url": "https://www.ithome.com/rss/",       "src": "IT之家",  "lang": "zh"},
    {"url": "https://www.jiqizhixin.com/rss",   "src": "机器之心","lang": "zh"},
    {"url": "https://techcrunch.com/feed/",       "src": "TechCrunch","lang": "en"},
    {"url": "https://www.wired.com/feed/tag/ai/latest/rss", "src": "Wired","lang": "en"},
    {"url": "https://venturebeat.com/category/ai/feed/", "src": "VentureBeat","lang": "en"},
    {"url": "https://www.artificialintelligence-news.com/feed/", "src": "AI News","lang": "en"},
]

AI_RE = re.compile(
    r"(artificial intelligence|machine learning|deep learning|neural network|"
    r"large language model|llm|gpt|gemini|claude|chatgpt|openai|anthropic|google deepmind|"
    r"ai model|ai system|ai agent|autonomous ai|ai assistant|"
    r"AI|GPT|LLM|Claude|Gemini|DeepSeek|百川|智谱|文心|Kimi|通义|豆包|"
    r"大模型|人工智能|深度学习|神经网络|智能体|AI Agent|昇腾|摩尔线程|"
    r"gpu|compute|datacenter|nvidia|amd|chip|算力|数据中心)",
    re.IGNORECASE
)

BULL_KW = [
    "launch","released","unveils","debut","announces","introduces",
    "raises","secures","closes","funding","investment",
    "acquires","acquisition","partnership","beats","surpasses","outperforms",
    "breakthrough","record","first","new","open source","free",
    "achieved","reached","scaling","expanding","growth","soars","surge",
    "发布","推出","开源","融资","收购","突破","超越","增长","飙升",
    "上线","首个","重大","新模型","刷新","刷新纪录","创新高"
]
BEAR_KW = [
    "investigation","lawsuit","fine","penalty","ban","banned",
    "outage","failure","breach","leak","hack","delay","cancel","shutdown",
    "layoff","cut","slowdown","decline","loss","concern","scandal",
    "warning","risk","crackdown","regulation","crisis","plunge","crash",
    "调查","罚款","处罚","禁令","宕机","泄露","推迟","取消","关闭",
    "裁员","亏损","风险","警告","下跌","暴跌","崩溃","危机"
]

# ── 免费 Google Translate（无需 API key） ──────────────────────
def translate_to_zh(text):
    """英文 → 中文（Google Translate 公共接口）"""
    try:
        q = urllib.parse.quote(text[:4000])
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=en&tl=zh-CN&dt=t&q={q}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text[:200] + "（翻译失败）"

def translate_to_en(text):
    """中文 → 英文"""
    try:
        q = urllib.parse.quote(text[:4000])
        url = (
            f"https://translate.googleapis.com/translate_a/single"
            f"?client=gtx&sl=zh-CN&tl=en&dt=t&q={q}"
        )
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            return "".join(seg[0] for seg in data[0] if seg[0])
    except Exception:
        return text[:200] + "(translation failed)"

# ── 情感分析 ─────────────────────────────────────────────────
def get_sentiment(title, summary):
    text = f"{title} {summary}".lower()
    bull_score = sum(1 for kw in BULL_KW if kw.lower() in text)
    bear_score = sum(1 for kw in BEAR_KW if kw.lower() in text)
    diff = bull_score - bear_score
    if diff >= 2:
        return {"label": "利好", "type": "bull", "score": round(diff * 0.5, 1)}
    if diff <= -2:
        return {"label": "利空", "type": "bear", "score": round(diff * 0.5, 1)}
    strong_bull = any(k in text for k in [
        "launch","released","unveils","acquires","raises","surpasses",
        "发布","开源","突破","融资"])
    strong_bear = any(k in text for k in [
        "investigation","lawsuit","fine","ban","breach","outage","layoff",
        "调查","罚款","禁令"])
    if strong_bull:
        return {"label": "利好", "type": "bull", "score": 1.2}
    if strong_bear:
        return {"label": "利空", "type": "bear", "score": -1.2}
    return {"label": "中性", "type": "neutral", "score": 0}

def get_tags(title, summary):
    text = f"{title} {summary}".lower()
    tags = []
    rules = [
        (r"model|gpt|gemini|claude|llm|发布|新模型|v4|v5|3\.\d|deepseek|文心|通义|开源模型", "模型发布"),
        (r"agent|智能体|autonomous|automation|自动化", "AI Agent"),
        (r"fund|invest|acqui|raises|closes|series|ipo|上市|融资|收购", "投融资"),
        (r"regulation|policy|law|act|监管|法案|合规|政策", "监管政策"),
        (r"gpu|cpu|chip|compute|nvidia|amd|算力|数据中心|hardware|infrastructure|昇腾|芯片", "基础设施"),
        (r"china|chinese|百度|阿里|腾讯|字节|华为|国产|国内|本土", "中国动态"),
        (r"open.?source|open-source|apache|mit license", "开源"),
    ]
    for pat, tag in rules:
        if re.search(pat, text, re.IGNORECASE):
            tags.append(tag)
    return tags[:3] if tags else []

# ── 抓取 RSS ───────────────────────────────────────────────────
def strip_html(s):
    return re.sub(r"<[^>]+>", "", s or "").strip()

def fetch_feed(feed, seen):
    import feedparser
    try:
        resp = urllib.request.urlopen(
            urllib.request.Request(
                feed["url"],
                headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Weekly/2.0)"}
            ),
            timeout=15
        )
        raw = resp.read()
        fd = feedparser.parse(raw)
        results = []
        for e in fd.entries[:15]:
            title = strip_html(e.get("title", ""))
            summary = strip_html(e.get("summary", "") or e.get("description", ""))[:500]
            link = e.get("link", "")
            pub = e.get("published", "") or e.get("updated", "")
            if not is_ai_article(title, summary):
                continue
            h = hashlib.md5(link.encode()).hexdigest()[:12]
            if h in seen:
                continue
            seen.add(h)

            # ── 翻译逻辑 ──
            if feed["lang"] == "en":
                # 英文源：保留原文 + 翻译成中文
                title_zh = translate_to_zh(title)
                summary_zh = translate_to_zh(summary[:500])
                time.sleep(0.3)  # 避免触发频率限制
                title_display = f"{title}\n[中译] {title_zh}"
                summary_display = summary_zh
            else:
                # 中文源：保留原文 + 翻译成英文
                title_en = translate_to_en(title)
                time.sleep(0.3)
                title_display = f"{title}\n[EN] {title_en}"
                summary_display = summary

            sent = get_sentiment(title, summary)
            results.append({
                "id": h,
                "title": title_display.strip(),
                "summary": summary_display.strip(),
                "url": link,
                "source": feed["src"],
                "lang": feed["lang"],
                "tags": get_tags(title, summary),
                "sentiment": sent,
                "published": (pub[:25] or "") + " UTC",
                "fetched_at": datetime.now().isoformat(),
            })
        print(f"  {feed['src']}: {len(results)} AI-relevant articles")
        return results
    except Exception as ex:
        print(f"  ERR {feed['src']}: {ex}")
        return []

def is_ai_article(title, summary):
    text = f"{title} {summary}"
    return bool(AI_RE.search(text))

# ── 主流程 ───────────────────────────────────────────────────
def run():
    print("\n=== AI Weekly Report - Multilingual ===\n")
    seen = set()
    all_articles = []
    for feed in FEEDS:
        results = fetch_feed(feed, seen)
        all_articles.extend(results)

    # 去重
    unique = []
    seen2 = set()
    for a in all_articles:
        if a["id"] not in seen2:
            seen2.add(a["id"])
            unique.append(a)

    unique.sort(key=lambda x: x.get("published", ""), reverse=True)

    out = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "total_articles": len(unique),
            "sources": list({a["source"] for a in unique}),
            "multilingual": True,
        },
        "articles": unique,
    }
    out_path = OUT_DIR / "ai_weekly_data.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    from collections import Counter
    sent_dist = Counter(a["sentiment"]["type"] for a in unique)
    print(f"\n--- Summary ---")
    print(f"Total: {len(unique)} AI-relevant articles")
    print(f"Sources: {out['meta']['sources']}")
    print(f"Saved: {out_path}")
    print(f"Sentiment: {dict(sent_dist)}")
    print("\nTop articles (bilingual):")
    for i, a in enumerate(unique[:5], 1):
        tags_str = ",".join(a["tags"] or [])
        print(f"  [{i}] {a['source']} | {a['title'][:60]}")
        print(f"       Tags: {tags_str} | {a['sentiment']['label']} | Score: {a['sentiment']['score']}")
        print(f"       URL: {a['url'][:80]}")
    return len(unique)

if __name__ == "__main__":
    n = run()
    print(f"\nDone. {n} articles written.")
