@echo off
setlocal EnableDelayedExpansion
chcp 65001 >nul 2>&1

REM ===============================
REM Set console title and banner
REM ===============================
title LANFXplorer Installation
echo.
echo ==================================================
echo     LANFXplorer Installation Starting...
echo ==================================================
echo.

REM Resolve app directory
REM ===============================
set "APP_DIR=%~dp0"
set "APP_DIR=%APP_DIR:~0,-1%"

set "OPT_DIR=%APP_DIR%\opt"
set "DATA_DIR=%APP_DIR%\data"
set "LOG_DIR=%APP_DIR%\logs"

mkdir "%OPT_DIR%" 2>nul
mkdir "%DATA_DIR%" 2>nul
mkdir "%LOG_DIR%" 2>nul

REM ===============================
REM Python — System Installation
REM ===============================
echo [+] Checking for system Python...

REM Try to find python in PATH first
set "PYTHON_EXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)

if defined PYTHON_EXE (
    echo [OK] Python found at: %PYTHON_EXE%
    goto :python_found
)

REM Python not found — download and install
echo [!] Python not found in PATH.
echo [+] Downloading Python 3.11.9 installer...
echo.
echo IMPORTANT: The Python installer will open in a new window.
echo Please complete the installation. Make sure to check
echo "Add Python to PATH" during setup (or note your install path).
echo.
pause

set "PY_INSTALLER=%USERPROFILE%\Downloads\pyth  on_installer.exe"

powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PY_INSTALLER%'" && (
    echo [+] Python installer downloaded
) || (
    echo [ERROR] Failed to download Python installer
    exit /b 1
)

echo [+] Launching Python installer...
echo [+] Please complete the installation wizard.
echo [+] RECOMMENDED: Enable "Add Python to PATH" option.
echo.

start /wait "" "%PY_INSTALLER%"
del "%PY_INSTALLER%" 2>nul

echo.
echo [+] Installer closed. Verifying Python...

REM Refresh PATH from registry so newly installed Python is visible
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v PATH 2^>nul') do set "USR_PATH=%%B"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v PATH 2^>nul') do set "SYS_PATH=%%B"
set "PATH=%SYS_PATH%;%USR_PATH%;%PATH%"

set "PYTHON_EXE="
for /f "delims=" %%i in ('where python 2^>nul') do (
    if not defined PYTHON_EXE set "PYTHON_EXE=%%i"
)

if not defined PYTHON_EXE (
    echo.
    echo [!] Python still not detected in PATH after installation.
    echo [!] This may happen if "Add Python to PATH" was not selected,
    echo [!] or if the current shell has not refreshed its environment.
    echo.
    echo Please enter the paths manually below.
    echo Example Python bin dir : C:\Users\You\AppData\Local\Programs\Python\Python311
    echo Example Scripts dir    : C:\Users\You\AppData\Local\Programs\Python\Python311\Scripts
    echo.
    set /p "PY_BIN_DIR=Enter Python bin directory (where python.exe is): "
    set /p "PY_SCRIPTS_DIR=Enter Python Scripts directory (where pip.exe is): "

    if not exist "!PY_BIN_DIR!\python.exe" (
        echo [ERROR] python.exe not found at: !PY_BIN_DIR!
        exit /b 1
    )
    if not exist "!PY_SCRIPTS_DIR!\pip.exe" (
        echo [WARNING] pip.exe not found at: !PY_SCRIPTS_DIR! — will attempt to use python -m pip
    )

    set "PYTHON_EXE=!PY_BIN_DIR!\python.exe"
    set "PATH=!PY_BIN_DIR!;!PY_SCRIPTS_DIR!;%PATH%"

    REM Persist paths for app.bat
    echo !PY_BIN_DIR!>  "%APP_DIR%\.python_bin_dir"
    echo !PY_SCRIPTS_DIR!> "%APP_DIR%\.python_scripts_dir"
    goto :python_found
)

:python_found
REM Derive dirs from the resolved exe path if not already set
if not defined PY_BIN_DIR (
    for %%i in ("%PYTHON_EXE%") do set "PY_BIN_DIR=%%~dpi"
    REM strip trailing backslash
    set "PY_BIN_DIR=!PY_BIN_DIR:~0,-1!"
    set "PY_SCRIPTS_DIR=!PY_BIN_DIR!\Scripts"
)

REM Persist for app.bat
echo !PY_BIN_DIR!>  "%APP_DIR%\.python_bin_dir"
echo !PY_SCRIPTS_DIR!> "%APP_DIR%\.python_scripts_dir"

echo [OK] Using Python : %PYTHON_EXE%
echo [OK] Bin dir      : !PY_BIN_DIR!
echo [OK] Scripts dir  : !PY_SCRIPTS_DIR!
echo.

REM ===============================
REM OpenSSL 3.5 LTS (System Installation)
REM ===============================
set "SYSTEM_SSL_PATH=C:\Program Files\OpenSSL-Win64\bin\openssl.exe"
if not exist "%SYSTEM_SSL_PATH%" (
    echo [+] Installing OpenSSL 3.5.5 LTS to system (Program Files)
    echo.
    echo IMPORTANT: The OpenSSL installer will open in a new window.
    echo You MUST accept the license agreement to continue installation.
    echo The installer will install to: C:\Program Files\OpenSSL-Win64
    echo If you cancel or reject, the installation will fail.
    echo.
    pause

    set "DOWNLOAD_PATH=%USERPROFILE%\Downloads\openssl_installer.exe"

    powershell -Command "Invoke-WebRequest -Uri 'https://slproweb.com/download/Win64OpenSSL_Light-3_5_5.exe' -OutFile '%DOWNLOAD_PATH%'" && (
        echo [+] OpenSSL installer downloaded to Downloads folder
    ) || (
        echo [ERROR] Failed to download OpenSSL installer
        exit /b 1
    )

    echo [+] Launching OpenSSL installer...
    echo [+] Please complete the installation wizard in the window that opens
    echo [+] Accept the default installation path (Program Files)
    echo [+] The script will continue automatically once you finish
    echo.

    start /wait "" "%DOWNLOAD_PATH%"

    echo [+] Installer closed, verifying installation...

    if exist "%SYSTEM_SSL_PATH%" (
        echo [+] OpenSSL installation complete at C:\Program Files\OpenSSL-Win64
        del "%DOWNLOAD_PATH%" 2>nul
    ) else (
        echo.
        echo [ERROR] OpenSSL installation failed or was cancelled by user
        echo [ERROR] The installer must be accepted to continue
        echo [ERROR] Expected location: C:\Program Files\OpenSSL-Win64\bin\openssl.exe
        del "%DOWNLOAD_PATH%" 2>nul
        exit /b 1
    )
) else (
    echo [OK] OpenSSL already installed at C:\Program Files\OpenSSL-Win64
)

REM ===============================
REM pip + requirements
REM ===============================
echo [+] Installing Python dependencies
"%PYTHON_EXE%" -m pip install --no-warn-script-location --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

"%PYTHON_EXE%" -m pip install --no-warn-script-location -r "%APP_DIR%\requirements.txt" && (
    echo [+] Dependencies installation complete
) || (
    echo [ERROR] Failed to install dependencies
    exit /b 1
)

REM Verify cryptography package is installed correctly
echo [+] Verifying cryptography package
"%PYTHON_EXE%" -c "import cryptography; print('[OK] cryptography', cryptography.__version__)" || (
    echo [WARNING] cryptography package may not be installed correctly
)

REM ===============================
REM Firewall rules
REM ===============================
echo [+] Configuring Windows Firewall rules for LANFXplorer...
"%PYTHON_EXE%" "%APP_DIR%\firewall_manager.py" --install && (
    echo [+] Firewall rules configured
) || (
    echo [WARNING] Firewall configuration failed. You may need to manually allow ports.
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
echo [OK] Installation completed successfully!
echo ================================================
echo    Python     : %PYTHON_EXE%
echo    OpenSSL 3.5.5 LTS: C:\Program Files\OpenSSL-Win64
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0