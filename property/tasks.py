from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


@shared_task(bind=True, max_retries=3)
def retrieve_context_data(self, property_id):
    """
    Celery task to retrieve context data for a property.

    This orchestrates all context service calls for Stage 2.
    Calls services based on the property's context options configuration.
    Sends WebSocket updates for progress and completion.
    """
    from property.models import Property

    try:
        property_obj = Property.objects.get(id=property_id)

        # Send initial progress update
        _send_websocket_update(
            property_id,
            'progress_update',
            {'message': 'Starting context data retrieval', 'progress': 0}
        )

        # TODO: Implement service orchestration in Phase 4
        # For now, just acknowledge task started

        return f'Context retrieval started for property {property_id}'

    except Property.DoesNotExist:
        raise ValueError(f'Property {property_id} does not exist')
    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3)
def calculate_property_rating(self, property_id):
    """
    Celery task to calculate property rating.

    This implements Stage 3 rating calculation.
    Evaluates all rating criteria and aggregates scores.
    Sends WebSocket updates when complete.
    """
    from property.models import Property

    try:
        property_obj = Property.objects.get(id=property_id)

        # Send initial progress update
        _send_websocket_update(
            property_id,
            'progress_update',
            {'message': 'Starting rating calculation', 'progress': 0}
        )

        # TODO: Implement rating calculation in Phase 5
        # For now, just acknowledge task started

        return f'Rating calculation started for property {property_id}'

    except Property.DoesNotExist:
        raise ValueError(f'Property {property_id} does not exist')
    except Exception as exc:
        # Retry on failure
        raise self.retry(exc=exc, countdown=60)


@shared_task
def bulk_retrieve_context_data(property_ids):
    """
    Bulk task to retrieve context data for multiple properties.
    Queues individual tasks for each property.
    """
    for property_id in property_ids:
        retrieve_context_data.delay(property_id)

    return f'Queued context retrieval for {len(property_ids)} properties'


@shared_task
def bulk_calculate_ratings(property_ids):
    """
    Bulk task to calculate ratings for multiple properties.
    Queues individual tasks for each property.
    """
    for property_id in property_ids:
        calculate_property_rating.delay(property_id)

    return f'Queued rating calculation for {len(property_ids)} properties'


def _send_websocket_update(property_id, message_type, data):
    """
    Helper function to send WebSocket updates to connected clients.

    Args:
        property_id: The property ID
        message_type: Type of message (progress_update, service_complete, etc)
        data: Message data dictionary
    """
    channel_layer = get_channel_layer()
    room_group_name = f'property_{property_id}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': message_type,
            'data': data
        }
    )
