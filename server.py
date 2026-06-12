#!/usr/bin/env python3
"""
AI 行业周报 — 本地服务器
=============================
功能:
  - 双击启动，自动打开浏览器
  - 页面加载时自动抓取最近7天数据
  - 点击"更新数据"按钮触发抓取
  - 一键导出 PDF / PPT 到桌面

用法:
  python server.py              # 启动服务器并打开浏览器
  python server.py --port 8899  # 指定端口
  python server.py --no-open    # 不自动打开浏览器
"""

import http.server
import json
import os
import sys
import subprocess
import threading
import time
import webbrowser
import argparse
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse, parse_qs

# ============================================================
# 配置
# ============================================================

BASE_DIR = Path(__file__).parent.resolve()
DATA_FILE = BASE_DIR / "ai_weekly_data.json"
HISTORY_DIR = BASE_DIR / "history"
SCRAPER_FILE = BASE_DIR / "ai_scraper.py"
SENTIMENT_FILE = BASE_DIR / "ai_sentiment.py"
REPORT_HTML = BASE_DIR / "report.html"
DESKTOP = Path.home() / "Desktop"

PORT = 8899

# ============================================================
# 历史数据管理
# ============================================================

def save_to_history():
    """将当前数据保存到 history/ 目录，按年-周命名"""
    if not DATA_FILE.exists():
        return None
    HISTORY_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    # 文件名: 2026-W24.json
    week_str = f"{now.strftime('%Y')}-W{now.strftime('%V')}"
    dest = HISTORY_DIR / f"{week_str}.json"
    import shutil
    shutil.copy2(str(DATA_FILE), str(dest))
    print(f"📦 历史归档: {dest.name}")
    return str(dest)


def get_last_week_file():
    """查找上一周的历史数据文件"""
    if not HISTORY_DIR.exists():
        return None
    files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
    # 排除当前周的文件
    now = datetime.now()
    current_week = f"{now.strftime('%Y')}-W{now.strftime('%V')}"
    for f in files:
        if f.stem != current_week:
            return f
    return None

# ============================================================
# 抓取 + 分析
# ============================================================

_fetch_lock = threading.Lock()
_last_fetch_time = None
_fetch_status = {"running": False, "last_time": None, "error": None}


def run_scrape_and_analyze():
    """执行抓取 → 情感分析流水线"""
    global _last_fetch_time
    with _fetch_lock:
        _fetch_status["running"] = True
        _fetch_status["error"] = None
        try:
            # 将当前数据归档到 history/
            save_to_history()

            # Step 1: 抓取
            print("\n📡 正在抓取最近7天数据...")
            r = subprocess.run(
                [sys.executable, str(SCRAPER_FILE), "--clear-cache"],
                capture_output=True, text=True, cwd=str(BASE_DIR), timeout=30
            )
            r = subprocess.run(
                [sys.executable, str(SCRAPER_FILE)],
                capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120
            )
            if r.returncode != 0:
                print(f"  ⚠ 抓取警告: {r.stderr[-300:]}")

            # Step 2: 情感分析
            print("🧠 正在进行情感分析...")
            r2 = subprocess.run(
                [sys.executable, str(SENTIMENT_FILE)],
                capture_output=True, text=True, cwd=str(BASE_DIR), timeout=60
            )
            if r2.returncode != 0:
                print(f"  ⚠ 情感分析警告: {r2.stderr[-200:]}")

            # Step 3: 将新数据也归档
            save_to_history()

            _last_fetch_time = datetime.now().isoformat()
            _fetch_status["last_time"] = _last_fetch_time
            print(f"✅ 数据更新完成: {_last_fetch_time}")

        except Exception as e:
            _fetch_status["error"] = str(e)
            print(f"❌ 抓取异常: {e}")
        finally:
            _fetch_status["running"] = False


# ============================================================
# 翻译代理
# ============================================================

_translate_cache = {}

def do_translate(text, target_lang="zh-CN"):
    """翻译文本 — 多源备选"""
    import urllib.request
    import urllib.parse

    if not text or len(text) < 3:
        return text, "passthrough"

    cache_key = f"{target_lang}|{text[:100]}"
    if cache_key in _translate_cache:
        return _translate_cache[cache_key], "cache"

    # 方案1: Google Translate 公共接口
    try:
        encoded = urllib.parse.quote(text[:3000])
        url = f"https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl={target_lang}&dt=t&q={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Referer": "https://translate.google.com/",
        })
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            result = "".join(s[0] for s in (data[0] or []) if s[0])
            if result and result != text:
                _translate_cache[cache_key] = result
                return result, "google"
    except Exception as e:
        print(f"  [Google翻译] 不可用: {str(e)[:60]}")

    # 方案2: MyMemory (免费)
    try:
        from_lang = "zh" if any('\u4e00' <= c <= '\u9fff' for c in text) else "en"
        encoded = urllib.parse.quote(text[:500])
        url = f"https://api.mymemory.translated.net/get?q={encoded}&langpair={from_lang}|{target_lang.replace('-CN','')}&de=bot@example.com"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("responseStatus") == 200:
                result = data.get("responseData", {}).get("translatedText", "")
                if result and result != text:
                    _translate_cache[cache_key] = result
                    return result, "mymemory"
    except Exception as e:
        print(f"  [MyMemory] 不可用: {str(e)[:60]}")

    return text, "failed"


# ============================================================
# PDF / PPT 导出
# ============================================================

def export_pdf():
    """使用 Playwright 将 HTML 转为 PDF"""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "playwright 未安装，请运行: pip install playwright && playwright install chromium"

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = DESKTOP / f"AI行业周报_{timestamp}.pdf"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        file_url = f"file:///{REPORT_HTML.resolve().as_posix()}"
        page.goto(file_url, wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(2000)
        page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={"top": "10mm", "bottom": "10mm", "left": "8mm", "right": "8mm"},
        )
        browser.close()

    return str(output_path), None


def export_ppt():
    """使用 python-pptx 生成 PPT"""
    try:
        from pptx import Presentation
        from pptx.util import Inches, Pt, Emu
        from pptx.dml.color import RGBColor
        from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
    except ImportError:
        return None, "python-pptx 未安装，请运行: pip install python-pptx"

    # 读取数据
    try:
        data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    except Exception:
        data = {"articles": [], "meta": {}}

    articles = data.get("articles", [])
    meta = data.get("meta", {})
    stats = data.get("sentiment_stats", data.get("stats", {}))

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    BG_COLOR = RGBColor(10, 14, 26)
    CARD_COLOR = RGBColor(17, 24, 39)
    ACCENT = RGBColor(59, 130, 246)
    WHITE = RGBColor(248, 250, 252)
    GRAY = RGBColor(148, 163, 184)
    GREEN = RGBColor(16, 185, 129)
    RED = RGBColor(239, 68, 68)
    YELLOW = RGBColor(245, 158, 11)
    PURPLE = RGBColor(139, 92, 246)

    def set_slide_bg(slide, color):
        bg = slide.background
        fill = bg.fill
        fill.solid()
        fill.fore_color.rgb = color

    def add_text_box(slide, left, top, width, height, text, font_size=18,
                     color=WHITE, bold=False, alignment=PP_ALIGN.LEFT):
        txBox = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = text
        p.font.size = Pt(font_size)
        p.font.color.rgb = color
        p.font.bold = bold
        p.alignment = alignment
        return txBox

    def add_rect(slide, left, top, width, height, fill_color):
        from pptx.util import Emu
        shape = slide.shapes.add_shape(
            1,  # MSO_SHAPE.RECTANGLE
            Inches(left), Inches(top), Inches(width), Inches(height)
        )
        shape.fill.solid()
        shape.fill.fore_color.rgb = fill_color
        shape.line.fill.background()
        return shape

    # ── Slide 1: 封面 ──
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    set_slide_bg(slide, BG_COLOR)
    add_text_box(slide, 1, 1.5, 11, 1.5, "AI 行业周报", 54, ACCENT, True, PP_ALIGN.CENTER)
    add_text_box(slide, 1, 3.2, 11, 0.8, "多源聚合 · 真实数据 · 情感分析 · 趋势洞察", 22, GRAY, False, PP_ALIGN.CENTER)
    week_range = f"{meta.get('week_start', '')} ~ {meta.get('week_end', '')}"
    add_text_box(slide, 1, 4.2, 11, 0.6, week_range, 18, RGBColor(100, 116, 139), False, PP_ALIGN.CENTER)
    add_text_box(slide, 1, 5.0, 11, 0.5, f"共 {len(articles)} 条新闻 · 生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}", 14, RGBColor(71, 85, 105), False, PP_ALIGN.CENTER)

    # ── Slide 2: KPI 概览 ──
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, BG_COLOR)
    add_text_box(slide, 0.5, 0.3, 12, 0.7, "📊 本周 KPI 概览", 32, WHITE, True)

    bull = len([a for a in articles if (a.get("sentiment", {}) or {}).get("type") == "bull" or "利好" in str((a.get("sentiment", {}) or {}).get("sentiment", ""))])
    bear = len([a for a in articles if (a.get("sentiment", {}) or {}).get("type") == "bear" or "利空" in str((a.get("sentiment", {}) or {}).get("sentiment", ""))])
    sources = len(set(a.get("source", "") for a in articles))
    china = len([a for a in articles if "中国动态" in str(a.get("tags", []))])
    neu = len(articles) - bull - bear

    kpis = [
        (f"{len(articles)}", "本周新闻", ACCENT),
        (f"{sources}", "数据来源", PURPLE),
        (f"{bull}", "利好信号", GREEN),
        (f"{bear}", "利空信号", RED),
        (f"{china}", "中国动态", RGBColor(6, 182, 212)),
    ]

    card_w = 2.2
    gap = 0.3
    total_w = len(kpis) * card_w + (len(kpis) - 1) * gap
    start_x = (13.333 - total_w) / 2

    for i, (num, label, color) in enumerate(kpis):
        x = start_x + i * (card_w + gap)
        add_rect(slide, x, 1.5, card_w, 2.0, CARD_COLOR)
        add_text_box(slide, x, 1.7, card_w, 1.0, num, 42, color, True, PP_ALIGN.CENTER)
        add_text_box(slide, x, 2.8, card_w, 0.5, label, 14, GRAY, False, PP_ALIGN.CENTER)

    # 情感分布条
    total = len(articles) or 1
    add_text_box(slide, 0.8, 4.2, 11, 0.5, "情感分布", 20, WHITE, True)

    bar_y = 4.9
    bar_h = 0.6
    bar_total_w = 11.0
    if total > 0:
        bull_w = bull / total * bar_total_w
        neu_w = neu / total * bar_total_w
        bear_w = bear / total * bar_total_w
        if bull_w > 0:
            add_rect(slide, 0.8, bar_y, max(bull_w, 0.1), bar_h, GREEN)
        if neu_w > 0:
            add_rect(slide, 0.8 + bull_w, bar_y, max(neu_w, 0.1), bar_h, YELLOW)
        if bear_w > 0:
            add_rect(slide, 0.8 + bull_w + neu_w, bar_y, max(bear_w, 0.1), bar_h, RED)

    add_text_box(slide, 0.8, 5.7, 11, 0.4, f"🟢 利好 {bull} ({round(bull/total*100)}%)  🟡 中性 {neu} ({round(neu/total*100)}%)  🔴 利空 {bear} ({round(bear/total*100)}%)", 14, GRAY)

    # ── Slide 3+: 新闻详情 (每页5条) ──
    per_page = 5
    for page_idx in range(0, len(articles), per_page):
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        set_slide_bg(slide, BG_COLOR)
        page_arts = articles[page_idx:page_idx + per_page]
        title_text = f"📰 AI 新闻 ({page_idx + 1}-{min(page_idx + per_page, len(articles))} / {len(articles)})"
        add_text_box(slide, 0.5, 0.3, 12, 0.7, title_text, 28, WHITE, True)

        y = 1.2
        for art in page_arts:
            sent = art.get("sentiment", {}) or {}
            sent_text = sent.get("sentiment", sent.get("label", ""))
            if "利好" in str(sent_text) or sent.get("type") == "bull":
                sent_color = GREEN
            elif "利空" in str(sent_text) or sent.get("type") == "bear":
                sent_color = RED
            else:
                sent_color = YELLOW

            title = (art.get("title", "") or "")[:80]
            summary = (art.get("summary", "") or "")[:120]
            source = art.get("source", "")
            pub = (art.get("published", "") or "")[:16]
            tags = ", ".join(art.get("tags", [])[:3])

            # Sentiment badge
            add_rect(slide, 0.7, y, 0.08, 0.9, sent_color)

            add_text_box(slide, 1.0, y, 9, 0.35, title, 16, WHITE, True)
            add_text_box(slide, 1.0, y + 0.35, 9, 0.3, summary, 11, GRAY)
            meta_text = f"{source} · {pub}"
            if tags:
                meta_text += f"  [{tags}]"
            add_text_box(slide, 1.0, y + 0.65, 9, 0.25, meta_text, 10, RGBColor(71, 85, 105))

            add_text_box(slide, 10.5, y + 0.1, 2.5, 0.3, sent_text.split()[-1] if " " in str(sent_text) else str(sent_text), 12, sent_color, True, PP_ALIGN.RIGHT)

            y += 1.15

    # ── 最后一页: 页脚 ──
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_bg(slide, BG_COLOR)
    add_text_box(slide, 1, 2.5, 11, 1, "AI 行业周报", 48, ACCENT, True, PP_ALIGN.CENTER)
    add_text_box(slide, 1, 3.8, 11, 0.5, "数据来源: IT之家 · 机器之心 · TechCrunch · The Verge · Wired · AI News", 16, GRAY, False, PP_ALIGN.CENTER)
    add_text_box(slide, 1, 4.5, 11, 0.5, "内容由 AI 自动聚合，仅供参考", 14, RGBColor(71, 85, 105), False, PP_ALIGN.CENTER)

    # 保存
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = DESKTOP / f"AI行业周报_{timestamp}.pptx"
    prs.save(str(output_path))
    return str(output_path), None


# ============================================================
# HTTP 请求处理器
# ============================================================

class ReportHandler(http.server.SimpleHTTPRequestHandler):
    """自定义 HTTP 处理器"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 路由: 首页 → report.html
        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(REPORT_HTML.read_bytes())
            return

        # API: 触发数据抓取
        if path == "/api/fetch":
            if _fetch_status["running"]:
                self._json_response({"status": "running", "message": "正在抓取中..."})
            else:
                # 后台线程执行抓取
                t = threading.Thread(target=run_scrape_and_analyze, daemon=True)
                t.start()
                self._json_response({"status": "started", "message": "数据抓取已启动"})
            return

        # API: 抓取状态
        if path == "/api/status":
            self._json_response(_fetch_status)
            return

        # API: 导出 PDF
        if path == "/api/export/pdf":
            try:
                result, err = export_pdf()
                if err:
                    self._json_response({"status": "error", "message": err})
                else:
                    self._json_response({"status": "ok", "path": result, "message": f"PDF 已保存到桌面: {Path(result).name}"})
            except Exception as e:
                self._json_response({"status": "error", "message": str(e)})
            return

        # API: 导出 PPT
        if path == "/api/export/ppt":
            try:
                result, err = export_ppt()
                if err:
                    self._json_response({"status": "error", "message": err})
                else:
                    self._json_response({"status": "ok", "path": result, "message": f"PPT 已保存到桌面: {Path(result).name}"})
            except Exception as e:
                self._json_response({"status": "error", "message": str(e)})
            return

        # API: 翻译代理
        if path == "/api/translate":
            qs = parse_qs(parsed.query)
            text = (qs.get("text", [""])[0] or "").strip()
            tl = qs.get("tl", ["zh-CN"])[0]
            if not text:
                self._json_response({"error": "text required"}, 400)
                return
            result, source = do_translate(text, tl)
            self._json_response({"translatedText": result, "source": source})
            return

        # API: 获取上周数据（自动从 history 查找）
        if path == "/api/last-week":
            last_file = get_last_week_file()
            if last_file and last_file.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(last_file.read_bytes())
            else:
                self._json_response({"articles": [], "meta": {}, "note": "no history yet"})
            return

        # API: 历史数据列表
        if path == "/api/history":
            if not HISTORY_DIR.exists():
                self._json_response({"files": []})
                return
            files = sorted(HISTORY_DIR.glob("*.json"), reverse=True)
            result = []
            for f in files:
                try:
                    d = json.loads(f.read_text("utf-8"))
                    meta = d.get("meta", {})
                    result.append({
                        "filename": f.name,
                        "week": f.stem,
                        "articles": meta.get("total_articles", len(d.get("articles", []))),
                        "generated": meta.get("generated_at", ""),
                    })
                except:
                    result.append({"filename": f.name, "week": f.stem})
            self._json_response({"files": result})
            return

        # 静态文件: ai_weekly_data.json
        if path == "/ai_weekly_data.json":
            if DATA_FILE.exists():
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                self.wfile.write(DATA_FILE.read_bytes())
            else:
                self._json_response({"articles": [], "meta": {}}, 404)
            return

        # 其他静态文件
        super().do_GET()

    def _json_response(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # 简化日志
        if "/api/" in str(args[0]) if args else False:
            print(f"  📡 {args[0]}")
        elif ".json" in str(args[0]) if args else False:
            pass  # 静默json请求
        else:
            super().log_message(format, *args)


# ============================================================
# 启动
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI 行业周报服务器")
    parser.add_argument("--port", type=int, default=PORT, help=f"端口号 (默认: {PORT})")
    parser.add_argument("--no-open", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--fetch-now", action="store_true", help="启动时立即抓取数据")
    args = parser.parse_args()

    port = args.port

    print(f"\n{'='*55}")
    print(f"  🤖 AI 行业周报 — 本地服务器")
    print(f"  端口: {port}")
    print(f"  地址: http://localhost:{port}")
    print(f"  桌面: {DESKTOP}")
    print(f"{'='*55}\n")

    # 检查依赖
    deps = []
    try:
        import playwright
        deps.append("✅ Playwright (PDF导出)")
    except ImportError:
        deps.append("⚠  Playwright 未安装 — PDF导出不可用")

    try:
        import pptx
        deps.append("✅ python-pptx (PPT导出)")
    except ImportError:
        deps.append("⚠  python-pptx 未安装 — PPT导出不可用")

    for d in deps:
        print(f"  {d}")
    print()

    # 如果数据文件不存在或启动时抓取
    if args.fetch_now or not DATA_FILE.exists():
        print("📡 启动时抓取数据...")
        t = threading.Thread(target=run_scrape_and_analyze, daemon=True)
        t.start()

    # 启动服务器
    server = http.server.HTTPServer(("0.0.0.0", port), ReportHandler)

    def open_browser():
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{port}")

    if not args.no_open:
        threading.Thread(target=open_browser, daemon=True).start()

    print(f"🌐 服务器已启动: http://localhost:{port}")
    print(f"   按 Ctrl+C 停止\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 服务器已停止")
        server.server_close()


if __name__ == "__main__":
    main()
