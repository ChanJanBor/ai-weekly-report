#!/usr/bin/env python3
"""
AI Weekly Report Scheduler & Push
定时推送调度器 — 邮件/飞书/微信多通道发送
=============================================
用法:
    python ai_scheduler.py --setup           # 交互式配置
    python ai_scheduler.py --send-email       # 发送邮件
    python ai_scheduler.py --send-feishu      # 发送飞书
    python ai_scheduler.py --run              # 完整流水线: 抓取→分析→导出→推送
    python ai_scheduler.py --test             # 测试各通道连接
    python ai_scheduler.py --cron-setup       # 生成 Windows 计划任务配置
"""

import json
import os
import sys
import smtplib
import argparse
import subprocess
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List


# ============================================================
# 配置管理
# ============================================================

CONFIG_FILE = Path(__file__).parent / "ai_scheduler_config.json"

DEFAULT_CONFIG = {
    "email": {
        "enabled": False,
        "smtp_server": "smtp.gmail.com",
        "smtp_port": 587,
        "use_tls": True,
        "sender": "",
        "password": "",
        "recipients": [],
        "subject_template": "AI行业周报 | {date_range}",
    },
    "feishu": {
        "enabled": False,
        "webhook_url": "",     # 飞书机器人 Webhook URL
        "chat_id": "",          # 飞书群聊ID (可选)
    },
    "wechat": {
        "enabled": False,
        "channel": "openclaw-weixin",
        "target": "",           # 微信接收者ID
    },
    "schedule": {
        "day_of_week": 5,       # 周五 (0=Mon, 6=Sun)
        "hour": 18,             # 下午6点
        "minute": 0,
        "timezone": "Asia/Shanghai",
    },
    "pipeline": {
        "auto_scrape": True,
        "auto_sentiment": True,
        "auto_export_pdf": True,
        "auto_export_docx": True,
        "clean_old_exports_days": 30,
    },
    "watchlist": {
        "companies": ["OpenAI", "Anthropic", "Google", "DeepSeek", "百度", "阿里", "腾讯", "字节跳动", "智谱", "月之暗面"],
        "topics": ["大模型发布", "AI Agent", "芯片/算力", "融资/IPO", "开源模型", "监管政策", "AI安全", "具身智能"],
    },
}


def load_config() -> dict:
    if CONFIG_FILE.exists():
        cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        # 深度合并默认值
        for key in DEFAULT_CONFIG:
            if key not in cfg:
                cfg[key] = DEFAULT_CONFIG[key]
            elif isinstance(DEFAULT_CONFIG[key], dict):
                for subkey in DEFAULT_CONFIG[key]:
                    if subkey not in cfg[key]:
                        cfg[key][subkey] = DEFAULT_CONFIG[key][subkey]
        return cfg
    return dict(DEFAULT_CONFIG)


def save_config(cfg: dict):
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


# ============================================================
# 邮件发送
# ============================================================

def send_email(cfg: dict, html_path: str = None, pdf_path: str = None) -> bool:
    """发送周报到邮箱"""
    email_cfg = cfg["email"]
    if not email_cfg["enabled"]:
        print("⚠ 邮件功能未启用。请先运行 --setup 配置。")
        return False
    if not email_cfg["sender"] or not email_cfg["password"]:
        print("❌ 邮件配置不完整 (缺少 sender/password)")
        return False

    # 构建邮件
    msg = MIMEMultipart("mixed")
    msg["From"] = email_cfg["sender"]
    msg["To"] = ", ".join(email_cfg["recipients"])
    msg["Subject"] = email_cfg["subject_template"].format(
        date_range=datetime.now().strftime("%Y.%m.%d")
    )

    # HTML 正文
    if html_path and Path(html_path).exists():
        html_body = Path(html_path).read_text(encoding="utf-8")
    else:
        html_body = "<h2>AI 行业周报</h2><p>请查看附件。</p>"
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    # PDF 附件
    if pdf_path and Path(pdf_path).exists():
        with open(pdf_path, "rb") as f:
            part = MIMEBase("application", "pdf")
            part.set_payload(f.read())
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f'attachment; filename="{Path(pdf_path).name}"'
            )
            msg.attach(part)

    # 发送
    try:
        with smtplib.SMTP(email_cfg["smtp_server"], email_cfg["smtp_port"], timeout=30) as server:
            if email_cfg["use_tls"]:
                server.starttls()
            server.login(email_cfg["sender"], email_cfg["password"])
            server.sendmail(email_cfg["sender"], email_cfg["recipients"], msg.as_string())
        print(f"✅ 邮件已发送 → {', '.join(email_cfg['recipients'])}")
        return True
    except Exception as e:
        print(f"❌ 邮件发送失败: {e}")
        return False


# ============================================================
# 飞书推送
# ============================================================

def send_feishu(cfg: dict, report_url: str = None) -> bool:
    """推送周报到飞书群 (通过 Webhook 机器人)"""
    feishu_cfg = cfg["feishu"]
    if not feishu_cfg["enabled"]:
        print("⚠ 飞书推送未启用")
        return False
    if not feishu_cfg["webhook_url"]:
        print("❌ 飞书 Webhook URL 未配置")
        return False

    import requests

    # 构建飞书富文本消息卡片
    card = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "🤖 AI 行业周报"},
                "template": "blue",
            },
            "elements": [
                {
                    "tag": "markdown",
                    "content": f"**📅 {datetime.now().strftime('%Y.%m.%d')}**\n\n"
                               f"本周AI行业最新动态已生成，包含：\n"
                               f"- 📰 热点新闻速览\n"
                               f"- 📈 趋势信号分析\n"
                               f"- 💰 模型价格对比\n"
                               f"- 🇨🇳 中国动态追踪\n"
                               f"- 📊 数据看板仪表盘",
                },
                {
                    "tag": "action",
                    "actions": [
                        {
                            "tag": "button",
                            "text": {"tag": "plain_text", "content": "📄 查看完整周报"},
                            "type": "primary",
                            "url": report_url or "https://example.com/report",
                        }
                    ],
                },
            ],
        },
    }

    try:
        resp = requests.post(feishu_cfg["webhook_url"], json=card, timeout=10)
        resp.raise_for_status()
        result = resp.json()
        if result.get("code") == 0:
            print("✅ 飞书消息已推送")
            return True
        else:
            print(f"❌ 飞书推送失败: {result}")
            return False
    except Exception as e:
        print(f"❌ 飞书推送异常: {e}")
        return False


# ============================================================
# 完整流水线
# ============================================================

def run_pipeline(cfg: dict):
    """执行完整流水线: 抓取→分析→导出→推送"""
    base_dir = Path(__file__).parent
    print(f"\n{'='*60}")
    print(f"  🚀 AI Weekly Report Pipeline")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    results = {}

    # Step 1: 抓取
    if cfg["pipeline"]["auto_scrape"]:
        print("📡 [1/5] 新闻抓取...")
        scraper_path = base_dir / "ai_scraper.py"
        if scraper_path.exists():
            r = subprocess.run([sys.executable, str(scraper_path)], capture_output=True, text=True)
            print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
            results["scrape"] = r.returncode == 0
        else:
            print("  ⚠ ai_scraper.py 未找到，跳过")
            results["scrape"] = False

    # Step 2: 情感分析
    if cfg["pipeline"]["auto_sentiment"]:
        print("\n🧠 [2/5] 情感分析...")
        sentiment_path = base_dir / "ai_sentiment.py"
        if sentiment_path.exists():
            r = subprocess.run([sys.executable, str(sentiment_path)], capture_output=True, text=True)
            print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
            results["sentiment"] = r.returncode == 0
        else:
            print("  ⚠ ai_sentiment.py 未找到，跳过")
            results["sentiment"] = False

    # Step 3: 导出 PDF/DOCX
    print("\n📄 [3/5] 文档导出...")
    export_path = base_dir / "ai_export.py"
    html_path = base_dir / "ai_weekly_report.html"
    if export_path.exists() and html_path.exists():
        r = subprocess.run(
            [sys.executable, str(export_path), "--html", str(html_path), "--format", "all"],
            capture_output=True, text=True
        )
        print(r.stdout[-500:] if len(r.stdout) > 500 else r.stdout)
        results["export"] = r.returncode == 0
    else:
        print("  ⚠ ai_export.py 未找到，跳过")
        results["export"] = False

    # Step 4: 邮件推送
    print("\n📧 [4/5] 邮件推送...")
    pdf_dir = base_dir / "exports"
    latest_pdf = None
    if pdf_dir.exists():
        pdfs = sorted(pdf_dir.glob("*.pdf"), key=lambda p: p.stat().st_mtime, reverse=True)
        if pdfs:
            latest_pdf = str(pdfs[0])
    results["email"] = send_email(cfg, str(html_path) if html_path.exists() else None, latest_pdf)

    # Step 5: 飞书推送
    print("\n📱 [5/5] 飞书推送...")
    results["feishu"] = send_feishu(cfg)

    # 总结
    print(f"\n{'='*60}")
    print(f"  Pipeline 完成")
    print(f"{'='*60}")
    for step, ok in results.items():
        status = "✅" if ok else "❌"
        print(f"  {status} {step}")
    print()


# ============================================================
# 交互式配置
# ============================================================

def interactive_setup():
    """交互式配置向导"""
    cfg = load_config()
    print("\n🔧 AI Weekly Report — 配置向导\n")

    # 邮件配置
    print("─ 邮件配置 ─")
    use_email = input("启用邮件推送? (y/N): ").strip().lower() == 'y'
    cfg["email"]["enabled"] = use_email
    if use_email:
        cfg["email"]["smtp_server"] = input(f"  SMTP服务器 [{cfg['email']['smtp_server']}]: ") or cfg["email"]["smtp_server"]
        cfg["email"]["sender"] = input(f"  发件邮箱: ") or cfg["email"]["sender"]
        cfg["email"]["password"] = input(f"  邮箱密码/授权码: ") or cfg["email"]["password"]
        rcpts = input(f"  收件人(逗号分隔): ") or ""
        if rcpts:
            cfg["email"]["recipients"] = [r.strip() for r in rcpts.split(",")]

    # 飞书配置
    print("\n─ 飞书配置 ─")
    use_feishu = input("启用飞书推送? (y/N): ").strip().lower() == 'y'
    cfg["feishu"]["enabled"] = use_feishu
    if use_feishu:
        cfg["feishu"]["webhook_url"] = input(f"  飞书机器人 Webhook URL: ") or cfg["feishu"]["webhook_url"]

    # 调度配置
    print("\n─ 调度配置 ─")
    cfg["schedule"]["day_of_week"] = int(input(f"  每周几发送 (0=周一, 4=周五) [{cfg['schedule']['day_of_week']}]: ") or cfg["schedule"]["day_of_week"])
    cfg["schedule"]["hour"] = int(input(f"  发送时间(小时, 0-23) [{cfg['schedule']['hour']}]: ") or cfg["schedule"]["hour"])

    save_config(cfg)
    print(f"\n✅ 配置已保存: {CONFIG_FILE}")


# ============================================================
# Windows 计划任务
# ============================================================

def generate_cron_config():
    """生成 Windows 计划任务 XML 和 Web Cron 配置"""
    cfg = load_config()
    base_dir = Path(__file__).parent

    # PowerShell 脚本
    ps_script = rf'''# AI Weekly Report — Windows Scheduled Task
# 自动执行: 抓取 → 分析 → 导出 → 推送
$ErrorActionPreference = "Stop"
$scriptDir = "{base_dir}"
$logFile = Join-Path $scriptDir "logs\scheduler_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

New-Item -ItemType Directory -Force -Path (Split-Path $logFile) | Out-Null

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) {{ $python = "python" }}

& $python "$scriptDir\ai_scheduler.py" --run 2>&1 | Tee-Object -FilePath $logFile
$exitCode = $LASTEXITCODE
Add-Content -Path $logFile -Value "Exit code: $exitCode @ $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')"
exit $exitCode
'''
    ps_path = base_dir / "run_weekly_report.ps1"
    ps_path.write_text(ps_script, encoding="utf-8")
    print(f"✅ PowerShell 脚本: {ps_path}")

    # Windows 计划任务命令
    task_name = "AI Weekly Report Pipeline"
    hours = f"{cfg['schedule']['hour']:02d}:{cfg['schedule']['minute']:02d}"
    days = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
    day = days[cfg['schedule']['day_of_week']]

    schtasks_cmd = (
        f'schtasks /Create /TN "{task_name}" '
        f'/TR "powershell.exe -ExecutionPolicy Bypass -File \\"{ps_path}\\"" '
        f'/SC WEEKLY /D {day} /ST {hours} /F'
    )
    print(f"\n📋 Windows 计划任务命令:")
    print(f"   {schtasks_cmd}")
    print(f"\n   或在 PowerShell 管理员窗口执行上述命令即可创建定时任务")

    # Web Cron (OpenClaw) 配置
    web_cron = {
        "name": "AI Weekly Report Pipeline",
        "schedule": {
            "kind": "cron",
            "expr": f"{cfg['schedule']['minute']} {cfg['schedule']['hour']} * * {cfg['schedule']['day_of_week']}",
            "tz": cfg["schedule"]["timezone"],
        },
        "payload": {
            "kind": "agentTurn",
            "message": f"执行 AI 周报完整流水线: 运行 {base_dir / 'ai_scheduler.py'} --run",
            "timeoutSeconds": 600,
        },
        "delivery": {
            "mode": "announce",
            "channel": cfg["wechat"]["channel"] if cfg["wechat"]["enabled"] else "",
        },
        "sessionTarget": "isolated",
    }

    cron_config_path = base_dir / "ai_cron_config.json"
    cron_config_path.write_text(json.dumps(web_cron, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📋 Web Cron 配置: {cron_config_path}")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="AI Weekly Report Scheduler & Push")
    parser.add_argument("--setup", action="store_true", help="交互式配置")
    parser.add_argument("--run", action="store_true", help="执行完整流水线")
    parser.add_argument("--send-email", action="store_true", help="仅发送邮件")
    parser.add_argument("--send-feishu", action="store_true", help="仅推送飞书")
    parser.add_argument("--test", action="store_true", help="测试通道连接")
    parser.add_argument("--cron-setup", action="store_true", help="生成计划任务配置")
    parser.add_argument("--show-config", action="store_true", help="显示当前配置")
    parser.add_argument("--html", default=None, help="指定HTML周报路径")
    args = parser.parse_args()

    cfg = load_config()

    if args.show_config:
        print(json.dumps(cfg, ensure_ascii=False, indent=2))
        return

    if args.setup:
        interactive_setup()
        return

    if args.run:
        run_pipeline(cfg)
        return

    if args.send_email:
        html = args.html or str(Path(__file__).parent / "ai_weekly_report.html")
        send_email(cfg, html)
        return

    if args.send_feishu:
        send_feishu(cfg)
        return

    if args.cron_setup:
        generate_cron_config()
        return

    if args.test:
        print("🔍 测试通道连接...\n")
        print("📧 邮件:", "✅ 已配置" if cfg["email"]["enabled"] and cfg["email"]["sender"] else "❌ 未配置")
        print("📱 飞书:", "✅ 已配置" if cfg["feishu"]["enabled"] and cfg["feishu"]["webhook_url"] else "❌ 未配置")
        print(f"\n📋 定时: 每周{['一','二','三','四','五','六','日'][cfg['schedule']['day_of_week']]} "
              f"{cfg['schedule']['hour']:02d}:{cfg['schedule']['minute']:02d}")
        return

    parser.print_help()


if __name__ == "__main__":
    main()