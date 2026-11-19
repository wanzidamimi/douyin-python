@echo off
chcp 65001 >nul
cd /d %~dp0
echo ============================================
echo  抖音弹幕实时显示（纯协议直连）
echo  浏览器打开 http://127.0.0.1:8800
echo ============================================
python -m uvicorn app:app --host 127.0.0.1 --port 8800
pause
