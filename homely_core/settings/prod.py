from .base import *
import os
from django.core.exceptions import ImproperlyConfigured

DEBUG=False
ALLOWED_HOSTS = [h for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h]

if not os.getenv('DATABASE_URL'):
    raise ImproperlyConfigured("DATABASE_URL environment variable is required in production")

if not os.getenv('REDIS_URL'):
    raise ImproperlyConfigured("REDIS_URL environment variable is required in production")

# Production email settings (configure via environment variables)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.getenv('EMAIL_HOST', 'smtp.gmail.com')
EMAIL_PORT = int(os.getenv('EMAIL_PORT', 587))
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv('EMAIL_HOST_USER', '')
EMAIL_HOST_PASSWORD = os.getenv('EMAIL_HOST_PASSWORD', '')
DEFAULT_FROM_EMAIL = os.getenv('DEFAULT_FROM_EMAIL', 'noreply@homely.com')

# Security settings
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')  # Railway terminates TLS at load balancer
SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
X_FRAME_OPTIONS = 'DENY'

SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'
MIDDLEWARE.append('homely_core.middleware.ContentSecurityPolicyMiddleware')

# CORS - only specific origins in production
CORS_ALLOWED_ORIGINS = [h for h in os.getenv('CORS_ALLOWED_ORIGINS', '').split(',') if h]

# Static files via whitenoise — must be after SecurityMiddleware
MIDDLEWARE.insert(1, 'whitenoise.middleware.WhiteNoiseMiddleware')
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# JWT Cookie — SameSite=None required for cross-origin (api.homely.app ↔ homely.app)
JWT_AUTH_COOKIE_SECURE = True
JWT_AUTH_COOKIE_SAMESITE = 'None'

# Rate limiting
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/min',
        'user': '300/min',
    },
}

# Email verification mandatory in production
ACCOUNT_EMAIL_VERIFICATION = 'mandatory'