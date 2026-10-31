@echo off
rem Start Jarvis. Double-click this file.
cd /d "%~dp0"
call .venv\Scripts\activate.bat
python talk.py
pause
