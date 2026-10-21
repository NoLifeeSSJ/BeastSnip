@echo off
if not exist "%~dp0.venv\Scripts\pythonw.exe" (
  echo Run Install.ps1 first.
  pause
  exit /b 1
)
start "BeastSnip" /D "%~dp0" "%~dp0.venv\Scripts\pythonw.exe" "%~dp0run_beastsnip.py"
