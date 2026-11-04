@echo off
REM Crea un acceso directo en el Escritorio hacia iniciar.bat
powershell -NoProfile -Command ^
 "$escritorio=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($escritorio+'\Facturador OCR.lnk'); $s.TargetPath='%~dp0iniciar.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%SystemRoot%\System32\SHELL32.dll,22'; $s.Description='Facturador OCR'; $s.Save()"
if exist "%USERPROFILE%\Desktop\Facturador OCR.lnk" (
    echo  Acceso directo creado en el Escritorio: "Facturador OCR"
) else (
    echo  No se pudo crear el acceso directo automaticamente.
    echo  Crea uno manual hacia: %~dp0iniciar.bat
)
ping -n 3 127.0.0.1 >nul
