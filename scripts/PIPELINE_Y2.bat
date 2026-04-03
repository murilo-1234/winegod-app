@echo off
title WineGod Pipeline Y2
echo.
echo  ========================================
echo   WineGod Pipeline Y2
echo   Dashboard: http://localhost:8050
echo   100 workers
echo  ========================================
echo.
echo  Abrindo dashboard no navegador...
start http://localhost:8050
echo.
cd /d C:\winegod-app
python scripts\pipeline_y2.py
pause
