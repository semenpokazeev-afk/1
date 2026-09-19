@echo off
chcp 65001 >nul
echo Остановка процессов ARBITER и Cloudflare Tunnel...
taskkill /f /im cloudflared.exe >nul 2>&1
taskkill /f /im uvicorn.exe >nul 2>&1
echo Готово.
