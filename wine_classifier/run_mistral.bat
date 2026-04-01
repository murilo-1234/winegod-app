@echo off
title Wine Classifier — Mistral (5 abas, Chrome separado)
cd /d "C:\winegod-app"

echo ============================================================
echo  WINE CLASSIFIER — Mistral (5 abas, 30s entre cada)
echo ============================================================

python wine_classifier\run_mistral.py

echo.
echo Finalizado!
pause
