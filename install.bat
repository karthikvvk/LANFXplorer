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

    powershell -Command ^
      "Invoke-WebRequest ^
      -Uri 'https://www.python.org/ftp/python/3.9.1/python-3.9.1-embed-amd64.zip' ^
      -OutFile '%OPT_DIR%\python39.zip'"

    powershell -Command ^
      "Expand-Archive '%OPT_DIR%\python39.zip' '%PY_DIR%' -Force"

    del "%OPT_DIR%\python39.zip"

    REM Enable site-packages
    for %%f in ("%PY_DIR%\python*._pth") do (
        powershell -Command ^
          "(Get-Content '%%f') -replace '#import site','import site' | Set-Content '%%f'"
    )

    REM Install pip
    echo [+] Installing pip
    powershell -Command ^
      "Invoke-WebRequest ^
      -Uri 'https://bootstrap.pypa.io/pip/3.9/get-pip.py' ^
      -OutFile '%OPT_DIR%\get-pip.py'"

    "%PY_DIR%\python.exe" "%OPT_DIR%\get-pip.py"
    del "%OPT_DIR%\get-pip.py"

) else (
    echo [✓] Python already present
)

REM ===============================
REM OpenSSL standalone (ZIP)
REM ===============================
if not exist "%SSL_DIR%\bin\openssl.exe" (
    echo [+] Installing OpenSSL (standalone)

    powershell -Command ^
      "Invoke-WebRequest ^
      -Uri 'https://slproweb.com/download/Win64OpenSSL-3_2_1.zip' ^
      -OutFile '%OPT_DIR%\openssl.zip'"

    powershell -Command ^
      "Expand-Archive '%OPT_DIR%\openssl.zip' '%SSL_DIR%' -Force"

    del "%OPT_DIR%\openssl.zip"
) else (
    echo [✓] OpenSSL already present
)

REM ===============================
REM pip + requirements
REM ===============================
echo [+] Installing Python dependencies
"%PY_DIR%\python.exe" -m pip install --upgrade pip
"%PY_DIR%\python.exe" -m pip install -r "%APP_DIR%\requirements.txt"

REM ===============================
REM Desktop shortcut
REM ===============================
echo [+] Creating desktop shortcut

set "SHORTCUT=%USERPROFILE%\Desktop\LANFXplorer.lnk"

powershell -Command ^
 "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%SHORTCUT%'); ^
  $s.TargetPath='%APP_DIR%\app.bat'; ^
  $s.WorkingDirectory='%APP_DIR%'; ^
  $s.Description='LANFXplorer'; ^
  $s.Save()"

REM ===============================
REM Mark install complete
REM ===============================
type nul > "%APP_DIR%\.installed"

echo.
echo [✓] Installation complete (Flutter-safe)
echo.

pause
