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

echo Checking for java...
where java >nul 2>nul
if %errorlevel% neq 0 (
    echo Java not found. Installing OpenJDK 17...
    winget install Microsoft.OpenJDK.17 --accept-package-agreements --accept-source-agreements
) else (
    echo Java is installed.
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
where tailscale >nul 2>nul
if %errorlevel% neq 0 (
    echo Tailscale not found. Installing...
    winget install Tailscale.Tailscale --accept-package-agreements --accept-source-agreements
) else (
    echo Tailscale is installed.
)

echo Configuring rclone...
if not exist .env (
    echo .env file not found. Please ensure it exists with S3 setup.
    exit /b
)

for /f "usebackq tokens=1* delims==" %%A in (".env") do (
    set "%%A=%%B"
)

rclone config create b2_mc s3 provider=Other endpoint=%S3_ENDPOINT% access_key_id=%S3_ACCESS_KEY% secret_access_key=%S3_SECRET_KEY% env_auth=false

echo Setup complete. Please restart your terminal before running launcher.py to ensure all new tools are in your PATH.
