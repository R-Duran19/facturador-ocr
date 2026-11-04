@echo off
set ENCONTRO=0
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8080 ^| findstr LISTENING') do (
    taskkill /F /PID %%a >nul 2>&1
    set ENCONTRO=1
)
if %ENCONTRO%==1 (
    echo  Sistema apagado.
) else (
    echo  El sistema no estaba corriendo.
)
ping -n 3 127.0.0.1 >nul
