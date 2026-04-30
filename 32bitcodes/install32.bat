@echo off
setlocal
chcp 65001 >nul 2>&1

REM ===============================
REM LANFXplorer — Windows 32-bit (x86) Installer
REM Standalone Python/OpenSSL removed — aioquic is gone.
REM cryptography pip package bundles its own OpenSSL via cffi.
REM Uses the system Python (must be 32-bit Python 3.10+ for 32-bit compatibility).
REM ===============================
title LANFXplorer 32-bit Installation
echo.
echo ==================================================
echo     LANFXplorer 32-bit Installation Starting...
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
REM NOTE: For true 32-bit operation, ensure the Python installed is
REM       the x86 (32-bit) variant from https://www.python.org
REM ===============================
echo [+] Checking for system Python
python --version >nul 2>&1 && (
    echo [OK] Python found
    python --version
    python -c "import struct; print('[OK] Pointer size:', struct.calcsize('P') * 8, 'bit')"
) || (
    echo [ERROR] Python not found.
    echo         For 32-bit: install Python 3.10 x86 from https://www.python.org/downloads/
    echo         Or run: winget install Python.Python.3.10
    pause
    exit /b 1
)

REM ===============================
REM pip upgrade + 32-bit requirements
REM ===============================
echo [+] Installing Python dependencies (32-bit)
python -m pip install --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

python -m pip install -r "%TESTING_DIR%\requirements_32.txt" && (
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
echo [OK] 32-bit Installation completed successfully!
echo ================================================
echo    Python: system (ensure x86 variant for 32-bit)
echo    cryptography: bundles own OpenSSL via cffi
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0
