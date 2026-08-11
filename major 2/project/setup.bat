@echo off
echo ============================================
echo  Student Data Management System - Setup
echo ============================================

echo.
echo [1/3] Installing Python backend dependencies...
cd backend
pip install -r requirements.txt
cd ..

echo.
echo [2/3] Installing React frontend dependencies...
cd frontend
npm install
cd ..

echo.
echo [3/3] Setup complete!
echo.
echo To start the system:
echo   Backend:  cd backend ^&^& python app.py
echo   Frontend: cd frontend ^&^& npm start
echo.
echo Make sure MySQL is running with:
echo   host: localhost
echo   user: root
echo   password: Manoj@123
echo.
pause
