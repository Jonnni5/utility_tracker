@echo off
if not "%1"=="min" start /min cmd /c "%0 min" & exit /b
powershell.exe -ExecutionPolicy Bypass -Command "cd 'G:\Project\utility_tracker'; & '.\venv\Scripts\Activate.ps1'; python '.\main.py'; exit"