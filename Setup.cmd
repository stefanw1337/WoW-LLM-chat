@echo off
cd /d "%~dp0"
echo WoW LLM Chat - Setup
set /p "WOW_LLM_CLIENT=Full path to your WoW client folder: "
if not defined WOW_LLM_CLIENT exit /b 1
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0Install.ps1" -WowDirectory "%WOW_LLM_CLIENT%"
if errorlevel 1 goto finish
python -m pip install -r bridge\requirements.txt
:finish
pause
