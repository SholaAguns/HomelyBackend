from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.db import database_sync_to_async
from property.models.stage1_models import Property, PropertyList
import logging

logger = logging.getLogger('property.consumers')


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
        logger.info("=" * 80)
        logger.info("WEBSOCKET CONNECTION ATTEMPT")
        logger.info(f"SCOPE PATH: {self.scope.get('path', 'NO PATH')}")
        logger.info(f"SCOPE URL_ROUTE: {self.scope.get('url_route', {})}")

        self.property_uuid = self.scope['url_route']['kwargs'].get('property_id')
        self.list_uuid = self.scope['url_route']['kwargs'].get('list_id')

        logger.info(f"PROPERTY_UUID: {self.property_uuid}")
        logger.info(f"LIST_UUID: {self.list_uuid}")

        # Determine room name based on what we're tracking
        if self.property_uuid:
            self.room_group_name = f'property_{self.property_uuid}'
            logger.info(f"ROOM NAME (PROPERTY): {self.room_group_name}")
        elif self.list_uuid:
            self.room_group_name = f'property_list_{self.list_uuid}'
            logger.info(f"ROOM NAME (LIST): {self.room_group_name}")
        else:
            logger.warning("NO PROPERTY_UUID OR LIST_UUID - CLOSING CONNECTION")
            await self.close()
            return

        # Join room group
        logger.info(f"JOINING ROOM GROUP: {self.room_group_name}")
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        logger.info("ACCEPTING WEBSOCKET CONNECTION")
        await self.accept()
        logger.info("WEBSOCKET CONNECTION ACCEPTED SUCCESSFULLY")
        logger.info("=" * 80)

    async def disconnect(self, close_code):
        """Leave room group on disconnect."""
        logger.info("=" * 80)
        logger.info(f"WEBSOCKET DISCONNECT - CLOSE_CODE: {close_code}")
        if hasattr(self, 'room_group_name'):
            logger.info(f"LEAVING ROOM GROUP: {self.room_group_name}")
            await self.channel_layer.group_discard(
                self.room_group_name,
                self.channel_name
            )
            logger.info("LEFT ROOM GROUP SUCCESSFULLY")
        else:
            logger.warning("NO ROOM_GROUP_NAME FOUND ON DISCONNECT")
        logger.info("=" * 80)

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
        logger.info(f"FORWARDING PROGRESS UPDATE TO CLIENT")
        await self.send_json({
            'type': 'progress_update',
            'data': event['data']
        })

    async def service_update(self, event):
        """Send service update (individual service completion/failure)."""
        logger.info(f"FORWARDING SERVICE UPDATE TO CLIENT: {event.get('data', {}).get('service', 'unknown')}")
        await self.send_json({
            'type': 'service_update',
            'data': event['data']
        })

    async def stage2_complete(self, event):
        """Send stage 2 completion notification."""
        logger.info(f"FORWARDING STAGE2 COMPLETE TO CLIENT")
        await self.send_json({
            'type': 'stage2_complete',
            'data': event['data']
        })

    async def rating_complete(self, event):
        """Send rating completion notification."""
        logger.info(f"FORWARDING RATING COMPLETE TO CLIENT")
        await self.send_json({
            'type': 'rating_complete',
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
