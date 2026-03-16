"""
ASGI config for homely_core project.

It exposes the ASGI callable as a module-level variable named ``application``.

For more information on this file, see
https://docs.djangoproject.com/en/6.0/howto/deployment/asgi/
"""

import os
import logging
from channels.routing import ProtocolTypeRouter, URLRouter
from channels.auth import AuthMiddlewareStack
from django.core.asgi import get_asgi_application

logger = logging.getLogger('homely_core.asgi')

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'homely_core.settings.prod')

logger.info("=" * 80)
logger.info("ASGI APPLICATION INITIALIZATION")
logger.info(f"DJANGO_SETTINGS_MODULE: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
logger.info("=" * 80)

django_asgi_app = get_asgi_application()

from homely_core.routing import websocket_urlpatterns

logger.info("=" * 80)
logger.info("CONFIGURING PROTOCOL TYPE ROUTER")
logger.info(f"WEBSOCKET URL PATTERNS COUNT: {len(websocket_urlpatterns)}")
logger.info("=" * 80)

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(
            websocket_urlpatterns
        )
    ),
})

logger.info("=" * 80)
logger.info("ASGI APPLICATION CONFIGURED SUCCESSFULLY")
logger.info("PROTOCOLS: http, websocket")
logger.info("=" * 80)
