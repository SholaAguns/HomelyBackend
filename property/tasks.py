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
    Orchestrates Stage 2 context data retrieval.

    Creates ContextData records for enabled services and launches
    individual service tasks. Property must be in 'New' or 'Stage2Complete' state.
    """
    from property.models import Property, ContextData

    try:
        property_obj = Property.objects.select_related('property_list__context_options').get(id=property_id)

        # Check if context options configured
        if not hasattr(property_obj.property_list, 'context_options'):
            raise ValueError('Context options not configured for this property list')

        context_options = property_obj.property_list.context_options
        enabled_services = context_options.get_enabled_services()

        if not enabled_services:
            raise ValueError('No context services enabled')

        # Transition to Stage2InProgress (FSM transition)
        property_obj.run_stage2()
        property_obj.save()

        # Create ContextData records for each service
        for service_name in enabled_services:
            ContextData.objects.get_or_create(
                property=property_obj,
                service_name=service_name,
                defaults={'status': 'PENDING'}
            )

        # Launch individual service tasks
        for service_name in enabled_services:
            run_service_task.delay(property_id, service_name)

        logger.info(f'Launched {len(enabled_services)} service tasks for property {property_id}')

        return f'Context retrieval started for property {property_id}: {len(enabled_services)} services'

    except Property.DoesNotExist:
        raise ValueError(f'Property {property_id} does not exist')
    except Exception as exc:
        logger.error(f'Failed to start context retrieval for property {property_id}: {exc}')
        raise self.retry(exc=exc, countdown=60)


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def run_service_task(self, property_id, service_name):
    """
    Execute individual context service with caching and retry logic.

    Workflow:
    1. Check Redis cache
    2. If miss, call service API
    3. Update ContextData record
    4. Cache result with service-specific TTL
    5. Send WebSocket update
    6. Check if all services complete → trigger complete_stage2()

    Implements automatic retry with exponential backoff for transient errors.
    """
    from property.models import Property, ContextData
    from property.services.context_retrieval import context_service_factory
    from django.core.cache import cache
    from django.utils import timezone
    import requests

    try:
        property_obj = Property.objects.get(id=property_id)
        context_data = ContextData.objects.get(property=property_obj, service_name=service_name)

        # Update status to IN_PROGRESS
        context_data.status = 'IN_PROGRESS'
        context_data.last_attempt_at = timezone.now()
        context_data.retry_count = self.request.retries
        context_data.save()

        # Get service instance
        service = context_service_factory(service_name)

        # Prepare service-specific parameters
        service_params = _get_service_params(property_obj, service_name)

        # Check cache first
        cache_key = service.get_cache_key(property_obj)
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.info(f'Cache hit for {service_name} - {cache_key}')
            data = cached_data
        else:
            logger.info(f'Cache miss for {service_name} - {cache_key}, fetching from API')
            # Fetch from external API
            data = service.fetch_data(property_obj, **service_params)

            # Cache with service-specific TTL
            cache.set(cache_key, data, service.get_cache_ttl())

        # Update ContextData with result
        context_data.data = data
        context_data.status = 'COMPLETE'
        context_data.completed_at = timezone.now()
        context_data.error_message = ''
        context_data.error_type = ''
        context_data.save()

        logger.info(f'Service {service_name} completed for property {property_id}')

        # Send WebSocket update
        _send_service_update(property_obj, service_name, 'COMPLETE', data)

        # Check if all services complete
        _check_stage2_completion(property_obj)

        return f'Service {service_name} completed for property {property_id}'

    except (Property.DoesNotExist, ContextData.DoesNotExist) as e:
        logger.error(f'Property or ContextData not found: {e}')
        raise

    except Exception as exc:
        logger.error(f'Service {service_name} failed for property {property_id}: {exc}')

        # Classify error to determine if retry
        error_info = _classify_error(exc)

        # Update ContextData with error
        try:
            context_data.last_attempt_at = timezone.now()
            context_data.retry_count = self.request.retries
            context_data.error_message = str(exc)
            context_data.error_type = error_info['error_type']
            context_data.save()
        except:
            pass

        # Retry if transient error and retries remaining
        if error_info['should_retry'] and self.request.retries < self.max_retries:
            retry_count = self.request.retries
            countdown = 60 * (2 ** retry_count)  # Exponential backoff: 60s, 120s, 240s
            logger.info(f'Retrying {service_name} in {countdown}s (attempt {retry_count + 1})')
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # Mark as failed
            try:
                context_data.status = 'FAILED'
                context_data.save()

                # Send WebSocket update
                _send_service_update(property_obj, service_name, 'FAILED', None, str(exc))

                # Check if all services complete (even with failures)
                _check_stage2_completion(property_obj)

            except:
                pass

            return f'Service {service_name} failed permanently for property {property_id}'


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
            logger.debug("making progess callback created=%s, total=%s", created, total)

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

        # Create Property objects using service batch method
        def batch_progress_callback(created, updated, failed):
            """Callback for batch creation progress"""
            task.failed_items = failed
            task.save(update_fields=['failed_items', 'updated_at'])

        result = service.batch_create_properties(
            properties_data,
            property_list,
            progress_callback=batch_progress_callback
        )

        created_count = result['created']
        updated_count = result['updated']
        skipped_count = 0

        # Add errors to task
        for error in result['errors']:
            task.add_error(f"Failed to create property: {error['error']}", error)

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


def _classify_error(exc) -> dict:
    """
    Classify exception to determine retry strategy.

    Error types:
    - network: Transient network errors (retry)
    - rate_limit: API rate limit (retry with backoff)
    - auth: Authentication errors (permanent, no retry)
    - data: Invalid property data (permanent, no retry)
    - not_found: Resource not found (permanent, no retry)
    - server: Server errors 500+ (retry)

    Returns:
        Dict with 'should_retry' bool and 'error_type' string
    """
    import requests

    # Network/timeout errors - transient, retry
    if isinstance(exc, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return {'should_retry': True, 'error_type': 'network'}

    # HTTP errors
    if isinstance(exc, requests.exceptions.HTTPError):
        status_code = exc.response.status_code if exc.response else 0

        if status_code == 429:
            # Rate limit - retry with backoff
            return {'should_retry': True, 'error_type': 'rate_limit'}
        elif status_code in [401, 403]:
            # Auth errors - permanent
            return {'should_retry': False, 'error_type': 'auth'}
        elif status_code == 404:
            # Not found - permanent
            return {'should_retry': False, 'error_type': 'not_found'}
        elif status_code >= 500:
            # Server errors - transient, retry
            return {'should_retry': True, 'error_type': 'server'}

    # Validation errors - permanent
    if isinstance(exc, ValueError):
        return {'should_retry': False, 'error_type': 'data'}

    # Unknown errors - don't retry
    return {'should_retry': False, 'error_type': 'unknown'}


def _send_service_update(property_obj, service_name, status, data=None, error=None):
    """
    Send WebSocket update for service completion/failure.

    Args:
        property_obj: Property instance
        service_name: Name of the service
        status: 'COMPLETE' or 'FAILED'
        data: Service data (if complete)
        error: Error message (if failed)
    """
    from property.models import ContextData

    # Calculate progress
    all_context_data = ContextData.objects.filter(property=property_obj)
    total = all_context_data.count()
    complete = all_context_data.filter(status='COMPLETE').count()
    failed = all_context_data.filter(status='FAILED').count()
    in_progress = all_context_data.filter(status__in=['PENDING', 'IN_PROGRESS']).count()

    message_data = {
        'property_id': property_obj.id,
        'property_state': property_obj.state,
        'service': service_name,
        'status': status,
        'data': data,
        'error': error,
        'progress': {
            'total': total,
            'complete': complete,
            'failed': failed,
            'in_progress': in_progress
        }
    }

    _send_websocket_update(property_obj.id, 'service_update', message_data)


def _get_service_params(property_obj, service_name):
    """
    Get service-specific parameters for fetch_data call.

    For POI service: Compiles poi_types from all property lists
    For other services: Returns empty dict

    Args:
        property_obj: Property instance
        service_name: Name of the service

    Returns:
        Dict of parameters to pass to service.fetch_data()
    """
    if service_name == 'poi':
        # Compile POI types from all property lists
        poi_types_set = set()
        radius = 1600  # Default

        for property_list in property_obj.property_lists.all():
            context_options = getattr(property_list, 'context_options', None)
            if context_options and context_options.enable_poi:
                # Add poi_types from this list
                if context_options.poi_types:
                    poi_types_set.update(context_options.poi_types)
                # Use the largest radius from all lists
                if context_options.poi_search_radius_meters:
                    radius = max(radius, context_options.poi_search_radius_meters)

        return {
            'poi_types': list(poi_types_set),
            'radius': radius
        }

    # No special params for other services
    return {}


def _check_stage2_completion(property_obj):
    """
    Check if all context services are complete/failed.
    If yes, transition property to Stage2Complete.

    Args:
        property_obj: Property instance
    """
    from property.models import ContextData

    all_context_data = ContextData.objects.filter(property=property_obj)
    incomplete = all_context_data.exclude(status__in=['COMPLETE', 'FAILED']).count()

    if incomplete == 0:
        # All services finished (either complete or failed)
        logger.info(f'All services finished for property {property_obj.id}, transitioning to Stage2Complete')

        # Transition to Stage2Complete
        property_obj.complete_stage2()
        property_obj.save()

        # Send completion WebSocket update
        _send_websocket_update(
            property_obj.id,
            'stage2_complete',
            {
                'property_id': property_obj.id,
                'property_state': property_obj.state,
                'message': 'Context data retrieval complete'
            }
        )
