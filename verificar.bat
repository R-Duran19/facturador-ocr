@echo off
title Facturador OCR - Salud del sistema
cd /d "%~dp0"
if not exist "venv\Scripts\python.exe" (
    echo Falta instalar. Corre primero instalar.bat
    pause
    exit /b 1
)
venv\Scripts\python.exe check_setup.py
echo.
pause
