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
    SearchCriteriaSerializer
)
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

    @action(detail=True, methods=['post'])
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
            property_data = service.extract_property_data(input_data)

            # If property_list provided, create Property model
            if property_list:
                from property.models import PropertyImage

                # Extract images before mapping
                images_data = property_data.pop('images', [])

                property_fields = self._map_extracted_to_property(property_data)
                property_obj = None

                # Check if property exists globally by external_id
                if property_fields.get('external_id'):
                    existing = Property.objects.filter(
                        external_id=property_fields['external_id']
                    ).first()

                    if existing:
                        # Add to current list if not already there
                        if not existing.property_lists.filter(uuid=property_list.uuid).exists():
                            existing.property_lists.add(property_list)

                        # Update property fields
                        for field, value in property_fields.items():
                            if field not in ['uuid', 'created_at']:
                                setattr(existing, field, value)
                        existing.save()
                        property_obj = existing

                        # Update images
                        if images_data:
                            property_obj.images.all().delete()
                            for idx, image_data in enumerate(images_data):
                                PropertyImage.objects.create(
                                    property=property_obj,
                                    source_url=image_data.get('source_url') or image_data.get('srcUrl') or '',
                                    url=image_data.get('url') or '',
                                    caption=image_data.get('caption') or '',
                                    order=idx
                                )

                        property_serializer = PropertySerializer(existing, context={'request': request})
                        return Response({
                            'success': True,
                            'property': property_serializer.data,
                            'created': False,
                            'updated': True,
                            'message': 'Property already exists, added to list and updated with latest data',
                            'source': service.__class__.__name__
                        })

                # Create new property
                property_obj = Property.objects.create(**property_fields)
                property_obj.property_lists.add(property_list)

                # Create images
                if images_data:
                    for idx, image_data in enumerate(images_data):
                        PropertyImage.objects.create(
                            property=property_obj,
                            source_url=image_data.get('source_url', image_data.get('srcUrl', '')),
                            url=image_data.get('url', ''),
                            caption=image_data.get('caption', ''),
                            order=idx
                        )

                property_serializer = PropertySerializer(property_obj, context={'request': request})

                return Response({
                    'success': True,
                    'property': property_serializer.data,
                    'created': True,
                    'message': 'Property created successfully',
                    'source': service.__class__.__name__
                }, status=status.HTTP_201_CREATED)

            # No property_list_uuid, just return data
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

    def _map_extracted_to_property(self, property_data: dict) -> dict:

        from decimal import Decimal

        # Handle postcode extraction from address if not present
        postcode = property_data.get('postcode', '')
        if not postcode and property_data.get('address'):
            import re
            postcode_match = re.search(
                r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}',
                property_data['address']
            )
            if postcode_match:
                postcode = postcode_match.group(0)

        if not postcode:
            postcode = ''

        return {
            'external_id': property_data.get('external_id', ''),
            'external_url': property_data.get('external_url', property_data.get('link', '')),
            'title': property_data.get('title', property_data.get('address', 'Untitled')),
            'address_line_1': property_data.get('address', property_data.get('address_line_1', '')),
            'address_line_2': property_data.get('address_line_2', ''),
            'city': property_data.get('city', ''),
            'postcode': postcode,
            'latitude': property_data.get('latitude'),
            'longitude': property_data.get('longitude'),
            'price': Decimal(str(property_data.get('price', 0))),
            'bedrooms': property_data.get('bedrooms', 0),
            'bathrooms': property_data.get('bathrooms', 0),
            'garden': property_data.get('garden', False),
            'parking': property_data.get('parking', False),
            'furnished_status': property_data.get('furnished_status', ''),
            'square_area': property_data.get('square_area'),
        }


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
