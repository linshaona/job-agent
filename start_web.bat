@echo off
chcp 65001 >nul
echo ========================================================
echo         Job-Agent 智能求职工作台 启动中...
echo ========================================================
echo.
echo 访问地址: http://127.0.0.1:8000
echo.

start "" "http://127.0.0.1:8000"
uv run uvicorn web_server:app --host 127.0.0.1 --port 8000 --reload
pause
