@echo off
rem The project health check: every automated test (includes one real OCR run on a synthetic PDF).
cd /d "%~dp0"
".venv\Scripts\python.exe" -m unittest discover -s tests -t . %*
