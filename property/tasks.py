import logging

from celery import shared_task
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger('property.tasks')


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


@shared_task(bind=True, max_retries=0)
def scrape_rightmove_properties(self, task_uuid, max_properties=100):
    """
    Celery task to scrape properties from Rightmove based on search criteria.

    Args:
        task_uuid: UUID of the PropertyListTask tracking this operation
        max_properties: Maximum number of properties to scrape

    Returns:
        Dict with results summary
    """
    from property.models import PropertyListTask, Property
    from property.services import RightmoveService
    from django.db import transaction
    from django.core.exceptions import ValidationError

    logger.debug("scrape_rightmove_properties started task_uuid=%s max_properties=%d", task_uuid, max_properties)

    try:
        # Get task and property list
        task = PropertyListTask.objects.get(uuid=task_uuid)
        property_list = task.property_list
        search_criteria = property_list.search_criteria

        if not search_criteria:
            logger.error("scrape_rightmove_properties task=%s property_list=%s has no search_criteria", task_uuid, property_list.uuid)
            raise ValueError("PropertyList does not have search criteria configured")

        # Update task status
        task.status = 'IN_PROGRESS'
        task.celery_task_id = self.request.id
        task.save(update_fields=['status', 'celery_task_id', 'updated_at'])
        logger.debug("scrape_rightmove_properties task=%s status=IN_PROGRESS", task_uuid)

        # Send initial websocket update
        _send_list_websocket_update(
            property_list.uuid,
            'scrape_progress',
            {
                'status': 'IN_PROGRESS',
                'completed_items': 0,
                'total_items': 0,
                'failed_items': 0,
                'progress_percentage': 0,
                'errors': [],
                'message': 'Starting property search...'
            }
        )

        # Convert search criteria to dict
        criteria_dict = {
            'area': search_criteria.area,
            'bedrooms_min': search_criteria.bedrooms_min,
            'bedrooms_max': search_criteria.bedrooms_max,
            'bathrooms_min': search_criteria.bathrooms_min,
            'bathrooms_max': search_criteria.bathrooms_max,
            'price_min': search_criteria.price_min,
            'price_max': search_criteria.price_max,
            'radius': search_criteria.radius,
            'property_types': search_criteria.property_types,
            'max_days_since_added': search_criteria.max_days_since_added,
        }

        # Initialize service and scrape
        service = RightmoveService()

        def progress_callback(created, total):
            """Callback for progress updates"""
            task.total_items = total
            task.completed_items = created
            task.save(update_fields=['total_items', 'completed_items', 'updated_at'])

            _send_list_websocket_update(
                property_list.uuid,
                'scrape_progress',
                {
                    'status': 'IN_PROGRESS',
                    'completed_items': created,
                    'total_items': total,
                    'failed_items': task.failed_items,
                    'progress_percentage': int((created / total) * 100) if total > 0 else 0,
                    'errors': task.errors,
                    'message': f'Scraped {created} of {total} properties...'
                }
            )

        # Scrape properties
        logger.debug("scrape_rightmove_properties task=%s calling scrape_properties_by_search", task_uuid)
        properties_data = service.scrape_properties_by_search(
            criteria_dict,
            max_properties=max_properties,
            progress_callback=progress_callback
        )
        logger.debug("scrape_rightmove_properties task=%s scrape returned %d properties", task_uuid, len(properties_data))

        # Create Property objects
        created_count = 0
        updated_count = 0
        skipped_count = 0

        for prop_data in properties_data:
            try:
                with transaction.atomic():
                    # Map service data to Property model fields
                    property_fields, images_data = _map_rightmove_to_property(prop_data)

                    # Check for existing property by external_id
                    external_id = property_fields.get('external_id')
                    property_obj = None

                    if external_id:
                        existing = Property.objects.filter(external_id=external_id).first()
                        if existing:
                            # Update existing property
                            for field, value in property_fields.items():
                                if field not in ['uuid', 'property_list', 'created_at']:
                                    setattr(existing, field, value)
                            existing.save()

                            # Add to property list if not already there
                            if existing.property_list != property_list:
                                # Property belongs to different list, skip
                                logger.debug("scrape_rightmove_properties task=%s skipped external_id=%s (belongs to different list)", task_uuid, external_id)
                                skipped_count += 1
                                continue

                            property_obj = existing
                            updated_count += 1
                            logger.debug("scrape_rightmove_properties task=%s updated external_id=%s", task_uuid, external_id)
                        else:
                            # Create new property
                            property_fields['property_list'] = property_list
                            property_obj = Property.objects.create(**property_fields)
                            created_count += 1
                            logger.debug("scrape_rightmove_properties task=%s created external_id=%s", task_uuid, external_id)
                    else:
                        # No external_id, create new
                        property_fields['property_list'] = property_list
                        property_obj = Property.objects.create(**property_fields)
                        created_count += 1
                        logger.debug("scrape_rightmove_properties task=%s created property (no external_id)", task_uuid)

                    # Create/update images
                    if property_obj and images_data:
                        from property.models import PropertyImage

                        # Clear existing images
                        property_obj.images.all().delete()

                        # Create new images
                        for idx, image_data in enumerate(images_data):
                            PropertyImage.objects.create(
                                property=property_obj,
                                source_url=image_data.get('source_url', image_data.get('srcUrl', '')),
                                url=image_data.get('url', ''),
                                caption=image_data.get('caption', ''),
                                order=idx
                            )

            except Exception as e:
                logger.error("scrape_rightmove_properties task=%s failed to create property: %s", task_uuid, e, exc_info=True)
                task.failed_items += 1
                # Convert non-JSON-serializable types for error logging
                from datetime import datetime, date
                serializable_data = {}
                for k, v in prop_data.items():
                    if isinstance(v, Decimal):
                        serializable_data[k] = str(v)
                    elif isinstance(v, (datetime, date)):
                        serializable_data[k] = v.isoformat()
                    elif isinstance(v, list):
                        serializable_data[k] = str(v)  # Lists might contain complex objects
                    else:
                        serializable_data[k] = v
                task.add_error(f"Failed to create property: {str(e)}", {'property_data': serializable_data})
                continue

        # Update task to completed
        logger.debug("scrape_rightmove_properties task=%s completed: created=%d updated=%d skipped=%d failed=%d", task_uuid, created_count, updated_count, skipped_count, task.failed_items)
        task.status = 'COMPLETED'
        task.completed_at = timezone.now()
        task.metadata['created_count'] = created_count
        task.metadata['updated_count'] = updated_count
        task.metadata['skipped_count'] = skipped_count
        task.save(update_fields=['status', 'completed_at', 'metadata', 'updated_at'])

        # Send completion websocket update
        _send_list_websocket_update(
            property_list.uuid,
            'scrape_complete',
            {
                'status': 'COMPLETED',
                'completed_items': created_count,
                'total_items': len(properties_data),
                'failed_items': task.failed_items,
                'progress_percentage': 100,
                'errors': task.errors,
                'metadata': {
                    'created': created_count,
                    'updated': updated_count,
                    'skipped': skipped_count,
                },
                'message': f'Scrape completed: {created_count} created, {updated_count} updated'
            }
        )

        return {
            'status': 'completed',
            'created': created_count,
            'updated': updated_count,
            'skipped': skipped_count,
            'failed': task.failed_items,
            'total': len(properties_data)
        }

    except (PropertyListTask.DoesNotExist, ValidationError):
        logger.error("scrape_rightmove_properties task=%s not found or invalid", task_uuid)
        return {'status': 'failed', 'error': f'Task {task_uuid} not found'}
    except Exception as e:
        logger.error("scrape_rightmove_properties task=%s failed: %s", task_uuid, e, exc_info=True)
        # Update task to failed
        try:
            task.status = 'FAILED'
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])

            # Send failure websocket update
            _send_list_websocket_update(
                property_list.uuid,
                'scrape_failed',
                {
                    'status': 'FAILED',
                    'completed_items': 0,
                    'total_items': 0,
                    'failed_items': 0,
                    'progress_percentage': 0,
                    'errors': [str(e)],
                    'message': f'Scrape failed: {str(e)}'
                }
            )
        except:
            pass

        raise


def _map_rightmove_to_property(prop_data):
    """
    Map Rightmove property data to Property model fields.

    Args:
        prop_data: Dict from RightmoveService

    Returns:
        Tuple of (property_fields dict, images_data list)
    """
    # Extract images
    images_data = prop_data.pop('images', [])

    # Map fields
    mapped = {
        'external_id': prop_data.get('external_id', ''),
        'external_url': prop_data.get('link', ''),
        'title': prop_data.get('title', prop_data.get('address', 'Untitled')),
        'address_line_1': prop_data.get('address', ''),
        'address_line_2': '',
        'city': '',
        'postcode': '',  # Will need to extract from address
        'latitude': prop_data.get('latitude'),
        'longitude': prop_data.get('longitude'),
        'price': prop_data.get('price', Decimal('0')),
        'bedrooms': prop_data.get('bedrooms', 0),
        'bathrooms': prop_data.get('bathrooms', 0),
        'garden': False,  # Not in current data
        'parking': False,  # Not in current data
        'furnished_status': '',
        'square_area': None,
    }

    # Try to extract postcode from address
    if prop_data.get('address'):
        import re
        postcode_match = re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}', prop_data['address'])
        if postcode_match:
            mapped['postcode'] = postcode_match.group(0)

    # If still no postcode, use placeholder
    if not mapped['postcode']:
        mapped['postcode'] = 'UNKNOWN'

    return mapped, images_data


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


def _send_list_websocket_update(property_list_uuid, message_type, data):
    """
    Helper function to send WebSocket updates for property list operations.

    Args:
        property_list_uuid: The property list UUID
        message_type: Type of message (scrape_progress, scrape_complete, etc)
        data: Message data dictionary
    """
    channel_layer = get_channel_layer()
    room_group_name = f'property_list_{property_list_uuid}'

    async_to_sync(channel_layer.group_send)(
        room_group_name,
        {
            'type': message_type.replace('_', '.'),  # Convert to dotted notation for consumer
            'data': data
        }
    )
