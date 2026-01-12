@echo off
REM Start Celery beat scheduler for Windows development

echo Starting Celery beat...
celery -A homely_core beat --loglevel=info
