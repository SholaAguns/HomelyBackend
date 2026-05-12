from .base import *

DEBUG=True
ALLOWED_HOSTS=['*']

# Development-specific CORS
CORS_ALLOW_ALL_ORIGINS = True

# Email backend for development (console)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable email verification for development
ACCOUNT_EMAIL_VERIFICATION = 'optional'

# JWT Cookie — Lax works same-origin in dev; Secure not needed without HTTPS
JWT_AUTH_COOKIE_SECURE = False
JWT_AUTH_COOKIE_SAMESITE = 'Lax'