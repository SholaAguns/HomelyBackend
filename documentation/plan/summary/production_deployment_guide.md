# Homely — Production Deployment Guide
*Written: 2026-05-14 | Updated: 2026-06-01 | Platform: Railway*

---

## Overview

| Service | Technology | Deploy method |
|---------|-----------|--------------|
| **Backend** (API) | Django + Uvicorn (ASGI) | Railway — Dockerfile |
| **Celery worker** | Celery + Redis | Railway — same image, override start command |
| **FlareSolverr** | FlareSolverr Docker image | Railway — custom Docker service |
| **Frontend** | Angular → nginx | Railway — multi-stage Dockerfile |
| **Database** | PostgreSQL 16 | Railway Postgres plugin |
| **Cache / broker** | Redis 7 | Railway Redis plugin |

---

## Pre-Deployment Checklist

Before touching Railway, complete these steps once:

- [ ] Rotate `SECRET_KEY` — generate a new one: `python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"`
- [ ] Generate a separate `JWT_SIGNING_KEY` (keeps sessions alive across `SECRET_KEY` rotations)
- [ ] Rotate `GOOGLE_MAPS_API_KEY` (restrict to Railway IP range in Google Cloud Console)
- [ ] Rotate all four Ofcom API keys
- [ ] Set up Google OAuth credentials (`GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`) in Google Cloud Console — add Railway backend URL to authorised redirect URIs
- [ ] Confirm backend repo does **not** have `db.sqlite3` committed (`*.sqlite3` is in `.gitignore`)
- [ ] Confirm `.env` is not committed to git
- [ ] Confirm `DEBUG=False` is enforced in `prod.py` (it is)

---

## Part 1 — Railway Project Setup

### 1.1 Create project

1. Log in to [railway.app](https://railway.app) → **New Project**
2. Name it `homely`

### 1.2 Add Postgres

1. In the project → **+ New** → **Database** → **PostgreSQL**
2. Railway auto-sets `DATABASE_URL` in the plugin's environment — note the value for later

### 1.3 Add Redis

1. **+ New** → **Database** → **Redis**
2. Railway auto-sets `REDIS_URL` — note the value

---

## Part 2 — Backend Deployment

### 2.1 Create the backend service

1. **+ New** → **GitHub Repo** → select `HomelyBackend`
2. Railway will detect the `Dockerfile` automatically
3. Leave **Start command** blank — the Dockerfile `CMD` runs gunicorn
4. Set **Root directory** → `/` (default)

### 2.2 Backend environment variables

Set all of the following in Railway → **Backend service** → **Variables**:

```
# Required — will crash on startup if missing
SECRET_KEY=<generate with python command above>
DATABASE_URL=<auto-set by Railway Postgres plugin>
REDIS_URL=<auto-set by Railway Redis plugin>
DJANGO_SETTINGS_MODULE=homely_core.settings.prod

# Celery (use same Redis instance, different DB number)
CELERY_BROKER_URL=<same as REDIS_URL>/2
CELERY_RESULT_BACKEND=<same as REDIS_URL>/2

# Allowed hosts — your Railway domain (add custom domain later)
ALLOWED_HOSTS=<your-backend>.up.railway.app

# CORS — allow your frontend domain
CORS_ALLOWED_ORIGINS=https://<your-frontend>.up.railway.app

# JWT — separate signing key so SECRET_KEY rotation doesn't log everyone out
JWT_SIGNING_KEY=<generate a separate random string>

# Frontend URL (used for invite links in emails)
FRONTEND_URL=https://<your-frontend>.up.railway.app

# Google OAuth
GOOGLE_CLIENT_ID=<from Google Cloud Console>
GOOGLE_CLIENT_SECRET=<from Google Cloud Console>

# Google Maps (POI service)
GOOGLE_MAPS_API_KEY=<rotated key>
POI_RESULTS_LIMIT=3

# Ofcom (broadband + mobile coverage)
OFCOM_BROADBAND_API_KEY_PRIMARY=<rotated key>
OFCOM_BROADBAND_API_KEY_SECONDARY=<rotated key>
OFCOM_MOBILE_API_KEY_PRIMARY=<rotated key>
OFCOM_MOBILE_API_KEY_SECONDARY=<rotated key>

# FlareSolverr (required for Zoopla scraping — see Part 4)
FLARESOLVERR_URL=http://<flaresolverr-service>.railway.internal:8191/v1

# Email (use Gmail App Password or SendGrid)
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=<your gmail>
EMAIL_HOST_PASSWORD=<gmail app password>
DEFAULT_FROM_EMAIL=noreply@homely.app

# Logging
PROPERTY_LOG_LEVEL=WARNING
HOMELY_CORE_LOG_LEVEL=WARNING

# Signup whitelist — comma-separated emails allowed to register
# Leave empty to allow open signup; set during live deployment rehearsal
SIGNUP_EMAIL_WHITELIST=email1@example.com,email2@example.com
```

> **Important:** `DATABASE_URL` and `REDIS_URL` can be shared from the plugin
> using Railway's variable reference syntax: `${{Postgres.DATABASE_URL}}`

> **Railway TLS termination:** Railway terminates HTTPS at their load balancer and
> forwards plain HTTP to the container. `prod.py` sets `SECURE_SSL_REDIRECT=True`
> and `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` so Django
> trusts Railway's `X-Forwarded-Proto` header. Without this, every request would
> redirect infinitely. Do **not** remove `SECURE_PROXY_SSL_HEADER` from prod.py.

### 2.3 Add the Celery worker service

The worker runs the same Docker image with a different start command.

1. **+ New** → **GitHub Repo** → same `HomelyBackend` repo
2. Rename the service to `celery-worker`
3. Set **Start command**: `celery -A homely_core worker -l info`
4. Copy all environment variables from the backend service (Railway allows referencing another service's vars with `${{backend-service.VARIABLE_NAME}}`)

### 2.4 First deploy — run migrations

The Dockerfile already runs `collectstatic` during the build step. Migrations must be run manually on first deploy:

1. After the first deploy succeeds, open **Backend service** → **Shell** (or use Railway CLI):
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

2. For subsequent deploys, add a **release command** in Railway service settings:
   ```
   python manage.py migrate
   ```
   (`collectstatic` is handled at image build time — no need to repeat it here)

### 2.5 Verify backend

```bash
# Health check — should return {"status": "ok"}
curl https://<your-backend>.up.railway.app/health/

# API should require auth
curl https://<your-backend>.up.railway.app/api/accounts/users/me/
# Expected: 401 Unauthorized
```

---

## Part 3 — Frontend Deployment

### 3.1 Create the frontend service

1. **+ New** → **GitHub Repo** → select `HomelyFrontend`
2. Railway will detect the `Dockerfile`
3. Set **Root directory** → `/` (default)

### 3.2 Frontend environment variables

Set in Railway → **Frontend service** → **Variables**:

```
# Runtime URL injection — injected into env.js by docker-entrypoint.sh
API_URL=https://<your-backend>.up.railway.app/api
WS_URL=wss://<your-backend>.up.railway.app/ws
```

> These override the compiled `environment.prod.ts` fallbacks without requiring a rebuild.
> The `docker-entrypoint.sh` runs `envsubst` on `env.template.js` → `env.js` at container start.

### 3.3 Verify frontend

```bash
# Should return 200 with Angular app HTML
curl -I https://<your-frontend>.up.railway.app/

# Deep-link routing — should return 200 (not 404)
curl -I https://<your-frontend>.up.railway.app/projects/some-uuid

# env.js should contain your Railway URLs (not the template placeholders)
curl https://<your-frontend>.up.railway.app/assets/env.js
# Expected: window.__env = { apiUrl: 'https://...', wsUrl: 'wss://...' }
```

---

## Part 4 — FlareSolverr Deployment

FlareSolverr is required for Zoopla search scraping. It is a Cloudflare bypass proxy that runs as a separate service.

### 4.1 Create the FlareSolverr service

1. In the Railway project → **+ New** → **Docker Image**
2. Image: `ghcr.io/flaresolverr/flaresolverr:latest`
3. Rename the service to `flaresolverr`
4. Set **Port** → `8191`

### 4.2 FlareSolverr environment variables

```
LOG_LEVEL=info
LOG_HTML=false
CAPTCHA_SOLVER=none
TZ=Europe/London
```

### 4.3 Wire backend to FlareSolverr

Railway services communicate over an internal network using the service name as hostname. Set on the **backend** and **celery-worker** services:

```
FLARESOLVERR_URL=http://flaresolverr.railway.internal:8191/v1
```

> The `.railway.internal` hostname is only accessible within the same Railway project.
> Do **not** expose FlareSolverr publicly — it has no authentication.

### 4.4 Verify FlareSolverr

```bash
# From the Railway backend shell:
curl http://flaresolverr.railway.internal:8191/v1 -s | python -m json.tool
# Expected: {"msg": "FlareSolverr is ready!", ...}
```

---

## Part 5 — Custom Domain (optional)

### Backend
1. Railway → Backend service → **Settings** → **Domains** → **Custom Domain**
2. Add `api.homely.app`
3. Update `ALLOWED_HOSTS` env var to include `api.homely.app`
4. Update `CORS_ALLOWED_ORIGINS` to include `https://homely.app`

### Frontend
1. Railway → Frontend service → **Settings** → **Domains** → **Custom Domain**
2. Add `homely.app`
3. Update `API_URL` to `https://api.homely.app/api`
4. Update `WS_URL` to `wss://api.homely.app/ws`
5. Redeploy frontend (triggers `envsubst` with new values — no rebuild needed)

---

## Part 6 — Post-Deploy Smoke Tests

Run through these manually after each deploy:

| Test | Expected result |
|------|----------------|
| `GET /health/` | `{"status": "ok"}` 200 |
| `GET /api/accounts/users/me/` (no cookie) | 401 Unauthorized |
| Register with whitelisted email | Account created, email verification received |
| Register with non-whitelisted email | 400 — "This email is not authorised to register." |
| Log in | Session cookie set, redirected to `/projects` |
| Create a project | Project appears in list |
| Create blank property list | List created immediately, no scraping started |
| Create property list with search criteria | Scraping tasks queued, SSE progress visible |
| HTML batch import (Rightmove) | Properties created, summary counts returned |
| Add single property via URL | Property card renders |
| Run Stage 2 on a property | SSE progress visible, context reports populate |
| Run Stage 3 | Rating calculated and displayed |
| WebSocket notifications | Real-time updates appear without page refresh |
| FlareSolverr health (from backend shell) | `{"msg": "FlareSolverr is ready!"}` |

---

## Part 7 — Rollback

Railway keeps previous deploys. To rollback:

1. Railway → Service → **Deployments** tab
2. Click the previous green deploy → **Redeploy**

For database rollback (if migrations ran):
```bash
# List migrations
python manage.py showmigrations

# Rollback to specific migration
python manage.py migrate <app_name> <migration_name>
```

---

## Part 8 — Monitoring

| Signal | Where to look |
|--------|--------------|
| App errors | Railway → Service → **Logs** |
| Health | `GET /health/` from uptime monitor (UptimeRobot, etc.) |
| DB connections | Railway Postgres plugin → **Metrics** |
| Redis memory | Railway Redis plugin → **Metrics** |
| Celery queue depth | Add `flower` for Celery monitoring (optional) |
| FlareSolverr | Railway → flaresolverr service → **Logs** |

---

## Environment Variable Reference

### Backend (all required in prod)

| Variable | Source | Notes |
|----------|--------|-------|
| `SECRET_KEY` | Generate | Rotate without invalidating sessions if `JWT_SIGNING_KEY` is also set |
| `DATABASE_URL` | Railway Postgres | Auto-set by plugin |
| `REDIS_URL` | Railway Redis | Auto-set by plugin |
| `CELERY_BROKER_URL` | Derived from `REDIS_URL` | Append `/2` |
| `CELERY_RESULT_BACKEND` | Derived from `REDIS_URL` | Append `/2` |
| `DJANGO_SETTINGS_MODULE` | Manual | `homely_core.settings.prod` |
| `ALLOWED_HOSTS` | Manual | Comma-separated Railway + custom domains |
| `CORS_ALLOWED_ORIGINS` | Manual | Comma-separated frontend URLs |
| `JWT_SIGNING_KEY` | Generate | Keeps sessions alive across `SECRET_KEY` rotations |
| `FRONTEND_URL` | Manual | Used in invite email links |
| `GOOGLE_CLIENT_ID` | Google Cloud Console | Google OAuth login |
| `GOOGLE_CLIENT_SECRET` | Google Cloud Console | Google OAuth login |
| `GOOGLE_MAPS_API_KEY` | Google Cloud Console | POI service |
| `POI_RESULTS_LIMIT` | Manual | Default `3` — max POI results per category |
| `OFCOM_BROADBAND_API_KEY_PRIMARY` | Ofcom portal | Broadband coverage |
| `OFCOM_BROADBAND_API_KEY_SECONDARY` | Ofcom portal | Failover key |
| `OFCOM_MOBILE_API_KEY_PRIMARY` | Ofcom portal | Mobile coverage |
| `OFCOM_MOBILE_API_KEY_SECONDARY` | Ofcom portal | Failover key |
| `FLARESOLVERR_URL` | Internal Railway URL | `http://flaresolverr.railway.internal:8191/v1` |
| `EMAIL_HOST` | Manual | Default `smtp.gmail.com` |
| `EMAIL_PORT` | Manual | Default `587` |
| `EMAIL_HOST_USER` | Gmail / SendGrid | SMTP credentials |
| `EMAIL_HOST_PASSWORD` | Gmail App Password | Not your account password |
| `DEFAULT_FROM_EMAIL` | Manual | Default `noreply@homely.com` |
| `SIGNUP_EMAIL_WHITELIST` | Manual | Comma-separated emails; empty = open signup |
| `PROPERTY_LOG_LEVEL` | Manual | `WARNING` in prod |
| `HOMELY_CORE_LOG_LEVEL` | Manual | `WARNING` in prod |

### Frontend

| Variable | Notes |
|----------|-------|
| `API_URL` | Full URL to backend API e.g. `https://api.homely.app/api` |
| `WS_URL` | WebSocket URL e.g. `wss://api.homely.app/ws` |

---

## Common Issues

**Backend won't start — `ImproperlyConfigured: DATABASE_URL...`**
→ Postgres plugin not linked to backend service. Check Railway variable references.

**Backend won't start — `ImproperlyConfigured: REDIS_URL...`**
→ Redis plugin not linked. Same fix.

**SSL redirect loop (ERR_TOO_MANY_REDIRECTS)**
→ Railway terminates TLS at the load balancer. `prod.py` must have `SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')` set so Django trusts the forwarded header rather than redirecting every request. Confirm it is present in `prod.py`.

**Frontend shows blank page / 404 on refresh**
→ nginx `try_files` is configured correctly — verify `nginx.conf` was included in Docker build.

**`env.js` still contains `${API_URL}` placeholders**
→ `API_URL` / `WS_URL` env vars not set in Railway frontend service. Set them and redeploy.

**WebSocket connections failing**
→ Check `WS_URL` starts with `wss://` (not `ws://`). Railway terminates TLS.

**Cookies not sent cross-origin**
→ `JWT_AUTH_COOKIE_SAMESITE=None` and `JWT_AUTH_COOKIE_SECURE=True` are set in prod.py.
  Ensure frontend and backend are on different subdomains (not different ports on localhost).

**Celery tasks not executing**
→ Check celery-worker service is running and shares the same `REDIS_URL` as the backend.
  Check logs: Railway → celery-worker → Logs.

**Zoopla scraping fails — FlareSolverr 500 errors**
→ Check FlareSolverr service is running: Railway → flaresolverr → Logs.
  Confirm `FLARESOLVERR_URL` on both backend and celery-worker points to `http://flaresolverr.railway.internal:8191/v1`.
  FlareSolverr may time out on heavy Cloudflare challenges — this is expected occasionally; Celery will retry.

**FlareSolverr not reachable from backend shell**
→ Services must be in the same Railway project to use `.railway.internal` hostnames.
  Verify the service name matches exactly (Railway uses the service name as the hostname).

**Static files 404**
→ `collectstatic` runs during the Docker image build step. If static files are missing, trigger a fresh deploy (not a redeploy of an existing image). Check the build logs for collectstatic errors.

**Google OAuth redirect mismatch**
→ Add `https://<your-backend>.up.railway.app/accounts/google/login/callback/` to authorised redirect URIs in Google Cloud Console. Update when switching to a custom domain.
