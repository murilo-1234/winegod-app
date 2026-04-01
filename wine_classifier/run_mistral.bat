@echo off
title Wine Classifier — Mistral (Chrome separado)
cd /d "C:\winegod-app"

echo ============================================================
echo  WINE CLASSIFIER — Mistral (4 abas, Chrome separado)
echo ============================================================

python wine_classifier\run_mistral.py

echo.
echo Finalizado!
pause
