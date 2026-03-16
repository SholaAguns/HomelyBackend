from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
import re
from decimal import Decimal
from property.models import Property, PropertyList, SavedLocation, SearchCriteria, PropertyListTask, PropertyImage, PlaceOfInterest
from property.stage2_models import ContextOptions


class SearchCriteriaSerializer(serializers.ModelSerializer):
    """Serializer for SearchCriteria model"""

    class Meta:
        model = SearchCriteria
        fields = [
            'id', 'area', 'bedrooms_min', 'bedrooms_max',
            'bathrooms_min', 'bathrooms_max', 'price_min', 'price_max',
            'radius', 'property_types', 'max_days_since_added',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_area(self, value):
        """Validate area is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Area cannot be empty")
        return value.strip()

    def validate(self, data):
        """Cross-field validation"""
        # Validate min/max ranges
        if data.get('bedrooms_min') and data.get('bedrooms_max'):
            if data['bedrooms_min'] > data['bedrooms_max']:
                raise serializers.ValidationError({
                    'bedrooms_min': 'Minimum bedrooms cannot be greater than maximum'
                })

        if data.get('bathrooms_min') and data.get('bathrooms_max'):
            if data['bathrooms_min'] > data['bathrooms_max']:
                raise serializers.ValidationError({
                    'bathrooms_min': 'Minimum bathrooms cannot be greater than maximum'
                })

        if data.get('price_min') and data.get('price_max'):
            if data['price_min'] > data['price_max']:
                raise serializers.ValidationError({
                    'price_min': 'Minimum price cannot be greater than maximum'
                })

        return data


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


class BulkPropertyCreationSerializer(serializers.Serializer):
    """Serializer for bulk property creation from search"""

    search_criteria = SearchCriteriaSerializer(required=True)
    max_properties = serializers.IntegerField(
        default=100,
        min_value=1,
        max_value=100,
        help_text="Maximum number of properties to scrape (1-100)"
    )


class PropertyListSerializer(serializers.ModelSerializer):
    """Serializer for PropertyList model"""

    owner = serializers.ReadOnlyField(source='owner.username')
    properties_count = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    search_criteria = SearchCriteriaSerializer(read_only=True)
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
            'search_criteria', 'viewers', 'contributors',
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


class PropertyImageSerializer(serializers.ModelSerializer):
    """Serializer for PropertyImage model"""

    class Meta:
        model = PropertyImage
        fields = ['id', 'source_url', 'url', 'caption', 'order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PlaceOfInterestSerializer(serializers.ModelSerializer):
    """Serializer for PlaceOfInterest model"""

    class Meta:
        model = PlaceOfInterest
        fields = [
            'uuid', 'place_id', 'place_type', 'name', 'address',
            'latitude', 'longitude', 'website_url', 'phone_number',
            'google_maps_url', 'straight_distance_km',
            'driving_distance_km', 'driving_time_min',
            'walking_distance_km', 'walking_time_min',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'created_at', 'updated_at']


class PropertySerializer(serializers.ModelSerializer):
    """Serializer for Property model"""

    property_lists = serializers.SerializerMethodField()
    property_lists_input = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=PropertyList.objects.all(),
        many=True,
        write_only=True,
        required=False,
        source='property_lists'
    )
    state_display = serializers.CharField(source='get_state_display', read_only=True)
    images = PropertyImageSerializer(many=True, read_only=True)
    primary_image = serializers.SerializerMethodField()

    class Meta:
        model = Property
        fields = [
            'uuid', 'property_lists', 'property_lists_input',
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
            'images', 'primary_image',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'uuid', 'state', 'state_display', 'property_lists',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'images', 'primary_image',
            'created_at', 'updated_at'
        ]

    def get_property_lists(self, obj):
        """Get dict of {uuid: title} for lists this property belongs to (filtered by owner access)"""
        request = self.context.get('request')
        if not request:
            return {}

        # Filter to lists owned by current user (TODO: add contributor access)
        user_lists = obj.property_lists.filter(owner=request.user)
        return {str(pl.uuid): pl.title for pl in user_lists}

    def validate_property_lists_input(self, value):
        """Ensure user can only add properties to their own lists"""
        request = self.context.get('request')
        if request:
            for prop_list in value:
                if prop_list.owner != request.user:
                    raise serializers.ValidationError("Cannot add property to another user's list")
        return value

    def get_primary_image(self, obj):
        """Get the primary (first) image for the property"""
        first_image = obj.images.first()
        return PropertyImageSerializer(first_image).data if first_image else None

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


class PropertyListTaskSerializer(serializers.ModelSerializer):
    """Serializer for PropertyListTask model"""

    property_list_uuid = serializers.ReadOnlyField(source='property_list.uuid')
    property_list_title = serializers.ReadOnlyField(source='property_list.title')
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    task_type_display = serializers.CharField(source='get_task_type_display', read_only=True)
    progress_percentage = serializers.IntegerField(read_only=True)
    websocket_url = serializers.SerializerMethodField()

    class Meta:
        model = PropertyListTask
        fields = [
            'uuid', 'property_list_uuid', 'property_list_title',
            'task_type', 'task_type_display', 'status', 'status_display',
            'celery_task_id', 'total_items', 'completed_items', 'failed_items',
            'progress_percentage', 'errors', 'error_message', 'metadata',
            'websocket_url', 'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = [
            'uuid', 'property_list_uuid', 'property_list_title',
            'status', 'status_display', 'task_type_display',
            'celery_task_id', 'total_items', 'completed_items', 'failed_items',
            'progress_percentage', 'errors', 'error_message', 'metadata',
            'websocket_url', 'created_at', 'updated_at', 'completed_at'
        ]

    def get_websocket_url(self, obj):
        """Return websocket URL for progress updates"""
        request = self.context.get('request')
        if request:
            ws_scheme = 'wss' if request.is_secure() else 'ws'
            host = request.get_host()
            return f"{ws_scheme}://{host}/ws/property-list/{obj.property_list.uuid}/"
        return None


class ContextOptionsSerializer(serializers.ModelSerializer):
    """Serializer for ContextOptions model"""

    property_list_uuid = serializers.ReadOnlyField(source='property_list.uuid')

    class Meta:
        model = ContextOptions
        fields = [
            'uuid',
            'property_list_uuid',
            'enable_crime',
            'enable_schools',
            'enable_broadband',
            'enable_mobile',
            'enable_poi',
            'enable_council_tax',
            'poi_types',
            'poi_search_radius_meters',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['uuid', 'property_list_uuid', 'created_at', 'updated_at']


# Context Report Data Serializers

class PlaceSerializer(serializers.Serializer):
    """Serializer for POI Place data"""
    name = serializers.CharField()
    distance_km = serializers.FloatField()
    address = serializers.CharField(required=False, allow_null=True)
    rating = serializers.FloatField(required=False, allow_null=True)
    user_ratings_total = serializers.IntegerField(required=False, allow_null=True)


class PoiReportDataSerializer(serializers.Serializer):
    """Serializer for POI report data matching frontend PoiReportData interface"""
    total_places = serializers.IntegerField()
    categories = serializers.ListField(child=serializers.CharField(), required=False)
    by_category = serializers.DictField(required=False)  # Dict of category -> list of places
    data_source = serializers.CharField()
    search_radius_km = serializers.FloatField()

    def validate_by_category(self, value):
        """Validate that by_category values are lists of place dicts"""
        if value:
            for category, places in value.items():
                if not isinstance(places, list):
                    raise serializers.ValidationError(f"Category '{category}' must contain a list of places")
                # Validate each place
                for place in places:
                    place_serializer = PlaceSerializer(data=place)
                    place_serializer.is_valid(raise_exception=True)
        return value


class SchoolSerializer(serializers.Serializer):
    """Serializer for School data"""
    name = serializers.CharField()
    distance_miles = serializers.FloatField()
    pupil_count = serializers.IntegerField()
    type = serializers.CharField()
    ofsted_url = serializers.URLField(required=False, allow_null=True)


class SchoolStatisticsSerializer(serializers.Serializer):
    """Serializer for School statistics"""
    primary_count = serializers.IntegerField()
    secondary_count = serializers.IntegerField()
    closest_primary_km = serializers.FloatField(required=False, allow_null=True)
    closest_secondary_km = serializers.FloatField(required=False, allow_null=True)


class SchoolsReportDataSerializer(serializers.Serializer):
    """Serializer for Schools report data matching frontend SchoolsReportData interface"""
    statistics = SchoolStatisticsSerializer()
    primary_schools = SchoolSerializer(many=True, required=False)
    secondary_schools = SchoolSerializer(many=True, required=False)
    note = serializers.CharField(required=False, allow_null=True)


class CrimeCategorySerializer(serializers.Serializer):
    """Serializer for Crime category data"""
    category = serializers.CharField()
    count = serializers.IntegerField()


class CrimeReportDataSerializer(serializers.Serializer):
    """Serializer for Crime report data matching frontend CrimeReportData interface"""
    total_crimes = serializers.IntegerField()
    period = serializers.CharField()
    crime_rating = serializers.CharField()
    top_categories = CrimeCategorySerializer(many=True)
    data_source = serializers.CharField()
    postcode_sector = serializers.CharField()


class FullFibreDataSerializer(serializers.Serializer):
    """Serializer for full fibre data"""
    availability_pct = serializers.FloatField()
    take_up_pct = serializers.FloatField()


class BroadbandReportDataSerializer(serializers.Serializer):
    """Serializer for Broadband report data matching frontend BroadbandReportData interface"""
    max_download_mbps = serializers.FloatField()
    max_upload_mbps = serializers.FloatField()
    full_fibre = FullFibreDataSerializer(required=False, allow_null=True)
    data_source = serializers.CharField()
    granularity = serializers.CharField()


class CoverageByNetworkSerializer(serializers.Serializer):
    """Serializer for coverage breakdown by network count"""
    all_4_networks = serializers.FloatField()
    three_networks = serializers.FloatField()
    two_networks = serializers.FloatField()
    one_network = serializers.FloatField()
    no_coverage = serializers.FloatField()


class CoverageScoresSerializer(serializers.Serializer):
    """Serializer for composite coverage scores"""
    four_g_coverage = serializers.FloatField()
    five_g_coverage = serializers.FloatField()
    overall_coverage = serializers.FloatField()


class MobileCoverageReportDataSerializer(serializers.Serializer):
    """Serializer for Mobile coverage report data matching frontend MobileCoverageReportData interface"""
    scores = CoverageScoresSerializer()
    four_g_coverage = serializers.DictField()
    five_g_coverage_high_confidence = serializers.DictField(required=False, allow_null=True)
    data_source = serializers.CharField()
    granularity = serializers.CharField()
    laua_name = serializers.CharField(required=False, allow_null=True)


class CouncilTaxReportDataSerializer(serializers.Serializer):
    """Serializer for Council Tax report data matching frontend CouncilTaxReportData interface"""
    band = serializers.CharField(allow_null=True)
    band_range = serializers.CharField(allow_null=True)
    local_authority = serializers.CharField(allow_null=True)
    address = serializers.CharField(required=False, allow_null=True)
    is_exact_match = serializers.BooleanField(default=True)
    country = serializers.CharField(default='England')
    retrieved_at = serializers.CharField(allow_null=True)
