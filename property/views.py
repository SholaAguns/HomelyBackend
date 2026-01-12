from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from property.models import Property, PropertyList, SavedLocation
from property.serializers import (
    PropertySerializer, PropertyDetailSerializer,
    PropertyListSerializer, PropertyListDetailSerializer,
    SavedLocationSerializer
)
from property.tasks import retrieve_context_data, calculate_property_rating


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
        queryset = Property.objects.filter(property_list__owner=self.request.user)

        # Optional filter by property_list uuid
        property_list_uuid = self.request.query_params.get('property_list')
        if property_list_uuid:
            queryset = queryset.filter(property_list__uuid=property_list_uuid)

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
