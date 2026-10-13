@echo off
setlocal
cd /d "%~dp0"
where conda >nul 2>nul
if errorlevel 1 goto fallback
call conda run --no-capture-output -n common python main.py %*
if errorlevel 1 pause
exit /b
:fallback
if exist "D:\Software\miniconda\envs\common\python.exe" (
  "D:\Software\miniconda\envs\common\python.exe" main.py %*
) else (
  echo Please activate the common Conda environment, then run: python main.py
  pause
)
if errorlevel 1 pause
