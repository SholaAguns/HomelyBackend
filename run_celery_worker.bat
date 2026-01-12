@echo off
REM Start Celery worker for Windows development

echo Starting Celery worker...
celery -A homely_core worker --loglevel=info --pool=solo
