from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from property.models.stage1_models import Property, PropertyList
import logging

logger = logging.getLogger('property.consumers')



class NotificationConsumer(AsyncJsonWebsocketConsumer):
    """WebSocket consumer for real-time in-app notifications."""

    async def connect(self):
        user = self.scope.get('user')
        if not user or not user.is_authenticated:
            await self.close()
            return
        self.group_name = f'notifications_{user.id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def receive_json(self, content):
        if content.get('type') == 'ping':
            await self.send_json({'type': 'pong'})

    async def notify(self, event):
        """Forward notification payload to the client."""
        await self.send_json({'type': 'notification', 'payload': event['payload']})
