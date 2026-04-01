@echo off
title Wine Classifier — Edge (Qwen + ChatGPT + GLM)
cd /d "C:\winegod-app"

echo ============================================================
echo  WINE CLASSIFIER — Edge (4 Qwen + 4 ChatGPT + 4 GLM)
echo ============================================================

python wine_classifier\run_edge.py

echo.
echo Finalizado!
pause
