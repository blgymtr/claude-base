@echo off
title Claude Base
cd /d "%~dp0"
where py >nul 2>nul && (py -3 server.py) || (python server.py)
if errorlevel 1 pause
