import json as _json
import logging

from celery import shared_task
from django.conf import settings
from django.utils import timezone
from decimal import Decimal

logger = logging.getLogger('property.tasks')


@shared_task(bind=True, max_retries=3)
def retrieve_context_data(self, property_id, property_list_id=None, services=None):
    from property.models import Property, ContextData, PropertyList

    try:
        property_obj = Property.objects.prefetch_related(
            'property_lists__project__context_options'
        ).get(id=property_id)

        # Determine which services to run
        if services:
            # Use provided services list
            enabled_services = services
        elif property_list_id:
            # Running from specific list - use project's context options
            try:
                property_list = PropertyList.objects.select_related('project__context_options').get(id=property_list_id)
                project = property_list.project
                if not hasattr(project, 'context_options'):
                    raise ValueError(f'Context options not configured for project {project.title}')
                enabled_services = project.context_options.get_enabled_services()
            except PropertyList.DoesNotExist:
                raise ValueError(f'Property list {property_list_id} not found')
        else:
            # Running from individual property - get from any list's project
            enabled_services = _get_enabled_services_from_project(property_obj)

        if not enabled_services:
            raise ValueError('No context services enabled')

        # Verify property is in correct state (FSM transition handled by caller - view or signal)
        if property_obj.state not in ['STAGE2_IN_PROGRESS', 'NEW', 'STAGE2_COMPLETE', 'STAGE3_IN_PROGRESS', 'STAGE3_COMPLETE']:
            raise ValueError(f'Cannot run context retrieval from state {property_obj.state}')

        if property_obj.state == 'NEW':
            property_obj.run_stage2()
            property_obj.save()
        elif property_obj.state in ['STAGE2_COMPLETE', 'STAGE3_IN_PROGRESS', 'STAGE3_COMPLETE']:
            property_obj.rerun_services()
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

            # Only cache successful responses (no error field or error is None/empty)
            if not data.get('error'):
                cache.set(cache_key, data, service.get_cache_ttl())
                logger.info(f'Cached successful response for {service_name} - {cache_key}')
            else:
                logger.info(f'Not caching error response for {service_name}: {data.get("error")}')

        # Update ContextData with result
        context_data.data = data
        context_data.status = 'COMPLETE'
        context_data.completed_at = timezone.now()
        context_data.error_message = ''
        context_data.error_type = ''
        context_data.save()

        logger.info(f'Service {service_name} completed for property {property_id}')

        # Send WebSocket update
        logger.info(f'SENDING UPDATE FOR Service: {service_name} ')
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
        except Exception:
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

            except Exception:
                pass

            return f'Service {service_name} failed permanently for property {property_id}'


@shared_task(bind=True, max_retries=3)
def calculate_property_rating(self, property_id):
    """
    Celery task to calculate property rating (Stage 3).

    Workflow:
    1. Verify property is in valid state
    2. Call rating service to calculate scores
    3. Persist results to database
    4. Send WebSocket update
    5. Transition to Stage3Complete

    Implements automatic retry with exponential backoff for transient errors.
    """
    from property.models import Property
    from property.services.rating_service import calculate_and_persist_rating

    try:
        property_obj = Property.objects.get(id=property_id)

        # Verify property is in correct state
        if property_obj.state not in ['STAGE3_IN_PROGRESS']:
            raise ValueError(f'Cannot calculate rating from state {property_obj.state}')

        logger.info(f'Starting rating calculation for property {property_id}')

        # Send initial progress update
        _send_property_event(
            property_obj.uuid,
            'rating_progress',
            {'message': 'Calculating rating...', 'progress': 50}
        )

        # Calculate and persist rating
        result = calculate_and_persist_rating(property_id)

        logger.info(f'Rating calculation complete for property {property_id}: {result["overall_rating"]}')

        # Refresh property object to get updated rating fields
        property_obj.refresh_from_db()

        # Transition to Stage3Complete
        property_obj.complete_stage3()
        property_obj.save()

        # Send completion update
        _send_rating_complete(property_obj, result)

        return f'Rating calculation complete for property {property_id}: {result["overall_rating"]}'

    except Property.DoesNotExist:
        logger.error(f'Property {property_id} does not exist')
        raise
    except ValueError as e:
        # Configuration errors - don't retry
        logger.error(f'Rating calculation failed for property {property_id}: {e}')
        # Mark property state appropriately
        try:
            property_obj = Property.objects.get(id=property_id)
            _send_rating_failed(property_obj, str(e))
        except Exception:
            pass
        raise
    except Exception as exc:
        logger.error(f'Rating calculation failed for property {property_id}: {exc}')
        # Retry on unexpected errors
        if self.request.retries < self.max_retries:
            countdown = 60 * (2 ** self.request.retries)  # Exponential backoff
            logger.info(f'Retrying rating calculation in {countdown}s (attempt {self.request.retries + 1})')
            raise self.retry(exc=exc, countdown=countdown)
        else:
            # Max retries exceeded
            try:
                property_obj = Property.objects.get(id=property_id)
                _send_rating_failed(property_obj, str(exc))
            except Exception:
                pass
            raise


@shared_task
def bulk_retrieve_context_data(property_ids, property_list_id=None):
    """
    Bulk task to retrieve context data for multiple properties.
    Queues individual tasks for each property.

    Args:
        property_ids: List of property IDs
        property_list_id: Optional PropertyList ID (when running from specific list)
    """
    for property_id in property_ids:
        retrieve_context_data.delay(property_id, property_list_id)

    return f'Queued context retrieval for {len(property_ids)} properties'


@shared_task
def bulk_calculate_ratings(property_ids, project_id=None):
    """
    Bulk task to calculate ratings for multiple properties.
    Queues individual tasks for each property.

    Args:
        property_ids: List of property IDs to rate
        project_id: Optional project ID (for project-level bulk operations)
    """
    from property.models import Property

    # Filter to only properties in valid states
    valid_properties = Property.objects.filter(
        id__in=property_ids,
        state__in=['STAGE2_COMPLETE', 'STAGE3_COMPLETE']
    )

    queued_count = 0
    for property_obj in valid_properties:
        # Transition to Stage3InProgress
        try:
            property_obj.run_stage3()
            property_obj.save()
            calculate_property_rating.delay(property_obj.id)
            queued_count += 1
        except Exception as e:
            logger.error(f'Failed to queue rating for property {property_obj.id}: {e}')
            continue

    logger.info(f'Queued rating calculation for {queued_count}/{len(property_ids)} properties')
    return f'Queued rating calculation for {queued_count} properties'


@shared_task
def bulk_calculate_project_ratings(project_id):
    """
    Calculate ratings for all properties in a project.

    Args:
        project_id: Project ID
    """
    from property.models import Project, Property

    try:
        project = Project.objects.get(id=project_id)

        # Get all properties in this project
        property_ids = []
        for property_list in project.property_lists.all():
            property_ids.extend(
                property_list.properties
                .filter(state__in=['STAGE2_COMPLETE', 'STAGE3_COMPLETE'])
                .values_list('id', flat=True)
            )

        # Remove duplicates
        property_ids = list(set(property_ids))

        # Queue bulk task
        bulk_calculate_ratings.delay(property_ids, project_id=project_id)

        return f'Queued rating calculation for {len(property_ids)} properties in project {project.title}'

    except Project.DoesNotExist:
        logger.error(f'Project {project_id} does not exist')
        raise ValueError(f'Project {project_id} does not exist')


@shared_task(bind=True, max_retries=0)
def scrape_rightmove_properties(self, task_uuid, max_properties=500):
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

        # Send initial SSE update
        _send_list_event(
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

            _send_list_event(
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

        # Send completion SSE update
        _send_list_event(
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

            # Send failure SSE update
            _send_list_event(
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
        except Exception:
            pass

        raise




@shared_task(bind=True, max_retries=0)
def scrape_zoopla_properties(self, task_uuid, max_properties=100):
    from property.models import PropertyListTask
    from property.services.property_creation.zoopla_service import ZooplaService
    from django.core.exceptions import ValidationError

    logger.debug("scrape_zoopla_properties started task_uuid=%s max_properties=%d", task_uuid, max_properties)

    try:
        task = PropertyListTask.objects.get(uuid=task_uuid)
        property_list = task.property_list
        search_criteria = property_list.search_criteria

        if not search_criteria:
            raise ValueError("PropertyList does not have search criteria configured")

        task.status = 'IN_PROGRESS'
        task.celery_task_id = self.request.id
        task.save(update_fields=['status', 'celery_task_id', 'updated_at'])

        _send_list_event(
            property_list.uuid,
            'scrape_progress',
            {
                'source': 'zoopla',
                'task_uuid': task_uuid,
                'status': 'IN_PROGRESS',
                'completed_items': 0,
                'total_items': 0,
                'failed_items': 0,
                'progress_percentage': 0,
                'errors': [],
                'message': 'Starting Zoopla property search...'
            }
        )

        criteria_dict = {
            'area': search_criteria.area,
            'bedrooms_min': search_criteria.bedrooms_min,
            'bedrooms_max': search_criteria.bedrooms_max,
            'price_min': search_criteria.price_min,
            'price_max': search_criteria.price_max,
            'radius': search_criteria.radius,
            'property_types': search_criteria.property_types,
            'max_days_since_added': search_criteria.max_days_since_added,
        }

        service = ZooplaService()

        def progress_callback(created, total):
            task.total_items = total
            task.completed_items = created
            task.save(update_fields=['total_items', 'completed_items', 'updated_at'])
            _send_list_event(
                property_list.uuid,
                'scrape_progress',
                {
                    'source': 'zoopla',
                    'task_uuid': task_uuid,
                    'status': 'IN_PROGRESS',
                    'completed_items': created,
                    'total_items': total,
                    'failed_items': task.failed_items,
                    'progress_percentage': int((created / total) * 100) if total > 0 else 0,
                    'errors': task.errors,
                    'message': f'Zoopla: scraped {created} of {total} properties...'
                }
            )

        properties_data = service.scrape_properties_by_search(
            criteria_dict,
            max_properties=max_properties,
            progress_callback=progress_callback
        )
        logger.debug("scrape_zoopla_properties task=%s scrape returned %d properties", task_uuid, len(properties_data))

        def batch_progress_callback(created, updated, failed):
            task.failed_items = failed
            task.save(update_fields=['failed_items', 'updated_at'])

        result = service.batch_create_properties(
            properties_data,
            property_list,
            progress_callback=batch_progress_callback
        )

        created_count = result['created']
        updated_count = result['updated']

        for error in result['errors']:
            task.add_error(f"Failed to create property: {error['error']}", error)

        task.status = 'COMPLETED'
        task.completed_at = timezone.now()
        task.metadata['created_count'] = created_count
        task.metadata['updated_count'] = updated_count
        task.metadata['source'] = 'zoopla'
        task.save(update_fields=['status', 'completed_at', 'metadata', 'updated_at'])

        _send_list_event(
            property_list.uuid,
            'scrape_complete',
            {
                'source': 'zoopla',
                'task_uuid': task_uuid,
                'status': 'COMPLETED',
                'completed_items': created_count,
                'total_items': len(properties_data),
                'failed_items': task.failed_items,
                'progress_percentage': 100,
                'errors': task.errors,
                'metadata': {'created': created_count, 'updated': updated_count},
                'message': f'Zoopla scrape completed: {created_count} created, {updated_count} updated'
            }
        )

        return {
            'status': 'completed',
            'source': 'zoopla',
            'created': created_count,
            'updated': updated_count,
            'failed': task.failed_items,
            'total': len(properties_data)
        }

    except (PropertyListTask.DoesNotExist, ValidationError):
        logger.error("scrape_zoopla_properties task=%s not found or invalid", task_uuid)
        return {'status': 'failed', 'error': f'Task {task_uuid} not found'}
    except Exception as e:
        logger.error("scrape_zoopla_properties task=%s failed: %s", task_uuid, e, exc_info=True)
        try:
            task.status = 'FAILED'
            task.error_message = str(e)
            task.completed_at = timezone.now()
            task.save(update_fields=['status', 'error_message', 'completed_at', 'updated_at'])
            _send_list_event(
                property_list.uuid,
                'scrape_failed',
                {
                    'source': 'zoopla',
                    'task_uuid': task_uuid,
                    'status': 'FAILED',
                    'completed_items': 0,
                    'total_items': 0,
                    'failed_items': 0,
                    'progress_percentage': 0,
                    'errors': [str(e)],
                    'message': f'Zoopla scrape failed: {str(e)}'
                }
            )
        except Exception:
            pass
        raise


@shared_task(bind=True, max_retries=0)
def enrich_properties_task(self, task_uuid):
    from property.models import PropertyListTask, Property
    from property.services.property_creation.factory import property_creation_service_factory

    task = PropertyListTask.objects.get(uuid=task_uuid)
    task.status = 'IN_PROGRESS'
    task.save()

    property_uuids = task.metadata.get('property_uuids', [])
    completed = 0
    failed = 0
    errors = []

    for puuid in property_uuids:
        try:
            prop = Property.objects.get(uuid=puuid)
            if prop.is_enriched:
                completed += 1
                continue
            if not prop.external_url:
                failed += 1
                errors.append(f'{puuid}: no external_url')
                continue
            service = property_creation_service_factory(prop.external_url, 'url')
            if not service or not hasattr(service, 'enrich_property_data'):
                failed += 1
                errors.append(f'{puuid}: no enrichment service')
                continue
            enriched = service.enrich_property_data(prop)
            prop.apply_enrichment(enriched)
            completed += 1
        except Exception as e:
            failed += 1
            errors.append(f'{puuid}: {str(e)}')
            logger.error("enrich_properties_task failed for uuid=%s: %s", puuid, e, exc_info=True)

        task.completed_items = completed
        task.failed_items = failed
        task.save()

    task.status = 'COMPLETED'
    task.errors = errors
    task.save()


def _publish_sse(channel: str, event_type: str, data: dict) -> None:
    """Publish a JSON-encoded SSE event to a Redis pub/sub channel."""
    import redis as _redis
    client = _redis.Redis.from_url(settings.REDIS_URL)
    try:
        payload = _json.dumps({'type': event_type, 'data': data})
        client.publish(channel, payload)
        logger.info(f"SSE published: channel={channel} type={event_type}")
    finally:
        client.close()


def _send_property_event(property_uuid, event_type: str, data: dict) -> None:
    _publish_sse(f'sse:property:{property_uuid}', event_type, data)


def _send_list_event(list_uuid, event_type: str, data: dict) -> None:
    _publish_sse(f'sse:property-list:{list_uuid}', event_type, data)


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
        'property_id': str(property_obj.uuid),
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

    # Send to property channel
    _send_property_event(property_obj.uuid, 'service_update', message_data)

    # Also send to all property list channels that contain this property
    for property_list in property_obj.property_lists.all():
        _send_list_event(property_list.uuid, 'service_update', message_data)


def _get_enabled_services_from_project(property_obj):
    """
    Get enabled services from property's project.

    Since context options are now at project level, all lists in same project
    share the same context options. We just need to get it from any list's project.

    Args:
        property_obj: Property instance

    Returns:
        List of unique service names enabled for the project
    """
    enabled_services = set()

    # Get project from any property list
    property_list = property_obj.property_lists.first()
    if property_list:
        project = property_list.project
        if hasattr(project, 'context_options'):
            enabled_services.update(project.context_options.get_enabled_services())

    return list(enabled_services)


def _get_service_params(property_obj, service_name):
    """
    Get service-specific parameters for fetch_data call.

    For POI service: Compiles poi_types from all projects
    For Schools service: Compiles school_types from all projects
    For other services: Returns empty dict

    Args:
        property_obj: Property instance
        service_name: Name of the service

    Returns:
        Dict of parameters to pass to service.fetch_data()
    """
    if service_name == 'schools':
        # Compile school types from all projects
        school_types_set = set()

        for property_list in property_obj.property_lists.all():
            project = property_list.project
            context_options = getattr(project, 'context_options', None)
            if context_options and context_options.enable_schools:
                # Add school_types from this project
                if context_options.school_types:
                    school_types_set.update(context_options.school_types)

        return {
            'school_types': list(school_types_set) if school_types_set else ['nursery', 'primary', 'secondary', 'all_through']
        }

    if service_name == 'poi':
        # Compile POI types from all projects
        poi_types_set = set()
        radius = 1600  # Default

        for property_list in property_obj.property_lists.all():
            project = property_list.project
            context_options = getattr(project, 'context_options', None)
            if context_options and context_options.enable_poi:
                # Add poi_types from this project
                if context_options.poi_types:
                    poi_types_set.update(context_options.poi_types)
                # Use the largest radius from all projects
                if context_options.poi_search_radius_meters:
                    radius = max(radius, context_options.poi_search_radius_meters)

        return {
            'poi_types': list(poi_types_set),
            'radius': radius
        }

    if service_name == 'saved_locations':
        # Compile saved location UUIDs from all projects
        saved_location_uuids_set = set()

        for property_list in property_obj.property_lists.all():
            project = property_list.project
            context_options = getattr(project, 'context_options', None)
            if context_options and context_options.enable_saved_locations:
                # Add saved_location_uuids from this project
                if context_options.saved_location_uuids:
                    saved_location_uuids_set.update(context_options.saved_location_uuids)

        return {
            'saved_location_uuids': list(saved_location_uuids_set)
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
        completion_data = {
            'property_id': str(property_obj.uuid),
            'property_state': property_obj.state,
            'message': 'Context data retrieval complete'
        }

        # Send to property channel
        _send_property_event(property_obj.uuid, 'stage2_complete', completion_data)

        # Also send to all property list channels that contain this property
        for property_list in property_obj.property_lists.all():
            _send_list_event(property_list.uuid, 'stage2_complete', completion_data)


def _send_rating_complete(property_obj, result):
    """
    Send WebSocket update when rating calculation completes.

    Args:
        property_obj: Property instance
        result: Rating calculation result dict
    """
    message_data = {
        'property_id': str(property_obj.uuid),
        'property_state': property_obj.state,
        'overall_rating': result['overall_rating'],
        'rating_breakdown': result['breakdown'],
        'disqualified': result['disqualified'],
        'disqualification_reason': result.get('disqualification_reason'),
        'message': 'Rating calculation complete'
    }

    # Send to property channel
    _send_property_event(property_obj.uuid, 'rating_complete', message_data)

    # Also send to all property list channels that contain this property
    for property_list in property_obj.property_lists.all():
        _send_list_event(property_list.uuid, 'rating_complete', message_data)

    logger.info(f'Sent rating_complete SSE update for property {property_obj.id}')


def _send_rating_failed(property_obj, error_message):
    """
    Send WebSocket update when rating calculation fails.

    Args:
        property_obj: Property instance
        error_message: Error description
    """
    message_data = {
        'property_id': str(property_obj.uuid),
        'property_state': property_obj.state,
        'error': error_message,
        'message': 'Rating calculation failed'
    }

    # Send to property channel
    _send_property_event(property_obj.uuid, 'rating_failed', message_data)

    # Also send to all property list channels that contain this property
    for property_list in property_obj.property_lists.all():
        _send_list_event(property_list.uuid, 'rating_failed', message_data)

    logger.info(f'Sent rating_failed SSE update for property {property_obj.id}')
