@echo off
chcp 65001 >nul
title 千绘莉的多功能工具箱 (Chieri Toolbox)
cd /d "%~dp0"
if exist ".venv\Scripts\pythonw.exe" (
    start "" ".venv\Scripts\pythonw.exe" "main.py" %*
) else if exist ".venv\Scripts\python.exe" (
    start "" ".venv\Scripts\python.exe" "main.py" %*
) else (
    python main.py %*
)
exit
