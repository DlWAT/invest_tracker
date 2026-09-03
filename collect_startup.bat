@echo off
cd /d "%~dp0"
chcp 65001 >nul
title Philippine Airbnb Scanner - Collecte
echo ============================================================
echo   Philippine Airbnb Scanner - collecte automatique
echo   Demarrage : %date% %time%
echo ============================================================
echo.
".venv\Scripts\python.exe" main.py
echo.
echo ============================================================
echo   Collecte terminee. Appuyez sur une touche pour fermer.
echo ============================================================
pause >nul
