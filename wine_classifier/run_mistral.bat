@echo off
title MISTRAL [0-L] 5 abas
cd /d "C:\winegod-app"

echo ============================================================
echo  MISTRAL [0-L] 5 abas - Chrome separado
echo ============================================================

python wine_classifier\run_mistral.py

echo.
echo Finalizado!
pause
