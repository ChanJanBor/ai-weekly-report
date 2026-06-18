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
    """将当前数据保存到 history/ 目录，按年-周命名（仅首次保存）"""
    if not DATA_FILE.exists():
        return None, False
    HISTORY_DIR.mkdir(exist_ok=True)
    now = datetime.now()
    week_str = f"{now.strftime('%Y')}-W{now.strftime('%V')}"
    dest = HISTORY_DIR / f"{week_str}.json"
    # 如果历史文件已存在，说明本周已保存过，跳过
    if dest.exists():
        print(f"📦 历史归档已存在: {dest.name}（跳过）")
        return str(dest), False
    import shutil
    shutil.copy2(str(DATA_FILE), str(dest))
    print(f"📦 历史归档: {dest.name}")
    return str(dest), True


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
            # 归档当前数据到 history/（仅首次，避免重复保存）
            save_to_history()

            # Step 1: 抓取新数据（自动与已有数据合并）
            print("\n📡 正在抓取最近7天数据...")
            r = subprocess.run(
                [sys.executable, str(SCRAPER_FILE)],
                capture_output=True, text=True, cwd=str(BASE_DIR), timeout=180
            )
            if r.returncode != 0:
                print(f"  ⚠ 抓取警告: {r.stderr[-300:]}")
            else:
                # 打印关键输出
                for line in r.stdout.split('\n'):
                    if '抓取完成' in line or '合并' in line or '数据已保存' in line:
                        print(f"  {line.strip()}")

            # Step 2: 情感分析
            print("🧠 正在进行情感分析...")
            r2 = subprocess.run(
                [sys.executable, str(SENTIMENT_FILE)],
                capture_output=True, text=True, cwd=str(BASE_DIR), timeout=60
            )
            if r2.returncode != 0:
                print(f"  ⚠ 情感分析警告: {r2.stderr[-200:]}")

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
    """生成 PDF"""
    try:
        from export_engine import export_pdf as _export_pdf
        return _export_pdf(DATA_FILE, DESKTOP)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, str(e)


def export_ppt():
    """生成可编辑 PPT"""
    try:
        from export_engine import export_ppt as _export_ppt
        return _export_ppt(DATA_FILE, DESKTOP)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return None, str(e)


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

        # API: 强制刷新（清除缓存后抓取）
        if path == "/api/fetch/force":
            if _fetch_status["running"]:
                self._json_response({"status": "running", "message": "正在抓取中..."})
            else:
                # 先清除缓存
                cache_file = BASE_DIR / "ai_news_cache.json"
                if cache_file.exists():
                    cache_file.write_text("{}", encoding="utf-8")
                    print("🗑️ 缓存已清除（强制刷新）")
                t = threading.Thread(target=run_scrape_and_analyze, daemon=True)
                t.start()
                self._json_response({"status": "started", "message": "强制刷新已启动"})
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
