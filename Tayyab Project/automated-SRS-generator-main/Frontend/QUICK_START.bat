@echo off
title Authentication System - Setup & Run
color 0A
cls

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║   🚀 AutoSRS.ai - Authentication System Setup          ║
echo ║      Complete Setup & Run Script                       ║
echo ╚════════════════════════════════════════════════════════╝
echo.

REM Change to project directory
cd /d "D:\up dated Final_year_Project"

echo ⏳ Step 1: Starting MySQL Service...
echo.
net start MySQL80 >nul 2>&1
if errorlevel 1 (
    echo ⚠️  MySQL might already be running or service name incorrect
    echo    Attempting to continue...
) else (
    echo ✅ MySQL started successfully
)
timeout /t 2 >nul

echo.
echo ⏳ Step 2: Setting up database...
echo.
cd /d "D:\up dated Final_year_Project\backend"

REM Check if setup has been done before
if exist "database_setup_complete.txt" (
    echo ✅ Database already setup (skipping)
) else (
    echo Running setup-database.sql...
    echo Please enter your MySQL root password when prompted below:
    echo.
    mysql -u root -p < setup-database.sql
    if errorlevel 1 (
        echo ❌ Database setup failed. Check your MySQL password in .env
        echo.
        echo Please ensure:
        echo   1. MySQL is running: net start MySQL80
        echo   2. .env file has correct DB_PASSWORD
        echo   3. Run manually: mysql -u root -p^< setup-database.sql
        pause
        exit /b 1
    )
    echo ✅ Database setup complete
    echo. > database_setup_complete.txt
)

echo.
echo ⏳ Step 3: Installing backend dependencies...
if exist "node_modules" (
    echo ✅ Dependencies already installed
) else (
    echo Installing npm packages (this may take a minute)...
    call npm install >nul 2>&1
    if errorlevel 1 (
        echo ❌ npm install failed
        echo Run manually: npm install
        pause
        exit /b 1
    )
    echo ✅ Backend dependencies installed
)

echo.
echo ⏳ Step 4: Installing frontend dependencies...
cd /d "D:\up dated Final_year_Project"
if exist "node_modules" (
    echo ✅ Dependencies already installed
) else (
    echo Installing npm packages (this may take a minute)...
    call npm install >nul 2>&1
    if errorlevel 1 (
        echo ❌ npm install failed
        echo Run manually: npm install
        pause
        exit /b 1
    )
    echo ✅ Frontend dependencies installed
)

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║              ✅ Setup Complete!                        ║
echo ╠════════════════════════════════════════════════════════╣
echo ║                                                        ║
echo ║  📋 Next Steps:                                        ║
echo ║                                                        ║
echo ║  1️⃣  Backend Terminal (Window 1):                      ║
echo ║     cd backend                                        ║
echo ║     npm start                                         ║
echo ║     (Runs on port 5000)                              ║
echo ║                                                        ║
echo ║  2️⃣  Frontend Terminal (Window 2):                     ║
echo ║     npm run dev                                       ║
echo ║     (Runs on port 3000)                              ║
echo ║                                                        ║
echo ║  3️⃣  Open Browser:                                     ║
echo ║     http://localhost:3000                            ║
echo ║                                                        ║
echo ║  📚 Full Guide: COMPLETE_SETUP_GUIDE.md                ║
echo ║                                                        ║
echo ║  🧪 Test Flow:                                         ║
echo ║     - Click Sign Up                                  ║
echo ║     - Create account with valid credentials          ║
echo ║     - Should see username in top right               ║
echo ║     - Click Logout to test logout flow               ║
echo ║     - Click Login to test login flow                 ║
echo ║                                                        ║
echo ║  ⚠️  Don't close this terminal until done!             ║
echo ║                                                        ║
echo ╚════════════════════════════════════════════════════════╝
echo.

echo Would you like to start the backend server now? (Y/N)
set /p start_backend=
if /i "%start_backend%"=="Y" (
    echo.
    echo Starting Backend Server...
    echo.
    cd /d "D:\up dated Final_year_Project\backend"
    call npm start
) else (
    echo.
    echo ✋ Manual start required. Run these in separate terminals:
    echo.
    echo Backend:
    echo   cd "D:\up dated Final_year_Project\backend"
    echo   npm start
    echo.
    echo Frontend (in another terminal):
    echo   cd "D:\up dated Final_year_Project"
    echo   npm run dev
    echo.
    pause
)
