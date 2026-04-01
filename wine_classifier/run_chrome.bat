@echo off
title Wine Classifier — Chrome (Mistral + Gemini + Grok)
cd /d "C:\winegod-app"

echo ============================================================
echo  WINE CLASSIFIER — Chrome (4 Mistral + 4 Gemini + 4 Grok)
echo ============================================================

python wine_classifier\run_chrome.py

echo.
echo Finalizado!
pause
