@echo off
setlocal

REM ===============================================
REM LANFXplorer Windows Application Launcher
REM ===============================================

REM Get the directory where this script is located
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

set "PY_PREFIX=%APP_DIR%\opt\python39"
set "PYTHON_EXE=%PY_PREFIX%\python.exe"

REM -------------------------------
REM Launch the application
REM -------------------------------

echo [*] Starting LANFXplorer...
echo     App Directory: %APP_DIR%
echo.

REM Use embedded Python installed by install.bat
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    echo         Please run install.bat first.
    pause
    exit /b 1
)

echo [*] Using Python: %PYTHON_EXE%

REM Set up environment for embedded Python
set "PYTHONHOME=%PY_PREFIX%"
set "PYTHONPATH=%APP_DIR%"
set "PATH=%PY_PREFIX%;%PY_PREFIX%\Scripts;C:\Program Files\OpenSSL-Win64;C:\Program Files\OpenSSL-Win64\bin;%PATH%"

REM Run the main application
"%PYTHON_EXE%" "%APP_DIR%\main.py"

REM Keep window open if there was an error
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
