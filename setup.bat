@echo off
setlocal

echo Checking for Python...
where python >nul 2>nul
if %errorlevel% neq 0 (
    echo Python not found. Installing...
    winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
) else (
    echo Python is installed.
)

echo Checking for Java 25...
set "JAVA_OK=0"
where java >nul 2>nul
if %errorlevel% equ 0 (
    for /f "tokens=3" %%V in ('java -version 2^>^&1 ^| findstr /i "version"') do (
        echo Found Java version %%~V
        echo %%~V | findstr /b "25." >nul 2>nul && set "JAVA_OK=1"
    )
)
if "%JAVA_OK%"=="0" (
    echo Java 25 not found. Installing OpenJDK 25...
    winget install Microsoft.OpenJDK.25 --accept-package-agreements --accept-source-agreements
) else (
    echo Java 25 is installed.
)

echo Checking for rclone...
where rclone >nul 2>nul
if %errorlevel% neq 0 (
    echo rclone not found. Installing...
    winget install Rclone.Rclone --accept-package-agreements --accept-source-agreements
) else (
    echo rclone is installed.
)

echo Checking for Tailscale...
set "TAILSCALE_FOUND=0"
where tailscale >nul 2>nul && set "TAILSCALE_FOUND=1"
if "%TAILSCALE_FOUND%"=="0" (
    if exist "%ProgramFiles%\Tailscale\tailscale.exe" set "TAILSCALE_FOUND=1"
)
if "%TAILSCALE_FOUND%"=="0" (
    if exist "%ProgramFiles(x86)%\Tailscale\tailscale.exe" set "TAILSCALE_FOUND=1"
)
if "%TAILSCALE_FOUND%"=="0" (
    echo Tailscale not found. Installing...
    winget install Tailscale.Tailscale --accept-package-agreements --accept-source-agreements
    echo.
    echo IMPORTANT: After installation, open Tailscale and sign in to your tailnet.
    echo All players must be on the same tailnet to connect to each other.
) else (
    echo Tailscale is installed.
)
REM Refresh PATH so newly installed tools are available in this session
set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
for /f "tokens=2*" %%A in ('reg query "HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment" /v Path 2^>nul') do set "PATH=%%B;%PATH%"
for /f "tokens=2*" %%A in ('reg query "HKCU\Environment" /v Path 2^>nul') do set "PATH=%%B;%PATH%"

echo Configuring rclone remote...
if not exist .env (
    echo .env file not found. Please create it with your B2 credentials.
    exit /b
)

for /f "usebackq tokens=1* delims==" %%A in (".env") do (
    set "%%A=%%B"
)

if "%B2_APP_KEY_ID%"=="" (
    echo B2_APP_KEY_ID is not set in .env. Please fill in your credentials.
    exit /b
)

rclone config create b2_mc b2 account=%B2_APP_KEY_ID% key=%B2_APP_KEY% hard_delete=true

echo.
echo Verifying B2 bucket connection...
rclone lsd b2_mc:%BUCKET_NAME% >nul 2>nul
if %errorlevel% neq 0 (
    echo FAILED: Could not connect to bucket "%BUCKET_NAME%".
    echo   Check your B2_APP_KEY_ID, B2_APP_KEY, and BUCKET_NAME in .env
    exit /b
) else (
    echo SUCCESS: Connected to bucket "%BUCKET_NAME%".
)

echo.
echo Setup complete. Please restart your terminal before running launcher.py to ensure all new tools are in your PATH.
