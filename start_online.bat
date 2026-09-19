@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo  🚀 Запуск ARBITER Gateway + Публичный Cloudflare Tunnel
echo ========================================================
.\.venv\Scripts\python.exe run_public.py
pause
