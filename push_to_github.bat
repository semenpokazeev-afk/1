@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo ========================================================
echo  🚀 Загрузка ARBITER в https://github.com/semenpokazeev-afk/1.git
echo ========================================================
echo.
git push -u origin main
echo.
echo ========================================================
echo  Если вы видите "Branch 'main' set up to track...",
echo  значит код успешно загружен на GitHub!
echo ========================================================
echo.
pause
