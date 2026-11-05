@echo off
cd /d "%~dp0"
title Facturador OCR

if "%1"=="SOLO_ACTUALIZAR" goto solo_actualizar
if "%1"=="SERVIDOR" goto servidor

if not exist "venv\Scripts\python.exe" (
    echo.
    echo  [!] Falta la instalacion. Ejecuta primero: instalar.bat
    echo.
    pause
    exit /b
)

where git >nul 2>&1
if errorlevel 1 goto sin_git
if not exist ".git" goto sin_git

echo  Buscando actualizaciones...
REM La actualizacion corre desde una COPIA en TEMP (git nunca reemplaza el script
REM en ejecucion). Se espera a que termine y recien entonces abre el sistema,
REM asi siempre corre la version nueva.
copy /y "%~f0" "%TEMP%\fact_actualizar.bat" >nul
start "" /wait /min cmd /c ""%TEMP%\fact_actualizar.bat" SOLO_ACTUALIZAR"
start "" cmd /c ""%TEMP%\fact_actualizar.bat" SERVIDOR"
exit /b

:sin_git
echo  [i] Sin actualizador git: se inicia la version instalada.
copy /y "%~f0" "%TEMP%\fact_actualizar.bat" >nul
start "" cmd /c ""%TEMP%\fact_actualizar.bat" SERVIDOR"
exit /b

:solo_actualizar
git pull --ff-only
if errorlevel 1 (
    echo  [i] No se pudo actualizar: sin internet o cambios locales. Se inicia con la version actual.
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
