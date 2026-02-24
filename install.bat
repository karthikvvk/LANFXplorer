@echo off
setlocal
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

set "PY_DIR=%OPT_DIR%\python39"
set "SSL_DIR=%OPT_DIR%\openssl"

mkdir "%OPT_DIR%" 2>nul
mkdir "%DATA_DIR%" 2>nul
mkdir "%LOG_DIR%" 2>nul

REM ===============================
REM Python 3.9.1 standalone
REM ===============================
if not exist "%PY_DIR%\python.exe" (
    echo [+] Installing Python 3.9.1 (standalone)

    powershell -Command "Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.9.1/python-3.9.1-embed-amd64.zip' -OutFile '%OPT_DIR%\python39.zip'" && (
        echo [+] Python download complete
    ) || (
        echo [ERROR] Failed to download Python
        exit /b 1
    )

    powershell -Command "Expand-Archive '%OPT_DIR%\python39.zip' '%PY_DIR%' -Force" && (
        echo [+] Python extraction complete
        del "%OPT_DIR%\python39.zip"
    ) || (
        echo [ERROR] Failed to extract Python
        exit /b 1
    )

    REM Enable site-packages
    for %%f in ("%PY_DIR%\python*._pth") do (
        powershell -Command "(Get-Content '%%f') -replace '#import site','import site' | Set-Content '%%f'"
    )

    REM Install pip
    echo [+] Installing pip
    powershell -Command "Invoke-WebRequest -Uri 'https://bootstrap.pypa.io/get-pip.py' -OutFile '%OPT_DIR%\get-pip.py'" && (
        echo [+] pip download complete
    ) || (
        echo [ERROR] Failed to download pip
        exit /b 1
    )

    "%PY_DIR%\python.exe" "%OPT_DIR%\get-pip.py" && (
        echo [+] pip installation complete
        del "%OPT_DIR%\get-pip.py"
    ) || (
        echo [ERROR] Failed to install pip
        exit /b 1
    )

) else (
    echo [OK] Python already present
)

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
    
    REM Run the installer interactively without /DIR to use default location
    start /wait "" "%DOWNLOAD_PATH%"
    
    echo [+] Installer closed, verifying installation...
    
    REM Check if OpenSSL was installed to system location
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
"%PY_DIR%\python.exe" -m pip install --no-warn-script-location --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

"%PY_DIR%\python.exe" -m pip install --no-warn-script-location -r "%APP_DIR%\requirements.txt" && (
    echo [+] Dependencies installation complete
) || (
    echo [ERROR] Failed to install dependencies
    exit /b 1
)

REM Verify cryptography package is installed correctly
echo [+] Verifying cryptography package
"%PY_DIR%\python.exe" -c "import cryptography; print('[OK] cryptography', cryptography.__version__)" || (
    echo [WARNING] cryptography package may not be installed correctly
)

REM ===============================
REM Firewall rules
REM ===============================
echo [+] Configuring Windows Firewall rules for LANFXplorer...
"%PY_DIR%\python.exe" "%APP_DIR%\firewall_manager.py" --install && (
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
echo    Python 3.9.1: %PY_DIR%
echo    OpenSSL 3.5.5 LTS: C:\Program Files\OpenSSL-Win64
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0

