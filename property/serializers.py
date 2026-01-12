from rest_framework import serializers
from property.models import Property, PropertyList, SavedLocation


class PropertyListSerializer(serializers.ModelSerializer):
    """Serializer for PropertyList model"""

    owner = serializers.ReadOnlyField(source='owner.username')
    properties_count = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()

    class Meta:
        model = PropertyList
        fields = [
            'id', 'uuid', 'owner', 'title', 'state',
            'rating_criteria', 'rating_criteria_source',
            'viewers', 'contributors',
            'properties_count', 'status_summary',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uuid', 'owner', 'state', 'created_at', 'updated_at']

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

    property_list_title = serializers.ReadOnlyField(source='property_list.title')
    property_list_uuid = serializers.ReadOnlyField(source='property_list.uuid')
    state_display = serializers.CharField(source='get_state_display', read_only=True)

    class Meta:
        model = Property
        fields = [
            'id', 'uuid', 'property_list', 'property_list_uuid', 'property_list_title',
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
            'id', 'uuid', 'state', 'state_display', 'property_list_uuid', 'property_list_title',
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
        fields = ['id', 'uuid', 'user', 'name', 'address', 'latitude', 'longitude', 'created_at', 'updated_at']
        read_only_fields = ['id', 'uuid', 'user', 'created_at', 'updated_at']

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user
        return super().create(validated_data)


class PropertyListDetailSerializer(PropertyListSerializer):
    """Extended serializer with properties for detail view"""

    properties = PropertySerializer(many=True, read_only=True)

    class Meta(PropertyListSerializer.Meta):
        fields = PropertyListSerializer.Meta.fields + ['properties']
