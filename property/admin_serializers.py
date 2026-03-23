"""
Serializers for admin CRUD operations
"""
from rest_framework import serializers
from .models import (
    Property, PropertyList, PropertyImage, SearchCriteria,
    PropertyListTask, ContextOptions, ContextData,
    RatingCriteria, Criterion, CriterionScore, SavedLocation,
    StateTransitionLog
)


class PropertyListSerializer(serializers.ModelSerializer):
    """Full serializer for PropertyList with related counts"""
    owner_username = serializers.CharField(source='owner.username', read_only=True)
    properties_count = serializers.SerializerMethodField()

    class Meta:
        model = PropertyList
        fields = [
            'uuid', 'title', 'state', 'owner', 'owner_username',
            'rating_criteria', 'rating_criteria_source', 'search_criteria',
            'properties_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'created_at', 'updated_at']

    def get_properties_count(self, obj):
        return obj.properties.count()


class PropertyImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = PropertyImage
        fields = ['id', 'source_url', 'url', 'caption', 'order', 'created_at']


class PropertySerializer(serializers.ModelSerializer):
    """Full serializer for Property with related data"""
    images = PropertyImageSerializer(many=True, read_only=True)
    lists_count = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'uuid', 'title', 'state',
            'address_line_1', 'address_line_2', 'city', 'postcode',
            'latitude', 'longitude',
            'price', 'bedrooms', 'bathrooms', 'square_area',
            'garden', 'parking', 'furnished_status',
            'council_tax_band', 'epc_rating', 'lease_length', 'floor_level',
            'child_suitable', 'completion_date',
            'external_id', 'external_url',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'images', 'lists_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'state', 'normalized_address', 'overall_rating', 'created_at', 'updated_at']

    def get_lists_count(self, obj):
        return obj.property_lists.count()


class PropertyListTaskSerializer(serializers.ModelSerializer):
    """Serializer for PropertyListTask"""
    list_title = serializers.CharField(source='property_list.title', read_only=True)
    list_uuid = serializers.UUIDField(source='property_list.uuid', read_only=True)
    progress_percentage = serializers.SerializerMethodField()

    class Meta:
        model = PropertyListTask
        fields = [
            'uuid', 'property_list', 'list_title', 'list_uuid',
            'task_type', 'status', 'celery_task_id',
            'total_items', 'completed_items', 'failed_items',
            'progress_percentage', 'errors', 'error_message', 'metadata',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['uuid', 'created_at', 'updated_at', 'completed_at']

    def get_progress_percentage(self, obj):
        return obj.progress_percentage


class ContextDataSerializer(serializers.ModelSerializer):
    """Serializer for ContextData"""
    property_title = serializers.CharField(source='property.title', read_only=True)
    property_uuid = serializers.UUIDField(source='property.uuid', read_only=True)

    class Meta:
        model = ContextData
        fields = [
            'id', 'uuid', 'property', 'property_title', 'property_uuid',
            'service_name', 'status', 'data',
            'error_message', 'error_type', 'retry_count',
            'created_at', 'last_attempt_at', 'completed_at'
        ]
        read_only_fields = ['uuid', 'created_at', 'last_attempt_at', 'completed_at']
