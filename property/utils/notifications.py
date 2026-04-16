import uuid as uuid_lib
from django.contrib.auth.models import User


def create_notification(recipient: User, actor, notification_type: str, title: str, message: str,
                        related_object_uuid=None, related_object_type: str = ''):
    from property.models import AppNotification
    notification = AppNotification.objects.create(
        recipient=recipient,
        actor=actor,
        notification_type=notification_type,
        title=title,
        message=message,
        related_object_uuid=related_object_uuid,
        related_object_type=related_object_type,
    )
    _send_ws_notification(recipient.id, {
        'uuid': str(notification.uuid),
        'notification_type': notification.notification_type,
        'title': notification.title,
        'message': notification.message,
        'related_object_uuid': str(related_object_uuid) if related_object_uuid else None,
        'related_object_type': related_object_type,
        'is_read': False,
        'created_at': notification.created_at.isoformat(),
    })
    return notification


def _send_ws_notification(user_id: int, payload: dict):
    try:
        from channels.layers import get_channel_layer
        from asgiref.sync import async_to_sync
        channel_layer = get_channel_layer()
        if channel_layer is None:
            return
        async_to_sync(channel_layer.group_send)(
            f'notifications_{user_id}',
            {'type': 'notify', 'payload': payload},
        )
    except Exception:
        pass
