@echo off
setlocal EnableDelayedExpansion

REM =================================================
REM LANFXplorer — 32-bit Headless Launcher (Windows)
REM No Flutter UI — runs backend services only
REM =================================================

REM -------------------------------------------------
REM Parse CLI arguments
REM -------------------------------------------------
set "CLI_PASSWORD="
set "CLI_NAME="
set "CLI_OUTDIR="
set "CLI_PORT="

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
if /i "%~1"=="-h"         goto :show_help
if /i "%~1"=="--help"     goto :show_help
echo [!] Unknown option: %~1
goto :show_help

:done_args

REM -------------------------------------------------
REM Resolve paths
REM -------------------------------------------------
set "APP_DIR=%~dp0.."
pushd "%APP_DIR%"
set "APP_DIR=%CD%"
popd


set "PYTHON_EXE=python"

REM Verify Python exists
if not exist "%PYTHON_EXE%" (
    echo [ERROR] Python not found at: %PYTHON_EXE%
    echo         Please run 32bitcodes\install32.bat first.
    pause
    exit /b 1
)

REM -------------------------------------------------
REM Set up Python environment
REM -------------------------------------------------
set "PYTHONPATH=%APP_DIR%"
set "PATH=%PY_PREFIX%;%PY_PREFIX%\Scripts;%PATH%"
set "OPENSSL_PATH=C:\Program Files (x86)\OpenSSL-Win32\bin\openssl.exe"

REM -------------------------------------------------
REM Force headless mode
REM -------------------------------------------------
set "LANFXPLORER_HEADLESS=1"

REM -------------------------------------------------
REM Apply CLI overrides
REM -------------------------------------------------
if defined CLI_PASSWORD (
    echo [+] Setting password from CLI
    set "PASSWORD=%CLI_PASSWORD%"
)

if defined CLI_NAME (
    echo [+] Device name: %CLI_NAME%
    set "USER=%CLI_NAME%"
)

if defined CLI_OUTDIR (
    if not exist "%CLI_OUTDIR%" mkdir "%CLI_OUTDIR%"
    echo [+] Output directory: %CLI_OUTDIR%
    set "OUTDIR=%CLI_OUTDIR%"
    set "SRCDIR=%CLI_OUTDIR%"
)

if defined CLI_PORT (
    echo [+] QUIC port: %CLI_PORT%
    set "PORT=%CLI_PORT%"
)

REM -------------------------------------------------
REM Show config summary
REM -------------------------------------------------
echo.
echo ================================================
echo   LANFXplorer 32-bit Headless Mode (Windows)
echo ================================================
echo   App dir  : %APP_DIR%
echo   Python   : %PYTHON_EXE%
if defined CLI_PASSWORD ( echo   Password : [set] ) else ( echo   Password : [not set] )
if defined CLI_NAME     ( echo   Name     : %CLI_NAME% ) else ( echo   Name     : %USERNAME% )
if defined CLI_OUTDIR   ( echo   Output   : %CLI_OUTDIR% ) else ( echo   Output   : %%USERPROFILE%%\Lanfxplorer )
if defined CLI_PORT     ( echo   Port     : %CLI_PORT% ) else ( echo   Port     : 4433 )
echo ================================================
echo.

REM -------------------------------------------------
REM Launch (headless)
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
echo   -h, --help                Show this help
echo.
echo Examples:
echo   %~nx0 --password mypass123
echo   %~nx0 -p secret -n "OldLaptop" -o C:\Received
echo   %~nx0                          (uses all defaults)
exit /b 0
