@echo off
setlocal
cd /d "%~dp0"

if "%PORT%"=="" set PORT=8000
if "%HOST%"=="" set HOST=0.0.0.0

where python >nul 2>&1
if errorlevel 1 (
  echo python is required but was not found on PATH.
  exit /b 1
)

if not exist venv (
  echo Creating virtualenv...
  python -m venv venv
)

call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul
python -m pip install -r requirements.txt
echo NearestExchange listening on %HOST%:%PORT%
python -m uvicorn main:app --host %HOST% --port %PORT%
