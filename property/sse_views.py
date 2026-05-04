import asyncio
import json
import logging

from asgiref.sync import sync_to_async
from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse

import redis.asyncio as aioredis

logger = logging.getLogger('property.sse')

RETRY_MS = 5000


def _unauthorized():
    return HttpResponse('Unauthorized', status=401)


@sync_to_async
def _resolve_user(token_str: str):
    from django.contrib.auth import get_user_model
    from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
    from rest_framework_simplejwt.tokens import AccessToken

    User = get_user_model()
    try:
        token = AccessToken(token_str)
        return User.objects.get(id=token['user_id'])
    except (InvalidToken, TokenError, User.DoesNotExist):
        return None


async def _event_stream(redis_channel: str):
    client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(redis_channel)

    try:
        yield f'retry: {RETRY_MS}\n'
        yield 'data: {"type": "connected"}\n\n'

        async for message in pubsub.listen():
            if message['type'] == 'message':
                yield f"data: {message['data']}\n\n"

    except (asyncio.CancelledError, GeneratorExit):
        pass
    finally:
        try:
            await pubsub.unsubscribe(redis_channel)
            await client.aclose()
        except Exception:
            pass


def _sse_response(generator):
    response = StreamingHttpResponse(generator, content_type='text/event-stream')
    response['Cache-Control'] = 'no-cache'
    response['X-Accel-Buffering'] = 'no'
    return response


async def property_stream(request, property_uuid):
    """
    GET /api/property/properties/<uuid>/stream/?token=<jwt>
    Streams: service_update, stage2_complete, rating_complete, rating_failed
    """
    token_str = request.GET.get('token')
    if not token_str:
        return _unauthorized()

    user = await _resolve_user(token_str)
    if not user:
        return _unauthorized()

    return _sse_response(_event_stream(f'sse:property:{property_uuid}'))


async def property_list_stream(request, list_uuid):
    """
    GET /api/property/property-lists/<uuid>/stream/?token=<jwt>
    Streams: service_update, stage2_complete, rating_complete,
             scrape_progress, scrape_complete, scrape_failed
    """
    token_str = request.GET.get('token')
    if not token_str:
        return _unauthorized()

    user = await _resolve_user(token_str)
    if not user:
        return _unauthorized()

    return _sse_response(_event_stream(f'sse:property-list:{list_uuid}'))


@sync_to_async
def _user_can_access_project(user, project_uuid_str: str) -> bool:
    from django.db.models import Q
    from property.models import Project
    return Project.objects.filter(uuid=project_uuid_str).filter(
        Q(owner=user) | Q(viewers=user) | Q(contributors=user)
    ).exists()


async def project_comment_stream(request, project_uuid):
    """
    GET /api/property/projects/<uuid>/comments/stream/?token=<jwt>
    Streams: comment_created, comment_deleted
    """
    token_str = request.GET.get('token')
    if not token_str:
        return _unauthorized()

    user = await _resolve_user(token_str)
    if not user:
        return _unauthorized()

    has_access = await _user_can_access_project(user, str(project_uuid))
    if not has_access:
        return _unauthorized()

    return _sse_response(_event_stream(f'sse:project:{project_uuid}:comments'))
