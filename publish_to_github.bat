@echo off
rem Put Jarvis on GitHub as a public repo. Double-click this file.
rem Safe to run again later: it just commits and pushes any new changes.
cd /d "%~dp0"

echo === Checking Git ===
where git >nul 2>&1
if errorlevel 1 (
    echo Git isn't installed. Installing it now...
    winget install -e --id Git.Git --accept-package-agreements --accept-source-agreements
    echo.
    echo Git installed. Close this window and double-click publish_to_github.bat again.
    pause
    exit /b 0
)

echo === Checking GitHub CLI ===
where gh >nul 2>&1
if errorlevel 1 (
    echo GitHub CLI isn't installed. Installing it now...
    winget install -e --id GitHub.cli --accept-package-agreements --accept-source-agreements
    echo.
    echo GitHub CLI installed. Close this window and double-click publish_to_github.bat again.
    pause
    exit /b 0
)

echo === Logging in to GitHub ===
gh auth status >nul 2>&1
if errorlevel 1 (
    echo A code will appear below and your browser will open. Paste the code and approve.
    gh auth login --hostname github.com --git-protocol https --web
    if errorlevel 1 goto failed
)
gh auth setup-git

rem Commits use GitHub's private no-reply address, so your real email stays private.
for /f "delims=" %%i in ('gh api user --jq .login') do set "GHUSER=%%i"
for /f "delims=" %%i in ('gh api user --jq .id') do set "GHID=%%i"
echo Logged in as %GHUSER%

echo.
echo === Committing ===
if not exist .git git init -b main
git config user.name "%GHUSER%"
git config user.email "%GHID%+%GHUSER%@users.noreply.github.com"
git add .
git diff --cached --quiet
if errorlevel 1 (
    git commit -m "Jarvis v1: voice loop and HUD"
    if errorlevel 1 goto failed
) else (
    echo Nothing new to commit.
)

echo.
echo === Uploading ===
git remote get-url origin >nul 2>&1
if errorlevel 1 (
    gh repo create jarvis --public --source=. --remote=origin --push --description "Voice assistant with local speech (Whisper + Kokoro), a Claude Code brain and a live browser HUD"
    if errorlevel 1 goto failed
) else (
    git push -u origin main
    if errorlevel 1 goto failed
)

echo.
echo === Done. Opening your repo... ===
gh repo view --web
pause
exit /b 0

:failed
echo.
echo Something went wrong. Screenshot this window and send it to Claude.
pause
exit /b 1
