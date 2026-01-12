# Running Homely Backend Services

## Quick Start (All Services)

Run this command to start all services at once:
```bash
activate_venv_and_run.bat
```

This will open 3 separate windows:
1. **Redis Server** - Message broker and cache
2. **Django Server** - API server (http://127.0.0.1:8000)
3. **Celery Worker** - Background task processor

---

## Running Services Individually

### 1. Redis Server
**Required for:** WebSockets (Channels), Celery tasks, Django cache

#### Windows Installation:
Download Redis for Windows from:
- Microsoft Archive: https://github.com/microsoftarchive/redis/releases
- Or use WSL2 with Redis

#### Start Redis:
```bash
redis-server
```

Default runs on: `redis://127.0.0.1:6379`

---

### 2. Django Development Server
```bash
.venv\Scripts\activate
python manage.py runserver
```

Runs on: http://127.0.0.1:8000

---

### 3. Celery Worker
```bash
.venv\Scripts\activate
celery -A homely_core worker --loglevel=info --pool=solo
```

Or use the batch script:
```bash
run_celery_worker.bat
```

**Note:** Windows requires `--pool=solo` flag for Celery

---

### 4. Celery Beat (Optional - for scheduled tasks)
```bash
.venv\Scripts\activate
celery -A homely_core beat --loglevel=info
```

Or use the batch script:
```bash
run_celery_beat.bat
```

---

## Service Dependencies

```
Redis Server (Port 6379)
    ├── Django Channels (DB 0) - WebSocket layer
    ├── Django Cache (DB 1) - Application cache
    └── Celery (DB 2) - Task queue & results

Django Server (Port 8000)
    ├── Depends on: Database (SQLite/PostgreSQL)
    └── Optional: Redis for channels/cache

Celery Worker
    ├── Depends on: Redis (broker + backend)
    └── Depends on: Django (tasks in property.tasks)
```

---

## Stopping Services

- Close the individual terminal windows, OR
- Press `Ctrl+C` in each window

---

## Troubleshooting

### Redis Connection Error
**Error:** `Error 10061: No connection could be made`

**Solution:**
1. Check if Redis is running: `redis-cli ping` (should return "PONG")
2. Install Redis if not installed
3. Check REDIS_URL in .env matches Redis server address

### Celery Worker Won't Start
**Error:** `ValueError: not enough values to unpack`

**Solution:** Add `--pool=solo` flag on Windows

### Port Already in Use
**Error:** `Port 8000 is already in use`

**Solution:**
- Kill existing process: `netstat -ano | findstr :8000` then `taskkill /PID <pid> /F`
- Or use different port: `python manage.py runserver 8001`

---

## Production Deployment

For production, replace these development servers with:
- **Redis:** Redis Cloud, AWS ElastiCache, or self-hosted Redis cluster
- **Django:** Gunicorn/uWSGI + Nginx
- **Celery:** Supervisor or systemd service
- **Celery Beat:** Single instance with supervisor

See deployment documentation for details.
