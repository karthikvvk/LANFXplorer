@echo off
setlocal enabledelayedexpansion

REM ===============================
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
    echo [✓] Python already present
)

REM ===============================
REM OpenSSL 3.5 LTS standalone  
REM ===============================
if not exist "%SSL_DIR%\bin\openssl.exe" (
    echo [+] Installing OpenSSL 3.5 LTS (standalone)

    powershell -Command "Invoke-WebRequest -Uri 'https://download.firedaemon.com/FireDaemon-OpenSSL/openssl-3.5.4.zip' -OutFile '%OPT_DIR%\openssl.zip'" && (
        echo [+] OpenSSL download complete
    ) || (
        echo [ERROR] Failed to download OpenSSL
        exit /b 1
    )

    powershell -Command "Expand-Archive '%OPT_DIR%\openssl.zip' '%SSL_DIR%' -Force" && (
        echo [+] OpenSSL extraction complete
        del "%OPT_DIR%\openssl.zip"
    ) || (
        echo [ERROR] Failed to extract OpenSSL
        exit /b 1
    )
) else (
    echo [✓] OpenSSL already present
)

REM ===============================
REM pip + requirements
REM ===============================
echo [+] Installing Python dependencies
"%PY_DIR%\python.exe" -m pip install --upgrade pip && (
    echo [+] pip upgrade complete
) || (
    echo [ERROR] Failed to upgrade pip
    exit /b 1
)

"%PY_DIR%\python.exe" -m pip install -r "%APP_DIR%\requirements.txt" && (
    echo [+] Dependencies installation complete
) || (
    echo [ERROR] Failed to install dependencies
    exit /b 1
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
echo [✓] Installation completed successfully!
echo ================================================
echo    Python 3.9.1: %PY_DIR%
echo    OpenSSL 3.3.5 LTS: %SSL_DIR%
echo    Desktop shortcut created
echo ================================================
echo.

pause
exit /b 0

:error
echo.
echo ================================================
echo [!] Installation failed!
echo ================================================
echo Please check the error messages above.
echo You may need to run this script again.
echo ================================================
echo.
pause
exit /b 1
