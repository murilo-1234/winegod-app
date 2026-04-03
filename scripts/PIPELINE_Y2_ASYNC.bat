@echo off
title WineGod Pipeline Y2 ASYNC
echo.
echo  ========================================
echo   WineGod Pipeline Y2 ASYNC
echo   200 chamadas concorrentes
echo   Dashboard: http://localhost:8050
echo  ========================================
echo.
echo  Abrindo dashboard...
start http://localhost:8050
echo.
cd /d C:\winegod-app
python scripts\pipeline_y2_async.py
pause
