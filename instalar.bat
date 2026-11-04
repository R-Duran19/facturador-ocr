@echo off
title Facturador OCR - Instalacion
cd /d "%~dp0"

echo ============================================
echo  Facturador OCR - INSTALACION
echo ============================================

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo.
    echo  [X] Python no esta instalado o no esta en el PATH.
    echo      Instala Python 3.12 desde https://www.python.org/downloads/
    echo      IMPORTANTE: marca la casilla "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%v in ('python --version 2^>^&1') do set PYVER=%%v
echo  Python detectado: %PYVER%

if exist "venv\Scripts\python.exe" (
    echo.
    echo  [i] El entorno virtual ya existe. Se reusan las instalaciones.
) else (
    echo.
    echo  [1/3] Creando entorno virtual...
    python -m venv venv
    if %errorlevel% neq 0 (
        echo  [X] No se pudo crear el entorno virtual.
        pause
        exit /b 1
    )
)

echo.
echo  [2/3] Actualizando pip...
venv\Scripts\python.exe -m pip install --upgrade pip --quiet

echo  [3/3] Instalando dependencias (tarda unos minutos)...
venv\Scripts\python.exe -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo.
    echo  [X] Fallo la instalacion de dependencias. Revisá el mensaje de arriba.
    pause
    exit /b 1
)

if not exist ".env" (
    echo.
    echo  [i] Creando .env desde la plantilla...
    copy .env.example .env >nul
    echo  ============================================================
    echo   IMPORTANTE: abri el archivo .env y configura:
    echo     GEMINI_API_KEY=tu_clave_de https://aistudio.google.com/apikey
    echo   (Sin esa clave la lectura automatica de facturas no funciona)
    echo  ============================================================
) else (
    echo  [i] .env ya existe: se conserva tu configuracion.
)

echo.
echo ============================================
echo  INSTALACION COMPLETA
echo  Siguiente paso: ejecutar crear_acceso_directo.bat
echo  y luego iniciar.bat (o el acceso del escritorio)
echo ============================================
echo.
choice /C SN /M "¿Crear acceso directo en el Escritorio ahora"
if %errorlevel%==1 call crear_acceso_directo.bat

choice /C SN /M "¿Iniciar el sistema ahora"
if %errorlevel%==1 start "" "%~dp0iniciar.bat"
exit /b 0
