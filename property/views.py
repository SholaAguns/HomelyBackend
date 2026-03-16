import logging

from django.db import transaction
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

logger = logging.getLogger('property.views')

from property.models import Property, PropertyList, SavedLocation, PropertyListTask, SearchCriteria
from property.serializers import (
    PropertySerializer, PropertyDetailSerializer,
    PropertyListSerializer, PropertyListDetailSerializer,
    SavedLocationSerializer, CreateFromInputSerializer,
    BulkPropertyCreationSerializer, PropertyListTaskSerializer,
    PlaceOfInterestSerializer,
    ContextOptionsSerializer,
)
from property.stage2_models import ContextOptions
from property.tasks import retrieve_context_data, calculate_property_rating, scrape_rightmove_properties
from property.services import property_creation_service_factory


class PropertyListViewSet(viewsets.ModelViewSet):
    """
    ViewSet for PropertyList CRUD operations.

    Users can only access their own property lists.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PropertyListSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to user's own lists"""
        return PropertyList.objects.filter(owner=self.request.user)

    def get_serializer_class(self):
        """Use detailed serializer for retrieve action"""
        if self.action == 'retrieve':
            return PropertyListDetailSerializer
        return PropertyListSerializer

    @action(detail=True, methods=['post'])
    def activate(self, request, uuid=None):
        """Activate a property list (DRAFT → ACTIVE)"""
        property_list = self.get_object()

        try:
            property_list.activate()
            property_list.save()
            return Response({
                'status': 'activated',
                'state': property_list.state
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'], url_path='run-stage2-bulk')
    def run_stage2_bulk(self, request, uuid=None):
        """Trigger Stage 2 for all properties in NEW state"""
        from property.tasks import bulk_retrieve_context_data

        property_list = self.get_object()

        # Get all properties in NEW state
        new_properties = property_list.properties.filter(state='NEW')

        if not new_properties.exists():
            return Response({
                'error': 'No properties in NEW state',
                'message': 'All properties have already started or completed Stage 2'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Queue bulk task with property_list_id
        property_ids = list(new_properties.values_list('id', flat=True))
        bulk_retrieve_context_data.delay(property_ids, property_list.id)

        return Response({
            'status': 'bulk_stage2_queued',
            'property_count': len(property_ids),
            'message': f'Stage 2 queued for {len(property_ids)} properties'
        })

    @extend_schema(
        request=BulkPropertyCreationSerializer,
        responses={
            202: PropertyListTaskSerializer,
            400: OpenApiResponse(description="Invalid search criteria"),
        },
        description="Start bulk property scraping from Rightmove search criteria. Returns task details for tracking progress."
    )
    @action(detail=True, methods=['post'], url_path='create-from-search')
    @transaction.atomic
    def create_from_search(self, request, uuid=None):
        property_list = self.get_object()
        logger.debug("create_from_search requested for property_list=%s by user=%s", uuid, request.user.id)

        serializer = BulkPropertyCreationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        search_criteria_data = serializer.validated_data['search_criteria']
        max_properties = serializer.validated_data.get('max_properties', 100)
        logger.debug("create_from_search criteria=%s max_properties=%d", search_criteria_data, max_properties)

        if property_list.search_criteria:
            search_criteria = property_list.search_criteria
            for field, value in search_criteria_data.items():
                setattr(search_criteria, field, value)
            search_criteria.save()
            logger.debug("create_from_search updated existing search_criteria=%s", search_criteria.id)
        else:
            search_criteria = SearchCriteria.objects.create(**search_criteria_data)
            property_list.search_criteria = search_criteria
            property_list.save()
            logger.debug("create_from_search created new search_criteria=%s", search_criteria.id)

        task = PropertyListTask.objects.create(
            property_list=property_list,
            task_type='SCRAPE_SEARCH',
            status='QUEUED'
        )

        transaction.on_commit(
            lambda: scrape_rightmove_properties.delay(str(task.uuid), max_properties=max_properties)
        )
        logger.debug("create_from_search queued task=%s", task.uuid)

        task_serializer = PropertyListTaskSerializer(task, context={'request': request})
        return Response(task_serializer.data, status=status.HTTP_202_ACCEPTED)

    @extend_schema(
        responses={
            200: PropertyListTaskSerializer,
            404: OpenApiResponse(description="Task not found"),
        },
        description="Get status of a scraping task. Polling fallback for clients without websocket support."
    )
    @action(detail=True, methods=['get'], url_path='scrape-status/(?P<task_uuid>[^/.]+)')
    def scrape_status(self, request, uuid=None, task_uuid=None):
        """
        Get scraping task status.

        Polling endpoint for progress updates (fallback for no websocket).
        Returns current task status, progress, and errors.
        """
        property_list = self.get_object()

        try:
            task = PropertyListTask.objects.get(
                uuid=task_uuid,
                property_list=property_list
            )

            serializer = PropertyListTaskSerializer(task, context={'request': request})
            return Response(serializer.data)

        except PropertyListTask.DoesNotExist:
            return Response(
                {'error': f'Task {task_uuid} not found for this property list'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get', 'put', 'patch'], url_path='context-options')
    def context_options(self, request, uuid=None):
        """Get or update context options for a property list"""
        property_list = self.get_object()
        context_options_obj, _ = ContextOptions.objects.get_or_create(property_list=property_list)

        if request.method == 'GET':
            serializer = ContextOptionsSerializer(context_options_obj)
            return Response(serializer.data)

        partial = request.method == 'PATCH'
        serializer = ContextOptionsSerializer(context_options_obj, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class PropertyViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Property CRUD operations.

    Users can only access properties in their own lists.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PropertySerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to properties in user's lists"""
        queryset = Property.objects.filter(property_lists__owner=self.request.user).distinct()

        # Optional filter by property_list uuid
        property_list_uuid = self.request.query_params.get('property_list')
        if property_list_uuid:
            queryset = queryset.filter(property_lists__uuid=property_list_uuid)

        return queryset

    def get_serializer_class(self):
        """Use detailed serializer for retrieve action"""
        if self.action == 'retrieve':
            return PropertyDetailSerializer
        return PropertySerializer

    @action(detail=True, methods=['post'], url_path='run-stage2')
    def run_stage2(self, request, uuid=None):
        """Trigger Stage 2 context retrieval (NEW → STAGE2_IN_PROGRESS)"""
        property_obj = self.get_object()

        try:
            property_obj.run_stage2()
            property_obj.save()

            # Queue Celery task (uses internal id)
            retrieve_context_data.delay(property_obj.id)

            return Response({
                'status': 'stage2_started',
                'state': property_obj.state,
                'message': 'Context data retrieval queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def run_stage3(self, request, uuid=None):
        """Trigger Stage 3 rating calculation (STAGE2_COMPLETE → STAGE3_IN_PROGRESS)"""
        property_obj = self.get_object()

        try:
            property_obj.run_stage3()
            property_obj.save()

            # Queue Celery task (uses internal id)
            calculate_property_rating.delay(property_obj.id)

            return Response({
                'status': 'stage3_started',
                'state': property_obj.state,
                'message': 'Rating calculation queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['post'])
    def rerun_services(self, request, uuid=None):
        """Rerun context services (STAGE2_COMPLETE/STAGE3_* → STAGE2_IN_PROGRESS)"""
        property_obj = self.get_object()

        try:
            property_obj.rerun_services()
            property_obj.save()

            # Queue Celery task (uses internal id)
            retrieve_context_data.delay(property_obj.id)

            return Response({
                'status': 'services_rerun_started',
                'state': property_obj.state,
                'message': 'Context services rerun queued'
            })
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )

    @action(detail=True, methods=['get'], url_path='context-data')
    def context_data(self, request, uuid=None):
        """Get all context data for a property"""
        from property.models import ContextData
        from property.utils.report_transformers import transform_context_data

        property_obj = self.get_object()
        context_data = ContextData.objects.filter(property=property_obj)

        data = []
        for cd in context_data:
            # Transform service data to match frontend expectations
            transformed_data = None
            if cd.status == 'COMPLETE' and cd.data:
                transformed_data = transform_context_data(cd.service_name, cd.data)

            data.append({
                'id': str(cd.uuid),
                'property_id': str(property_obj.uuid),
                'service_name': cd.service_name,
                'status': cd.status,
                'data': transformed_data,
                'error_message': cd.error_message,
                'started_at': cd.last_attempt_at,
                'completed_at': cd.completed_at,
                'cached': False
            })

        return Response(data)

    @action(detail=True, methods=['get'], url_path='context-data/(?P<service_name>[^/.]+)')
    def context_data_detail(self, request, uuid=None, service_name=None):
        """Get specific service context data for a property"""
        from property.models import ContextData

        property_obj = self.get_object()

        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name=service_name
            )

            return Response({
                'service_name': context_data.service_name,
                'status': context_data.status,
                'data': context_data.data,
                'error_message': context_data.error_message,
                'error_type': context_data.error_type,
                'retry_count': context_data.retry_count,
                'completed_at': context_data.completed_at,
                'last_attempt_at': context_data.last_attempt_at
            })
        except ContextData.DoesNotExist:
            return Response(
                {'error': f'No context data found for service {service_name}'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['post'], url_path='retry-service/(?P<service_name>[^/.]+)')
    def retry_service(self, request, uuid=None, service_name=None):
        """Retry a failed context service"""
        from property.models import ContextData
        from property.tasks import run_service_task

        property_obj = self.get_object()

        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name=service_name
            )

            if context_data.status not in ['FAILED', 'COMPLETE']:
                return Response(
                    {'error': f'Service {service_name} is currently {context_data.status}'},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Reset to PENDING and queue task
            context_data.status = 'PENDING'
            context_data.error_message = ''
            context_data.error_type = ''
            context_data.save()

            run_service_task.delay(property_obj.id, service_name)

            return Response({
                'status': 'service_retry_queued',
                'service_name': service_name,
                'message': f'Service {service_name} queued for retry'
            })

        except ContextData.DoesNotExist:
            return Response(
                {'error': f'No context data found for service {service_name}'},
                status=status.HTTP_404_NOT_FOUND
            )

    @action(detail=True, methods=['get'], url_path='broadband')
    def broadband(self, request, uuid=None):
        """Get broadband coverage data for property"""
        from property.models import ContextData
        from property.services.context_retrieval.broadband_dataset_service import BroadbandDatasetService

        property_obj = self.get_object()

        # Try to get from context data first
        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name='broadband'
            )

            if context_data.status == 'COMPLETE':
                return Response(context_data.data)
            elif context_data.status == 'FAILED':
                return Response(
                    {
                        'error': 'Failed to fetch broadband data',
                        'message': context_data.error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            else:
                return Response(
                    {
                        'status': context_data.status,
                        'message': 'Broadband data is being fetched'
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        except ContextData.DoesNotExist:
            # Fetch on-demand if not in context data
            try:
                service = BroadbandDatasetService()
                data = service.fetch_data(property_obj)
                return Response(data)
            except Exception as e:
                return Response(
                    {'error': f'Failed to fetch broadband data: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    @action(detail=True, methods=['get'], url_path='mobile')
    def mobile(self, request, uuid=None):
        """Get mobile coverage data for property"""
        from property.models import ContextData
        from property.services.context_retrieval.mobile_dataset_service import MobileDatasetService

        property_obj = self.get_object()

        # Try to get from context data first
        try:
            context_data = ContextData.objects.get(
                property=property_obj,
                service_name='mobile'
            )

            if context_data.status == 'COMPLETE':
                return Response(context_data.data)
            elif context_data.status == 'FAILED':
                return Response(
                    {
                        'error': 'Failed to fetch mobile data',
                        'message': context_data.error_message
                    },
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )
            else:
                return Response(
                    {
                        'status': context_data.status,
                        'message': 'Mobile data is being fetched'
                    },
                    status=status.HTTP_202_ACCEPTED
                )

        except ContextData.DoesNotExist:
            # Fetch on-demand if not in context data
            try:
                service = MobileDatasetService()
                data = service.fetch_data(property_obj)
                return Response(data)
            except Exception as e:
                return Response(
                    {'error': f'Failed to fetch mobile data: {str(e)}'},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

    @action(detail=True, methods=['get'], url_path='places-of-interest')
    def places_of_interest(self, request, uuid=None):
        """
        Get Places of Interest for property.

        Optional query param:
        - place_type: Filter by specific type (e.g., 'school', 'hospital')
        """
        from property.models import PlaceOfInterest

        property_obj = self.get_object()
        place_type = request.query_params.get('place_type')

        # Query POIs for this property
        pois = PlaceOfInterest.objects.filter(property=property_obj)

        # Filter by type if specified
        if place_type:
            pois = pois.filter(place_type=place_type)

        # Order by distance
        pois = pois.order_by('place_type', 'straight_distance_km')

        serializer = PlaceOfInterestSerializer(pois, many=True)
        return Response(serializer.data)

    @extend_schema(
        request=CreateFromInputSerializer,
        responses={
            200: OpenApiResponse(
                description="Property data extracted successfully",
                examples=[
                    OpenApiExample(
                        'Success Response',
                        value={
                            "success": True,
                            "property_data": {
                                "title": "3 bedroom house in London",
                                "price": "500000.00",
                                "address_line_1": "123 Example Street",
                                "city": "London",
                                "postcode": "SW1A 1AA",
                                "bedrooms": 3,
                                "bathrooms": 2,
                                "garden": True,
                                "parking": False,
                                "external_url": "https://www.rightmove.co.uk/properties/123456",
                                "external_id": "123456"
                            },
                            "source": "RightmoveService",
                            "message": "Property data extracted successfully"
                        }
                    )
                ]
            ),
            201: PropertySerializer,
            400: OpenApiResponse(description="Invalid input or extraction failed"),
        },
        description="Extract property data from URL or text input. Optionally create Property model if property_list_uuid provided."
    )
    @action(detail=False, methods=['post'], url_path='create-from-input')
    def create_from_input(self, request):
        """
        Extract property data from URL or text input.

        If property_list_uuid is provided, creates Property model and adds to list.
        Otherwise, returns unsaved property data that can be used to populate form.
        """
        # Validate input using serializer
        serializer = CreateFromInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        input_data = serializer.validated_data['input_data']
        input_type = serializer.validated_data['input_type']
        property_list_uuid = request.data.get('property_list_uuid')

        # Validate property_list access BEFORE extracting data
        property_list = None
        if property_list_uuid:
            try:
                property_list = PropertyList.objects.get(
                    uuid=property_list_uuid,
                    owner=request.user
                )
            except PropertyList.DoesNotExist:
                return Response(
                    {'error': 'Property list not found or access denied'},
                    status=status.HTTP_404_NOT_FOUND
                )

        # Get appropriate service
        service = property_creation_service_factory(input_data, input_type)

        if not service:
            return Response(
                {
                    'error': 'No service available to handle this input',
                    'message': f'Could not find a service to process this {input_type}'
                },
                status=status.HTTP_400_BAD_REQUEST
            )

        # Extract property data
        try:
            # If property_list provided, create Property model using service
            if property_list:
                property_obj, created = service.create_property(input_data, input_type, property_list)

                property_serializer = PropertySerializer(property_obj, context={'request': request})

                if created:
                    return Response({
                        'success': True,
                        'property': property_serializer.data,
                        'created': True,
                        'message': 'Property created successfully',
                        'source': service.__class__.__name__
                    }, status=status.HTTP_201_CREATED)
                else:
                    return Response({
                        'success': True,
                        'property': property_serializer.data,
                        'created': False,
                        'updated': True,
                        'message': 'Property already exists, added to list and updated with latest data',
                        'source': service.__class__.__name__
                    })

            # No property_list_uuid, just extract and return data
            property_data = service.extract_property_data(input_data, input_type)
            return Response({
                'success': True,
                'property_data': property_data,
                'source': service.__class__.__name__,
                'message': 'Property data extracted successfully'
            })

        except ValueError as e:
            return Response(
                {
                    'error': 'Extraction failed',
                    'message': str(e)
                },
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as e:
            return Response(
                {
                    'error': 'Unexpected error',
                    'message': str(e)
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )



class SavedLocationViewSet(viewsets.ModelViewSet):
    """
    ViewSet for SavedLocation CRUD operations.

    Users can only access their own saved locations.
    Lookup by UUID for public-facing URLs.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = SavedLocationSerializer
    lookup_field = 'uuid'

    def get_queryset(self):
        """Filter to user's own saved locations"""
        return SavedLocation.objects.filter(user=self.request.user)


class SchoolViewSet(viewsets.ViewSet):
    """
    ViewSet for school-related operations.

    Provides endpoints for retrieving Ofsted reports.
    """
    permission_classes = [IsAuthenticated]

    def ofsted_report(self, request, urn=None):
        """
        Get Ofsted report for a school by URN.

        Returns cached data if available (30 days TTL).

        Example:
            GET /api/schools/ofsted/100000/
        """
        from property.services.context_retrieval.ofsted_service import OfstedService

        if not urn:
            return Response(
                {'error': 'URN is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Fetch Ofsted data
        data = OfstedService.get_ofsted_report(urn)

        # Check if error
        if 'error' in data:
            if data['error'] == 'School not found':
                return Response(data, status=status.HTTP_404_NOT_FOUND)
            else:
                return Response(data, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(data, status=status.HTTP_200_OK)
