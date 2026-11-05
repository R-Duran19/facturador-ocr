@echo off
title Facturador OCR - Instalacion
cd /d "%~dp0"

echo ============================================
echo  Facturador OCR - INSTALACION
echo ============================================

set "PYEXE="
set "PYARGS="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if defined PYEXE goto tiene_python

py -3.12 --version >nul 2>&1
if errorlevel 1 goto probar_python
set "PYEXE=py"
set "PYARGS=-3.12"
goto tiene_python

:probar_python
where python >nul 2>&1
if errorlevel 1 goto instalar_python
set "PYVERSTR="
for /f "tokens=*" %%v in ('python --version 2^>^&1') do set "PYVERSTR=%%v"
echo %PYVERSTR% | findstr /C:"3.12" >nul
if errorlevel 1 goto instalar_python
set "PYEXE=python"
goto tiene_python

:instalar_python
echo.
echo  [1/5] No se encontro Python 3.12. Instalandolo automaticamente...
where winget >nul 2>&1
if not errorlevel 1 (
    echo   Instalando con winget - tarda unos minutos, NO cierres esta ventana...
    winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements --silent
) else (
    echo   Descargando instalador oficial de python.org...
    powershell -NoProfile -Command "try { [Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe' -OutFile $env:TEMP+'\python-installer.exe' -UseBasicParsing; exit 0 } catch { exit 1 }"
    if not exist "%TEMP%\python-installer.exe" (
        echo   [X] No se pudo descargar el instalador. Revisa internet e intenta de nuevo.
        pause
        exit /b 1
    )
    echo   Instalando silenciosamente - tarda unos minutos, NO cierres esta ventana...
    "%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_launcher=1
)

set "PYEXE="
set "PYARGS="
if exist "%LOCALAPPDATA%\Programs\Python\Python312\python.exe" set "PYEXE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if not defined PYEXE if exist "%ProgramFiles%\Python312\python.exe" set "PYEXE=%ProgramFiles%\Python312\python.exe"
if defined PYEXE goto tiene_python
py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo   [X] Python 3.12 se instalo pero no se detecto. Cierra esta ventana, abrila de nuevo y corre instalar.bat otra vez.
    pause
    exit /b 1
)
set "PYEXE=py"
set "PYARGS=-3.12"

:tiene_python
set "PYVER="
"%PYEXE%" %PYARGS% --version > "%TEMP%\pyver.txt" 2>&1
set /p PYVER=<"%TEMP%\pyver.txt"
echo.
echo  Python 3.12 detectado: %PYVER%
echo.

REM ---- venv: debe ser de Python 3.12; si no, se recrea ----
if not exist "venv\Scripts\python.exe" goto crear_venv
set "VVER="
venv\Scripts\python.exe --version > "%TEMP%\pyver.txt" 2>&1
set /p VVER=<"%TEMP%\pyver.txt"
echo %VVER% | findstr /C:"3.12" >nul
if not errorlevel 1 goto venv_ok
echo  [i] El venv existente usa %VVER% y NO es Python 3.12. Se borra y se recrea...
rmdir /s /q venv

:crear_venv
echo  [2/5] Creando entorno virtual con Python 3.12...
"%PYEXE%" %PYARGS% -m venv venv
if errorlevel 1 (
    echo  [X] No se pudo crear el entorno virtual.
    pause
    exit /b 1
)

:venv_ok
echo  [3/5] Instalando dependencias (tarda varios minutos, NO cierres)...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet
venv\Scripts\python.exe -m pip install -r requirements.txt
if errorlevel 1 (
    echo  [X] Fallo la instalacion de dependencias. Revisa el mensaje de arriba.
    pause
    exit /b 1
)

if not exist ".env" (
    echo  [4/5] Creando .env desde la plantilla...
    copy .env.example .env >nul
    echo  ============================================================
    echo   IMPORTANTE: abre el archivo .env y configura:
    echo     GEMINI_API_KEY=tu_clave_de https://aistudio.google.com/apikey
    echo   Sin esa clave la lectura automatica de facturas no funciona
    echo  ============================================================
) else (
    echo  [4/5] .env ya existe: se conserva tu configuracion.
)

echo.
echo  [5/5] Verificando instalacion...
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
