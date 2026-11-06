@echo off
setlocal
cd /d "%~dp0"
if errorlevel 1 exit /b 1
if not exist data mkdir data
python -B import_places.py samples/pilot_osm.json --db data/pilot.sqlite
if errorlevel 1 goto failed
python -B demo_web.py --pilot-db data/pilot.sqlite --open-browser
if not errorlevel 1 exit /b 0
:failed
pause
exit /b 1
