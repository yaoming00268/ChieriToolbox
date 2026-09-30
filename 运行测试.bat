@echo off
chcp 65001 >nul
title 工具箱自动化单元测试
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m unittest tests/test_toolbox.py %*
) else (
    python -m unittest tests/test_toolbox.py %*
)
echo.
pause
