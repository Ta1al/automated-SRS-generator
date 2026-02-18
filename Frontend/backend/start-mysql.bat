@echo off
REM Start MySQL Server on Windows
echo.
echo 🚀 Starting MySQL Server...
echo.

REM Check if MySQL80 service exists (default MySQL 8.0 name)
sc query MySQL80 >nul 2>&1
if %errorlevel% equ 0 (
    net start MySQL80
    echo.
    echo ✅ MySQL80 service started!
    echo.
) else (
    REM Try MySQL service
    sc query MySQL >nul 2>&1
    if %errorlevel% equ 0 (
        net start MySQL
        echo.
        echo ✅ MySQL service started!
        echo.
    ) else (
        echo.
        echo ❌ MySQL service not found!
        echo.
        echo Please check:
        echo 1. MySQL is installed
        echo 2. Service name is correct (MySQL80, MySQL, etc.)
        echo 3. Run this script as Administrator
        echo.
        pause
        exit /b 1
    )
)

echo.
echo 💡 MySQL is ready! Now you can start the backend:
echo.
echo    npm start
echo.
echo 📊 To check database, run:
echo.
echo    mysql -u root -p
echo.
pause
