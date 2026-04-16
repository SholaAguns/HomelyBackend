from django.urls import path
from property.consumers import PropertyUpdateConsumer, NotificationConsumer
import logging

logger = logging.getLogger('homely_core.routing')

logger.info("=" * 80)
logger.info("WEBSOCKET ROUTING SETUP")
logger.info("REGISTERING WEBSOCKET URL PATTERNS:")
logger.info("  - ws/property/<uuid:property_id>/")
logger.info("  - ws/property-list/<uuid:list_id>/")
logger.info("  - ws/notifications/")
logger.info("=" * 80)

websocket_urlpatterns = [
    path('ws/property/<uuid:property_id>/', PropertyUpdateConsumer.as_asgi()),
    path('ws/property-list/<uuid:list_id>/', PropertyUpdateConsumer.as_asgi()),
    path('ws/notifications/', NotificationConsumer.as_asgi()),
]
