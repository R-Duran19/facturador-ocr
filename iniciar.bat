@echo off
cd /d "%~dp0"
title Facturador OCR

if "%1"=="SOLO_ACTUALIZAR" goto solo_actualizar

if not exist "venv\Scripts\python.exe" (
    echo.
    echo  [!] Falta la instalacion. Ejecuta primero: instalar.bat
    echo.
    pause
    exit /b
)

if "%YA_ACTUALIZADO%"=="1" goto servidor

where git >nul 2>&1
if errorlevel 1 goto servidor
if not exist ".git" goto servidor

echo  Buscando actualizaciones...
REM La actualizacion corre desde una COPIA en TEMP (git nunca la reemplaza),
REM asi este archivo puede ser reescrito sin matar la ejecucion.
copy /y "%~f0" "%TEMP%\fact_actualizar.bat" >nul
set "YA_ACTUALIZADO=1"
start "" "%~f0"
start "" /min cmd /c ""%TEMP%\fact_actualizar.bat" SOLO_ACTUALIZAR"
exit /b

:solo_actualizar
git pull --ff-only
if errorlevel 1 (
    echo  [i] No se pudo actualizar: sin internet o cambios locales.
    ping -n 4 127.0.0.1 >nul
) else (
    echo  Sistema actualizado con la ultima version.
)
exit /b

:servidor
title Facturador OCR
netstat -ano | findstr :8080 | findstr LISTENING >nul
if %errorlevel%==0 (
    echo  El sistema YA ESTA CORRIENDO. Abriendo el navegador...
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
