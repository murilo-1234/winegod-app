@echo off
title Mistral Classifier — Wine Classification (4 abas)
cd /d "%~dp0\.."

echo ============================================================
echo  MISTRAL CLASSIFIER — 4 abas x 1000 itens
echo  Integrado com Pipeline Y2 (y2_results)
echo ============================================================
echo.

python scripts\mistral_classifier.py

echo.
echo Pressione qualquer tecla para fechar...
pause
