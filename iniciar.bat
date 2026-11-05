@echo off
title Facturador OCR
cd /d "%~dp0"

if not exist "venv\Scripts\python.exe" (
    echo.
    echo  [!] Falta la instalacion. Ejecuta primero: instalar.bat
    echo.
    pause
    exit /b
)

REM ---------- Actualizador automatico: git pull al arrancar ----------
where git >nul 2>&1
if errorlevel 1 goto sin_actualizar
if not exist ".git" goto sin_actualizar

echo  Buscando actualizaciones...
git pull --ff-only --quiet
if errorlevel 1 (
    echo  [i] No se pudo actualizar (sin internet o cambios locales). Se inicia con la version actual.
) else (
    echo  Sistema actualizado con la ultima version.
)
goto arrancar

:sin_actualizar
echo  [i] Sin actualizador git: se inicia la version instalada.

:arrancar
netstat -ano | findstr :8080 | findstr LISTENING >nul
if %errorlevel%==0 (
    echo.
    echo  El sistema YA ESTA CORRIENDO. Abriendo el navegador...
    echo.
    start "" http://127.0.0.1:8080
    ping -n 3 127.0.0.1 >nul
    exit /b
)

echo.
echo  ============================================
echo   Facturador OCR - iniciando...
echo   Cierra esta ventana para APAGAR el sistema
echo ============================================
echo.

start "" /min cmd /c "ping -n 3 127.0.0.1 >nul && start "" http://127.0.0.1:8080"
venv\Scripts\python.exe -m webui.main

echo.
echo  Sistema apagado.
ping -n 3 127.0.0.1 >nul
