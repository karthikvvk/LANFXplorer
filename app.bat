@echo off
setlocal EnableDelayedExpansion

REM =================================================
REM LANFXplorer — Unified Application Launcher
REM 64-bit: Flutter UI  |  32-bit: Python UI → headless
REM =================================================

REM -------------------------------------------------
REM Parse CLI arguments
REM -------------------------------------------------
set "CLI_PASSWORD="
set "CLI_NAME="
set "CLI_OUTDIR="
set "CLI_PORT="
set "FORCE_HEADLESS="

:parse_args
if "%~1"=="" goto :done_args
if /i "%~1"=="-p"         ( set "CLI_PASSWORD=%~2" & shift & shift & goto :parse_args )
if /i "%~1"=="--password" ( set "CLI_PASSWORD=%~2" & shift & shift & goto :parse_args )
if /i "%~1"=="-n"         ( set "CLI_NAME=%~2"     & shift & shift & goto :parse_args )
if /i "%~1"=="--name"     ( set "CLI_NAME=%~2"     & shift & shift & goto :parse_args )
if /i "%~1"=="-o"         ( set "CLI_OUTDIR=%~2"   & shift & shift & goto :parse_args )
if /i "%~1"=="--outdir"   ( set "CLI_OUTDIR=%~2"   & shift & shift & goto :parse_args )
if /i "%~1"=="-P"         ( set "CLI_PORT=%~2"     & shift & shift & goto :parse_args )
if /i "%~1"=="--port"     ( set "CLI_PORT=%~2"     & shift & shift & goto :parse_args )
if /i "%~1"=="--headless" ( set "FORCE_HEADLESS=1"  & shift & goto :parse_args )
if /i "%~1"=="-h"         goto :show_help
if /i "%~1"=="--help"     goto :show_help
echo [!] Unknown option: %~1
goto :show_help
:done_args

REM -------------------------------------------------
REM Resolve paths
REM -------------------------------------------------
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

REM -------------------------------------------------
REM Resolve system Python from install-time markers
REM -------------------------------------------------
set "PY_BIN_DIR="
set "PY_SCRIPTS_DIR="

if exist "%APP_DIR%\.python_bin_dir" (
    set /p PY_BIN_DIR=<"%APP_DIR%\.python_bin_dir"
    REM trim any trailing spaces/newlines
    set "PY_BIN_DIR=!PY_BIN_DIR: =!"
)
if exist "%APP_DIR%\.python_scripts_dir" (
    set /p PY_SCRIPTS_DIR=<"%APP_DIR%\.python_scripts_dir"
    set "PY_SCRIPTS_DIR=!PY_SCRIPTS_DIR: =!"
)

REM If marker files exist and are valid, prepend those dirs to PATH
if defined PY_BIN_DIR (
    if exist "!PY_BIN_DIR!\python.exe" (
        set "PATH=!PY_BIN_DIR!;!PY_SCRIPTS_DIR!;%PATH%"
    )
)

REM Resolve the actual python.exe to use
set "PYTHON_EXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)

if not defined PYTHON_EXE (
    echo [ERROR] Python not found.
    echo         Please run install.bat first, or ensure Python is on your PATH.
    pause
    exit /b 1
)

REM -------------------------------------------------
REM Set up Python environment
REM -------------------------------------------------
set "PYTHONPATH=%APP_DIR%"

REM Make system OpenSSL CLI available via env var (not on PATH — avoids DLL conflicts)
set "OPENSSL_PATH=C:\Program Files\OpenSSL-Win64\bin\openssl.exe"

REM -------------------------------------------------
REM Architecture auto-detection
REM -------------------------------------------------
set "ARCH_BITS=64"
if "%PROCESSOR_ARCHITECTURE%"=="x86" (
    if not defined PROCESSOR_ARCHITEW6432 (
        set "ARCH_BITS=32"
        set "OPENSSL_PATH=C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe"
    )
)

REM -------------------------------------------------
REM Apply CLI overrides
REM -------------------------------------------------
if defined FORCE_HEADLESS set "LANFXPLORER_HEADLESS=1"
if defined CLI_PASSWORD   set "PASSWORD=%CLI_PASSWORD%"
if defined CLI_NAME       set "USER=%CLI_NAME%"
if defined CLI_PORT       set "PORT=%CLI_PORT%"

if defined CLI_OUTDIR (
    if not exist "%CLI_OUTDIR%" mkdir "%CLI_OUTDIR%"
    set "OUTDIR=%CLI_OUTDIR%"
    set "SRCDIR=%CLI_OUTDIR%"
)

REM -------------------------------------------------
REM Config summary (when CLI args used)
REM -------------------------------------------------
set "SHOW_BANNER="
if defined CLI_PASSWORD set "SHOW_BANNER=1"
if defined CLI_NAME     set "SHOW_BANNER=1"
if defined CLI_OUTDIR   set "SHOW_BANNER=1"
if defined CLI_PORT     set "SHOW_BANNER=1"
if defined FORCE_HEADLESS set "SHOW_BANNER=1"

if defined SHOW_BANNER (
    echo.
    echo ================================================
    if defined FORCE_HEADLESS (
        echo   LANFXplorer [%ARCH_BITS%-bit — headless]
    ) else (
        echo   LANFXplorer [%ARCH_BITS%-bit]
    )
    echo ================================================
    if defined CLI_PASSWORD echo   Password : [set]
    if defined CLI_NAME     echo   Name     : %CLI_NAME%
    if defined CLI_OUTDIR   echo   Output   : %CLI_OUTDIR%
    if defined CLI_PORT     echo   Port     : %CLI_PORT%
    echo ================================================
    echo.
)

REM -------------------------------------------------
REM Launch
REM -------------------------------------------------
"%PYTHON_EXE%" "%APP_DIR%\main.py"

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Application exited with error code %errorlevel%
    pause
)
exit /b

REM -------------------------------------------------
:show_help
echo Usage: %~nx0 [OPTIONS]
echo.
echo Options:
echo   -p, --password PASSWORD   Set the peer authentication password
echo   -n, --name     NAME       Set device/user display name
echo   -o, --outdir   PATH       Set file receive directory
echo   -P, --port     PORT       Set QUIC port (default: 4433)
echo       --headless            Force headless mode (no UI)
echo   -h, --help                Show this help
echo.
echo Examples:
echo   %~nx0                            Normal launch
echo   %~nx0 --password mypass123       Set password
echo   %~nx0 -p secret --headless      Headless with password
exit /b 0