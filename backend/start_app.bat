@echo off
rem Start the Claim Verifier review window from this project's own environment.
cd /d "%~dp0"
".venv\Scripts\python.exe" -m app
