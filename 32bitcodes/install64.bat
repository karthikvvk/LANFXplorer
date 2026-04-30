@echo off
setlocal
chcp 65001 >nul 2>&1

REM ===============================
REM LANFXplorer — Windows 64-bit (amd64) Installer
REM Standalone Python/OpenSSL removed — aioquic is gone.
REM cryptography pip package bundles its own OpenSSL via cffi.
REM Uses the system Python (must be installed by user or via winget).
REM ===============================
title LANFXplorer 64-bit Installation
echo.
echo ==================================================
echo     LANFXplorer 64-bit Installation Starting...
echo ==================================================
echo.

REM Resolve directories
set "TESTING_DIR=%~dp0"
set "TESTING_DIR=%TESTING_DIR:~0,-1%"

REM APP_DIR is the parent of 32bitcodes
for %%I in ("%TESTING_DIR%\..") do set "APP_DIR=%%~fI"

set "DATA_DIR=%APP_DIR%\data"
set "LOG_DIR=%APP_DIR%\logs"

mkdir "%DATA_DIR%" 2>nul
mkdir "%LOG_DIR%" 2>nul

REM ===============================
REM Check for system Python
REM ===============================
echo [+] Checking for system Python
python --version >nul 2>&1 && (
    echo [OK] Python found
    python --version
) || (
    echo [ERROR] Python not found. Please install Python 3.8+ from https://www.python.org
    echo         Or run: winget install Python.Python.3.12
    pause
    exit /b 1
)

REM ===============================
REM pip upgrade + 64-bit requirements
REM ===============================
echo [+] Installing Python dependencies (64-bit)
python -m pip install --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

python -m pip install -r "%TESTING_DIR%\requirements_64.txt" && (
    echo [+] Dependencies installation complete
) || (
    echo [ERROR] Failed to install dependencies
    exit /b 1
)

REM Verify cryptography package
echo [+] Verifying cryptography package
python -c "import cryptography; print('[OK] cryptography', cryptography.__version__)" || (
    echo [WARNING] cryptography package may not be installed correctly
)

REM ===============================
REM Desktop shortcut
REM ===============================
echo [+] Creating desktop shortcut

set "SHORTCUT=%USERPROFILE%\Desktop\LANFXplorer.lnk"

powershell -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%APP_DIR%\app.bat'; $s.WorkingDirectory='%APP_DIR%'; $s.Description='LANFXplorer'; $s.Save()"

REM ===============================
REM Mark install complete
REM ===============================
type nul > "%APP_DIR%\.installed"

echo.
echo ================================================
echo [OK] 64-bit Installation completed successfully!
echo ================================================
echo    Python: system
echo    cryptography: bundles own OpenSSL via cffi
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0
