from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
import re
from decimal import Decimal
from property.models import Property, PropertyList, SavedLocation


class CreateFromInputSerializer(serializers.Serializer):
    """Serializer for create-from-input endpoint request"""

    input_data = serializers.CharField(
        required=True,
        allow_blank=False,
        help_text="URL or text to extract property data from"
    )
    input_type = serializers.ChoiceField(
        choices=['url', 'text'],
        default='url',
        help_text="Type of input: 'url' or 'text'"
    )

    def validate_input_data(self, value):
        """Validate input_data is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Input data cannot be empty")
        return value.strip()


class PropertyListSerializer(serializers.ModelSerializer):
    """Serializer for PropertyList model"""

    owner = serializers.ReadOnlyField(source='owner.username')
    properties_count = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    viewers = serializers.SlugRelatedField(
        slug_field='email',
        queryset=User.objects.all(),
        many=True,
        required=False
    )
    contributors = serializers.SlugRelatedField(
        slug_field='email',
        queryset=User.objects.all(),
        many=True,
        required=False
    )

    class Meta:
        model = PropertyList
        fields = [
            'uuid', 'owner', 'title', 'state',
            'viewers', 'contributors',
            'properties_count', 'status_summary',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'state', 'created_at', 'updated_at']

    def get_properties_count(self, obj):
        return obj.properties.count()

    def get_status_summary(self, obj):
        return obj.get_status_summary()

    def create(self, validated_data):
        # Set owner from request user
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class PropertySerializer(serializers.ModelSerializer):
    """Serializer for Property model"""

    property_list = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=PropertyList.objects.all()
    )
    property_list_title = serializers.ReadOnlyField(source='property_list.title')
    state_display = serializers.CharField(source='get_state_display', read_only=True)

    class Meta:
        model = Property
        fields = [
            'uuid', 'property_list', 'property_list_title',
            'state', 'state_display',
            'title', 'address_line_1', 'address_line_2', 'city', 'postcode',
            'latitude', 'longitude',
            'price', 'bedrooms', 'bathrooms', 'square_area',
            'garden', 'parking', 'furnished_status',
            'council_tax_band', 'epc_rating', 'lease_length', 'floor_level',
            'child_suitable', 'completion_date',
            'external_id', 'external_url',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'uuid', 'state', 'state_display', 'property_list_title',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'created_at', 'updated_at'
        ]

    def validate_property_list(self, value):
        """Ensure user can only add properties to their own lists"""
        request = self.context.get('request')
        if request and value.owner != request.user:
            raise serializers.ValidationError("Cannot add property to another user's list")
        return value

    def validate_postcode(self, value):
        """Validate UK postcode format"""
        if not value:
            return value

        # UK postcode regex pattern
        uk_postcode_pattern = r'^[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}$'
        if not re.match(uk_postcode_pattern, value.upper().strip()):
            raise serializers.ValidationError("Invalid UK postcode format")
        return value.upper().strip()

    def validate_external_url(self, value):
        """Validate external URL format"""
        if not value:
            return value

        validator = URLValidator()
        try:
            validator(value)
        except DjangoValidationError:
            raise serializers.ValidationError("Invalid URL format")
        return value

    def validate_price(self, value):
        """Validate price is positive and within reasonable range"""
        if value is not None:
            if value <= 0:
                raise serializers.ValidationError("Price must be greater than zero")
            if value > Decimal('100000000'):  # 100 million
                raise serializers.ValidationError("Price exceeds maximum allowed value")
        return value

    def validate_latitude(self, value):
        """Validate latitude is within UK bounds"""
        if value is not None:
            # UK latitude range approximately 49.9 to 60.9
            if not (Decimal('49.0') <= value <= Decimal('61.0')):
                raise serializers.ValidationError("Latitude must be within UK bounds (49.0 to 61.0)")
        return value

    def validate_longitude(self, value):
        """Validate longitude is within UK bounds"""
        if value is not None:
            # UK longitude range approximately -8.6 to 1.8
            if not (Decimal('-9.0') <= value <= Decimal('2.0')):
                raise serializers.ValidationError("Longitude must be within UK bounds (-9.0 to 2.0)")
        return value

    def validate_bedrooms(self, value):
        """Validate bedrooms is positive"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Bedrooms cannot be negative")
        if value is not None and value > 50:
            raise serializers.ValidationError("Bedrooms exceeds reasonable maximum")
        return value

    def validate_bathrooms(self, value):
        """Validate bathrooms is positive"""
        if value is not None and value < 0:
            raise serializers.ValidationError("Bathrooms cannot be negative")
        if value is not None and value > 20:
            raise serializers.ValidationError("Bathrooms exceeds reasonable maximum")
        return value

    def validate(self, data):
        """Cross-field validation"""
        # Ensure at minimum title and postcode exist
        if not data.get('title'):
            raise serializers.ValidationError({'title': 'Property title is required'})
        if not data.get('postcode'):
            raise serializers.ValidationError({'postcode': 'Postcode is required'})

        return data


class PropertyDetailSerializer(PropertySerializer):
    """Extended serializer with related data for detail view"""

    context_data = serializers.SerializerMethodField()
    available_transitions = serializers.SerializerMethodField()

    class Meta(PropertySerializer.Meta):
        fields = PropertySerializer.Meta.fields + ['context_data', 'available_transitions']

    def get_context_data(self, obj):
        """Return context data summary"""
        # TODO: Implement in Phase 4
        return []

    def get_available_transitions(self, obj):
        """Return available FSM transitions"""
        return [
            transition.name for transition in obj.get_available_state_transitions()
        ]


class SavedLocationSerializer(serializers.ModelSerializer):
    """Serializer for SavedLocation model"""

    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = SavedLocation
        fields = ['uuid', 'user', 'name', 'address', 'latitude', 'longitude', 'created_at', 'updated_at']
        read_only_fields = ['uuid', 'user', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class PropertyListDetailSerializer(PropertyListSerializer):
    """Extended serializer with properties for detail view"""

    properties = PropertySerializer(many=True, read_only=True)

    class Meta(PropertyListSerializer.Meta):
        fields = PropertyListSerializer.Meta.fields + ['properties']
