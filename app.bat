@echo off
setlocal enabledelayedexpansion

REM ===============================================
REM LANFXplorer Windows Application Launcher
REM ===============================================

REM Get the directory where this script is located
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

set "OPENSSL_PREFIX=%APP_DIR%\opt\openssl"
set "PY_PREFIX=%APP_DIR%\opt\python39"

REM Environment variables are set conditionally below based on which Python is used
REM Linux keeps the existing structure; Windows has conditional setup

REM -------------------------------
REM Launch the application
REM -------------------------------

echo [*] Starting LANFXplorer...
echo     Python: %PY_PREFIX%\python.exe
echo     App Directory: %APP_DIR%
echo.

REM Check if Python exists
REM Try system Python first (better OpenSSL compatibility)
set "PYTHON_EXE="
where python >nul 2>&1
if %errorlevel%==0 (
    set "PYTHON_EXE=python"
    echo [*] Using system Python
    
    REM For system Python: only set PYTHONPATH to app directory, clear PYTHONHOME
    set "PYTHONHOME="
    set "PYTHONPATH=%APP_DIR%"
    
    REM Add system OpenSSL to PATH
    set "PATH=C:\Program Files\OpenSSL-Win64;C:\Program Files\OpenSSL-Win64\bin;%PATH%"
) else if exist "%PY_PREFIX%\python.exe" (
    set "PYTHON_EXE=%PY_PREFIX%\python.exe"
    echo [*] Using standalone Python from opt
    
    REM For embedded Python: set PYTHONHOME and add to PATH
    set "PYTHONHOME=%PY_PREFIX%"
    set "PYTHONPATH=%APP_DIR%"
    set "PATH=%PY_PREFIX%;%PY_PREFIX%\Scripts;C:\Program Files\OpenSSL-Win64;C:\Program Files\OpenSSL-Win64\bin;%PATH%"
) else (
    echo [!] Error: Python not found
    echo     Please run install.bat first or install Python system-wide
    pause
    exit /b 1
)

REM Run the main application
"%PYTHON_EXE%" "%APP_DIR%\main.py"

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [!] Application exited with error code %errorlevel%
    pause
)
