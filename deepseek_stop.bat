@echo off
REM ============================================================================
REM  Sonario - stop the background DeepSeek server.
REM  Use this if you want to free port 8001 or sign in fresh.
REM ============================================================================
title Sonario - stop DeepSeek server
echo.
echo   Stopping any DeepSeek server running on port 8001...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8001" ^| findstr "LISTENING"') do (
  echo   Stopping process %%p ...
  taskkill /PID %%p /F >nul 2>&1
)
echo   Done. The DeepSeek server is stopped.
echo.
pause
