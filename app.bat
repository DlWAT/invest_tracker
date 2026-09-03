@echo off
cd /d "%~dp0"
chcp 65001 >nul
title Philippine Airbnb Scanner - App
echo Demarrage de l'application sur http://127.0.0.1:5000 ...
echo (Le navigateur s'ouvrira automatiquement. Fermez cette fenetre pour arreter.)
echo.
start "" powershell -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Start-Process 'http://127.0.0.1:5000'"
".venv\Scripts\python.exe" app.py
echo.
pause
