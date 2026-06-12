@echo off
REM AI 周报翻译代理 - 启动脚本
REM 双击运行即可启动翻译服务

cd /d "C:\Users\Administrator\Desktop\ai_weekly_report"
echo 正在启动翻译代理...
node translate_proxy.js
pause
