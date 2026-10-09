@echo off
chcp 65001 >nul
rem 端口可用环境变量覆盖:set PORT=8020 && start_web.bat
rem 默认 8010,避开 issue-pr-agent 控制台的 8000,两个控制台可同时开
if "%PORT%"=="" set PORT=8010
echo ========================================================
echo         Job-Agent 智能求职工作台 启动中...
echo ========================================================
echo.
echo 访问地址: http://127.0.0.1:%PORT%
echo.

start "" "http://127.0.0.1:%PORT%"
uv run uvicorn web_server:app --host 127.0.0.1 --port %PORT% --reload
pause
