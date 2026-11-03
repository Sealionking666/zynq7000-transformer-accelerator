@echo off
setlocal
cd /d "%~dp0"
if defined FUSION_DEMO_PYTHON (
  "%FUSION_DEMO_PYTHON%" -X utf8 -B server.py %*
) else (
  py -3 -X utf8 -B server.py %*
)
if errorlevel 1 pause
