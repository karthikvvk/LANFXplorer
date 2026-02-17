@echo off
setlocal
chcp 65001 >nul 2>&1

REM ===============================
REM LANFXplorer — Windows 64-bit (amd64) Installer
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

REM APP_DIR is the parent of 32bittesting
for %%I in ("%TESTING_DIR%\..") do set "APP_DIR=%%~fI"

set "OPT_DIR=%APP_DIR%\opt"
set "DATA_DIR=%APP_DIR%\data"
set "LOG_DIR=%APP_DIR%\logs"

set "PY_DIR=%OPT_DIR%\python39"
set "SSL_DIR=%OPT_DIR%\openssl"

mkdir "%OPT_DIR%" 2>nul
mkdir "%DATA_DIR%" 2>nul
mkdir "%LOG_DIR%" 2>nul

REM ===============================
REM Python 3.9.1 standalone (64-bit)
REM ===============================
set "PY_VERSION=3.9.1"
set "PY_ARCH=amd64"
set "PY_URL=https://www.python.org/ftp/python/%PY_VERSION%/python-%PY_VERSION%-embed-%PY_ARCH%.zip"

if not exist "%PY_DIR%\python.exe" (
    echo [+] Installing Python %PY_VERSION% (64-bit standalone)

    powershell -Command "Invoke-WebRequest -Uri '%PY_URL%' -OutFile '%OPT_DIR%\python39.zip'" && (
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
REM OpenSSL 3.5 LTS (64-bit System Installation)
REM ===============================
set "SYSTEM_SSL_PATH=C:\Program Files\OpenSSL-Win64\bin\openssl.exe"
if not exist "%SYSTEM_SSL_PATH%" (
    echo [+] Installing OpenSSL 3.5.5 LTS (64-bit) to system
    echo.
    echo IMPORTANT: The OpenSSL installer will open in a new window.
    echo You MUST accept the license agreement to continue installation.
    echo The installer will install to: C:\Program Files\OpenSSL-Win64
    echo If you cancel or reject, the installation will fail.
    echo.
    pause

    set "DOWNLOAD_PATH=%USERPROFILE%\Downloads\openssl_installer_64.exe"
    
    powershell -Command "Invoke-WebRequest -Uri 'https://slproweb.com/download/Win64OpenSSL_Light-3_5_5.exe' -OutFile '%DOWNLOAD_PATH%'" && (
        echo [+] OpenSSL 64-bit installer downloaded
    ) || (
        echo [ERROR] Failed to download OpenSSL installer
        exit /b 1
    )

    echo [+] Launching OpenSSL 64-bit installer...
    echo [+] Please complete the installation wizard
    echo.
    
    start /wait "" "%DOWNLOAD_PATH%"
    
    echo [+] Installer closed, verifying installation...
    
    if exist "%SYSTEM_SSL_PATH%" (
        echo [+] OpenSSL 64-bit installation complete
        del "%DOWNLOAD_PATH%" 2>nul
    ) else (
        echo.
        echo [ERROR] OpenSSL 64-bit installation failed or was cancelled
        echo [ERROR] Expected: C:\Program Files\OpenSSL-Win64\bin\openssl.exe
        del "%DOWNLOAD_PATH%" 2>nul
        exit /b 1
    )
) else (
    echo [OK] OpenSSL 64-bit already installed
)

REM ===============================
REM pip + 64-bit requirements
REM ===============================
echo [+] Installing Python dependencies (64-bit)
"%PY_DIR%\python.exe" -m pip install --no-warn-script-location --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

"%PY_DIR%\python.exe" -m pip install --no-warn-script-location -r "%TESTING_DIR%\requirements_64.txt" && (
    echo [+] 64-bit dependencies installation complete
) || (
    echo [ERROR] Failed to install dependencies
    exit /b 1
)

REM Verify cryptography package
echo [+] Verifying cryptography package
"%PY_DIR%\python.exe" -c "import cryptography; print('[OK] cryptography', cryptography.__version__)" || (
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
echo    Python %PY_VERSION% (64-bit): %PY_DIR%
echo    OpenSSL 3.5.5 LTS (64-bit): C:\Program Files\OpenSSL-Win64
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0
