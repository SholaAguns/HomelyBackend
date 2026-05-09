from unittest.mock import patch

from django.test import TestCase, AsyncClient
from django.contrib.auth.models import User
from rest_framework_simplejwt.tokens import RefreshToken

from property.models import Project, PropertyList


class PropertyStreamViewTest(TestCase):
    """Test property_stream SSE view authentication"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='user', email='user@test.com', password='testpass123'
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.async_client = AsyncClient()

    async def test_stream_returns_401_without_token(self):
        """GET /properties/<uuid>/stream/ returns 401 when no token provided"""
        response = await self.async_client.get(
            '/api/property/properties/00000000-0000-0000-0000-000000000001/stream/'
        )
        self.assertEqual(response.status_code, 401)

    async def test_stream_returns_401_with_invalid_token(self):
        """GET /properties/<uuid>/stream/ returns 401 for invalid JWT token"""
        response = await self.async_client.get(
            '/api/property/properties/00000000-0000-0000-0000-000000000001/stream/?token=badtoken'
        )
        self.assertEqual(response.status_code, 401)

    @patch('property.sse_views._event_stream')
    async def test_stream_returns_streaming_response_for_authenticated_user(self, mock_event_stream):
        """GET /properties/<uuid>/stream/ returns SSE streaming response for valid token"""
        async def _mock_gen():
            yield 'data: {"type": "connected"}\n\n'

        mock_event_stream.return_value = _mock_gen()

        response = await self.async_client.get(
            f'/api/property/properties/00000000-0000-0000-0000-000000000001/stream/?token={self.token}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get('Content-Type'), 'text/event-stream')

    @patch('property.sse_views._event_stream')
    async def test_stream_uses_correct_redis_channel_for_property(self, mock_event_stream):
        """GET /properties/<uuid>/stream/ subscribes to sse:property:<uuid> channel"""
        async def _mock_gen():
            yield 'data: {"type": "connected"}\n\n'

        mock_event_stream.return_value = _mock_gen()
        property_uuid = '00000000-0000-0000-0000-000000000001'

        await self.async_client.get(
            f'/api/property/properties/{property_uuid}/stream/?token={self.token}'
        )

        mock_event_stream.assert_called_once_with(f'sse:property:{property_uuid}')


class PropertyListStreamViewTest(TestCase):
    """Test property_list_stream SSE view authentication"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='user', email='user@test.com', password='testpass123'
        )
        self.token = str(RefreshToken.for_user(self.user).access_token)
        self.async_client = AsyncClient()

    async def test_stream_returns_401_without_token(self):
        """GET /property-lists/<uuid>/stream/ returns 401 when no token provided"""
        response = await self.async_client.get(
            '/api/property/property-lists/00000000-0000-0000-0000-000000000001/stream/'
        )
        self.assertEqual(response.status_code, 401)

    async def test_stream_returns_401_with_invalid_token(self):
        """GET /property-lists/<uuid>/stream/ returns 401 for invalid JWT token"""
        response = await self.async_client.get(
            '/api/property/property-lists/00000000-0000-0000-0000-000000000001/stream/?token=badtoken'
        )
        self.assertEqual(response.status_code, 401)

    @patch('property.sse_views._event_stream')
    async def test_stream_returns_streaming_response_for_authenticated_user(self, mock_event_stream):
        """GET /property-lists/<uuid>/stream/ returns SSE streaming response for valid token"""
        async def _mock_gen():
            yield 'data: {"type": "connected"}\n\n'

        mock_event_stream.return_value = _mock_gen()

        response = await self.async_client.get(
            f'/api/property/property-lists/00000000-0000-0000-0000-000000000001/stream/?token={self.token}'
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get('Content-Type'), 'text/event-stream')

    @patch('property.sse_views._event_stream')
    async def test_stream_uses_correct_redis_channel_for_list(self, mock_event_stream):
        """GET /property-lists/<uuid>/stream/ subscribes to sse:property-list:<uuid> channel"""
        async def _mock_gen():
            yield 'data: {"type": "connected"}\n\n'

        mock_event_stream.return_value = _mock_gen()
        list_uuid = '00000000-0000-0000-0000-000000000001'

        await self.async_client.get(
            f'/api/property/property-lists/{list_uuid}/stream/?token={self.token}'
        )

        mock_event_stream.assert_called_once_with(f'sse:property-list:{list_uuid}')
