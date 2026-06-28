@echo off
REM ============================================================================
REM  Sonario - stop the background Windows Copilot server.
REM  Use this if you want to free port 8000 or sign in fresh.
REM ============================================================================
title Sonario - stop Copilot server
echo.
echo   Stopping any Copilot server running on port 8000...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
  echo   Stopping process %%p ...
  taskkill /PID %%p /F >nul 2>&1
)
echo   Done. The Copilot server is stopped.
echo.
pause
