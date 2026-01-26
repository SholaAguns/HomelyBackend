from django.urls import path
from property.consumers import PropertyUpdateConsumer

websocket_urlpatterns = [
    path('ws/property/<int:property_id>/', PropertyUpdateConsumer.as_asgi()),
    path('ws/property-list/<uuid:list_id>/', PropertyUpdateConsumer.as_asgi()),
]
