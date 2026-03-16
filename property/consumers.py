from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from property.models import Property, PropertyList


class PropertyUpdateConsumer(AsyncJsonWebsocketConsumer):
    """
    WebSocket consumer for real-time property and property list updates.

    Handles:
    - Property state transitions (Stage1 -> Stage2 -> Stage3)
    - Context data retrieval progress
    - Rating calculation updates
    - Service completion notifications
    """

    async def connect(self):
        """Accept WebSocket connection and join appropriate room."""
        self.property_uuid = self.scope['url_route']['kwargs'].get('property_id')
        self.list_uuid = self.scope['url_route']['kwargs'].get('list_id')

        # Determine room name based on what we're tracking
        if self.property_uuid:
            self.room_group_name = f'property_{self.property_uuid}'
        elif self.list_uuid:
            self.room_group_name = f'property_list_{self.list_uuid}'
        else:
            await self.close()
            return

        # Join room group
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

    async def disconnect(self, close_code):
        """Leave room group on disconnect."""
        if hasattr(self, 'room_group_name'):
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )

    # Receive message from WebSocket (from client)
    async def receive_json(self, content):
        """Handle messages from client (if needed)."""
        message_type = content.get('type', '')

        if message_type == 'ping':
            await self.send_json({'type': 'pong'})

    # Receive message from room group
    async def property_update(self, event):
        """Send property update to WebSocket."""
        await self.send_json({
            'type': 'property_update',
            'data': event['data']
        })

    async def stage_transition(self, event):
        """Send state transition notification to WebSocket."""
        await self.send_json({
            'type': 'stage_transition',
            'data': event['data']
        })

    async def service_complete(self, event):
        """Send service completion notification to WebSocket."""
        await self.send_json({
            'type': 'service_complete',
            'data': event['data']
        })

    async def rating_update(self, event):
        """Send rating calculation update to WebSocket."""
        await self.send_json({
            'type': 'rating_update',
            'data': event['data']
        })

    async def progress_update(self, event):
        """Send progress update (e.g., 3/5 services complete)."""
        await self.send_json({
            'type': 'progress_update',
            'data': event['data']
        })

    # Property list scrape handlers
    async def scrape_progress(self, event):
        """Send scrape progress update to WebSocket."""
        await self.send_json({
            'type': 'scrape_progress',
            'data': event['data']
        })

    async def scrape_complete(self, event):
        """Send scrape completion notification to WebSocket."""
        await self.send_json({
            'type': 'scrape_complete',
            'data': event['data']
        })

    async def scrape_failed(self, event):
        """Send scrape failure notification to WebSocket."""
        await self.send_json({
            'type': 'scrape_failed',
            'data': event['data']
        })
