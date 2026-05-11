web: gunicorn homely_core.asgi:application -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:$PORT
worker: celery -A homely_core worker -l info
