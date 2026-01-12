@echo off
echo Starting Homely Backend Services...
echo.

REM Start Redis Server (if installed)
echo Starting Redis Server...
start "Redis Server" redis-server
timeout /t 2 /nobreak >nul

REM Start Django Development Server
echo Starting Django Server...
start "Django Server" cmd /k "cd C:/Users/shola/Repos/HomelyBackend/.venv/Scripts && call activate.bat && cd C:/Users/shola/Repos/HomelyBackend && python manage.py runserver"
timeout /t 2 /nobreak >nul

REM Start Celery Worker
echo Starting Celery Worker...
start "Celery Worker" cmd /k "cd C:/Users/shola/Repos/HomelyBackend/.venv/Scripts && call activate.bat && cd C:/Users/shola/Repos/HomelyBackend && celery -A homely_core worker --loglevel=info --pool=solo"

echo.
echo All services started in separate windows.
echo Close this window or press any key to exit...
pause >nul