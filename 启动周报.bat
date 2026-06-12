@echo off
chcp 65001 >nul 2>&1
title AI 行业周报 — 启动中...

echo ============================================================
echo   AI 行业周报 — 一键启动
echo ============================================================
echo.

cd /d "%~dp0"

:: 检查 Python
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.8+
    pause
    exit /b 1
)

:: 检查依赖
echo [1/3] 检查依赖...
python -c "import feedparser" >nul 2>&1 || pip install feedparser -q
python -c "import requests" >nul 2>&1 || pip install requests -q
python -c "import pptx" >nul 2>&1 || pip install python-pptx -q

:: Playwright (PDF 导出)
python -c "from playwright.sync_api import sync_playwright" >nul 2>&1
if errorlevel 1 (
    echo [提示] 安装 Playwright (PDF导出需要)...
    pip install playwright -q
    python -m playwright install chromium >nul 2>&1
)

echo [2/3] 依赖检查完成
echo.

echo [3/3] 启动服务器...
echo.
echo ============================================================
echo   浏览器将自动打开 http://localhost:8899
echo   页面加载时自动抓取最近 7 天数据
echo   点击"更新数据"按钮可重新抓取
echo   点击"导出 PDF/PPT"保存到桌面
echo   按 Ctrl+C 停止服务器
echo ============================================================
echo.

python server.py --port 8899

pause
