@echo off
cd /d "%~dp0"
if not exist .env (
  copy /Y judge-demo.env.example .env >nul
  echo Golden demo safe settings were created in .env.
)
if not exist .venv (
  where py >nul 2>nul
  if errorlevel 1 (
    python -m venv .venv
  ) else (
    py -3 -m venv .venv
  )
)
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe -m streamlit run app.py
pause
