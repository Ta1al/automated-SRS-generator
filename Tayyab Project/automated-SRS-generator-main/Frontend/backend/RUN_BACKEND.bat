@echo off
title 🚀 Backend Server - AutoSRS.ai
color 0A
cls

echo.
echo ╔════════════════════════════════════════════════════════╗
echo ║   🚀 Backend Server - AutoSRS.ai Authentication        ║
echo ╚════════════════════════════════════════════════════════╝
echo.

cd /d "D:\up dated Final_year_Project\backend"

echo ✅ Starting Backend Server on port 5000...
echo.
echo 📍 API URL: http://localhost:5000
echo 📝 API Docs: http://localhost:5000/api
echo 🔐 Database: chatbot_db
echo.
echo Waiting for connections...
echo.

npm start

pause
