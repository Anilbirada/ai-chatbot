@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Creating virtual environment...
  py -3 -m venv .venv
  if errorlevel 1 (
    echo.
    echo Could not create the virtual environment.
    echo Install Python 3.10+ and try again.
    pause
    exit /b 1
  )
)
call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if not exist ".env" copy ".env.example" ".env" >nul
python app.py
endlocal
