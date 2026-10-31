@echo off
rem Start the Jarvis HUD. Double-click this file.
cd /d "%~dp0"
echo Checking packages...
python -m uv pip install --quiet --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 (
    echo Package install failed. Screenshot this and send it to Claude.
    pause
    exit /b 1
)
.venv\Scripts\python.exe server.py
pause
