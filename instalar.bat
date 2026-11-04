@echo off
title Facturador OCR - Instalacion
cd /d "%~dp0"

echo ============================================
echo  Facturador OCR - INSTALACION
echo ============================================

set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>&1
    if not errorlevel 1 set "PYEXE=py"
)
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"

if defined PYEXE goto tiene_python

echo.
echo  [1/4] Python no esta instalado. Instalando Python 3.12 automaticamente...
where winget >nul 2>&1
if not errorlevel 1 (
    echo   Instalando con winget (tarda unos minutos, NO cierres esta ventana)...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
) else (
    echo   Descargando instalador oficial de python.org...
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $env:TEMP+'\python-installer.exe' -UseBasicParsing; exit 0 } catch { exit 1 }"
    if not exist "%TEMP%\python-installer.exe" (
        echo   [X] No se pudo descargar el instalador. Revisa internet e intenta de nuevo.
        pause
        exit /b 1
    )
    echo   Instalando silenciosamente (tarda unos minutos, NO cierres esta ventana)...
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
)

set "PYEXE="
where python >nul 2>&1
if not errorlevel 1 set "PYEXE=python"
if not defined PYEXE (
    where py >nul 2>&1
    if not errorlevel 1 set "PYEXE=py"
)
if not defined PYEXE if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
    echo   [X] Python se instalo pero no se detecto. Cierra esta ventana, abrila de nuevo y corre instalar.bat otra vez.
    pause
    exit /b 1
)
echo  Python instalado y detectado OK.

:tiene_python
set "PYVER="
"%PYEXE%" --version > "%TEMP%\pyver.txt" 2>&1
set /p PYVER=<"%TEMP%\pyver.txt"
echo.
echo  Python detectado: %PYVER%
echo.
echo  [2/4] Creando entorno virtual...
if exist "venv\Scripts\python.exe" (
    echo   (ya existia, se reusa)
) else (
    "%PYEXE%" -m venv venv
    if errorlevel 1 (
        echo  [X] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

echo  [3/4] Instalando dependencias (tarda varios minutos, NO cierres)...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo  [X] Fallo la instalacion de dependencias. Revisa el mensaje de arriba.
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [4/4] Creando .env desde la plantilla...
    copy .env.example .env >nul
    echo  ============================================================
    echo   IMPORTANTE: abre el archivo .env y configura:
    echo     GEMINI_API_KEY=tu_clave_de https://aistudio.google.com/apikey
    echo   (Sin esa clave la lectura automatica de facturas no funciona)
    echo  ============================================================
) else (
    echo  [4/4] .env ya existe: se conserva tu configuracion.
)

echo.
echo  Verificando instalacion...
venv\Scripts\python.exe check_setup.py

echo.
echo ============================================
echo  INSTALACION COMPLETA
echo ============================================
choice /C SN /M "Crear acceso directo en el Escritorio"
if not errorlevel 2 call crear_acceso_directo.bat

choice /C SN /M "Iniciar el sistema ahora"
if not errorlevel 2 start "" "%~dp0iniciar.bat"
exit /b 0
