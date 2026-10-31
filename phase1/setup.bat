@echo off
rem Jarvis Phase 1 - one-off setup. Double-click this file.
rem Uses "uv" to give Jarvis its own Python 3.12, because the speech
rem libraries don't support the newest Python yet. Your main Python is untouched.
cd /d "%~dp0"

echo === Checking Python ===
python --version
if errorlevel 1 (
    echo Python isn't on your PATH. Reinstall Python and tick "Add python.exe to PATH".
    pause
    exit /b 1
)

echo.
echo === Checking Claude Code ===
where claude
if errorlevel 1 (
    echo Can't find Claude Code. Check that "claude --version" works in a new terminal.
    pause
    exit /b 1
)

echo.
echo === Installing uv (Python version manager) ===
python -m pip install --user --upgrade uv
if errorlevel 1 goto failed

echo.
echo === Creating Jarvis's own Python 3.12 environment ===
if exist .venv rmdir /s /q .venv
python -m uv venv --python 3.12 .venv
if errorlevel 1 goto failed

echo.
echo === Installing packages (a few minutes) ===
python -m uv pip install --python .venv\Scripts\python.exe -r requirements.txt
if errorlevel 1 goto failed

echo.
.venv\Scripts\python.exe --version
echo === All done. Double-click run_jarvis.bat to start Jarvis. ===
pause
exit /b 0

:failed
echo.
echo Install failed. Screenshot the error above and send it to Claude.
pause
exit /b 1
