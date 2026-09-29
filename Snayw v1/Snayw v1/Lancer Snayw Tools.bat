@echo off
setlocal
title Snayw v1
chcp 65001 >nul
cd /d "%~dp0"
where py >nul 2>nul
if %errorlevel%==0 (
    py -3 "%~dp0snayw_tools.py"
) else (
    python "%~dp0snayw_tools.py"
)
if errorlevel 1 (
    echo.
    echo Snayw Tools n'a pas demarre. Verifie Python 3 et Tkinter.
    pause
)
endlocal
