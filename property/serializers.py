from rest_framework import serializers
from django.contrib.auth.models import User
from django.core.validators import URLValidator
from django.core.exceptions import ValidationError as DjangoValidationError
import re
from decimal import Decimal
from property.models.stage1_models import Property, PropertyList, SavedLocation, SearchCriteria, PropertyListTask, PropertyImage, Project, TaskList, Task, ProjectInvitation, AppNotification, PropertyFavorite, KeyFeature, ProjectComment
from property.models.stage2_models import ContextOptions
from property.models.stage3_models import RatingCriteria, Criterion, CriterionScore
from property.models.models_poi import PlaceOfInterest
from property.utils.geocoding import geocode_postcode


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


class ProjectSerializer(serializers.ModelSerializer):
    """Serializer for Project model"""

    owner = serializers.ReadOnlyField(source='owner.username')
    property_lists_count = serializers.SerializerMethodField()
    viewers = serializers.SlugRelatedField(
        slug_field='email',
        many=True,
        queryset=User.objects.all(),
        required=False
    )
    contributors = serializers.SlugRelatedField(
        slug_field='email',
        many=True,
        queryset=User.objects.all(),
        required=False
    )
    # Use UUID for rating_criteria (consistent with RatingCriteriaViewSet lookup)
    rating_criteria = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=RatingCriteria.objects.all(),
        allow_null=True,
        required=False
    )
    rating_criteria_name = serializers.SerializerMethodField()
    rating_criteria_source = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=RatingCriteria.objects.all(),
        allow_null=True,
        required=False
    )
    rating_criteria_source_name = serializers.SerializerMethodField()
    has_context_options = serializers.SerializerMethodField()
    context_options = serializers.SerializerMethodField()

    class Meta:
        model = Project
        fields = [
            'uuid', 'owner', 'title', 'description',
            'viewers', 'contributors', 'property_lists_count',
            'rating_criteria', 'rating_criteria_name',
            'rating_criteria_source', 'rating_criteria_source_name',
            'has_context_options', 'context_options',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'created_at', 'updated_at']

    def get_property_lists_count(self, obj):
        return obj.property_lists.count()

    def get_rating_criteria_name(self, obj):
        return obj.rating_criteria.name if obj.rating_criteria else None

    def get_rating_criteria_source_name(self, obj):
        return obj.rating_criteria_source.name if obj.rating_criteria_source else None

    def get_has_context_options(self, obj):
        return hasattr(obj, 'context_options')

    def get_context_options(self, obj):
        if hasattr(obj, 'context_options'):
            # Lazy import to avoid circular dependency since ContextOptionsSerializer is defined later
            serializer = ContextOptionsSerializer(obj.context_options)
            return serializer.data
        return None

    def validate_rating_criteria(self, value):
        """Validate that user owns the rating criteria"""
        if value and self.context.get('request'):
            user = self.context['request'].user
            if value.owner != user:
                raise serializers.ValidationError(
                    "You can only use rating criteria that you own"
                )
        return value

    def create(self, validated_data):
        viewers = validated_data.pop('viewers', [])
        contributors = validated_data.pop('contributors', [])
        validated_data['owner'] = self.context['request'].user
        project = super().create(validated_data)
        project.viewers.set(viewers)
        project.contributors.set(contributors)
        return project

    def update(self, instance, validated_data):
        viewers = validated_data.pop('viewers', None)
        contributors = validated_data.pop('contributors', None)
        instance = super().update(instance, validated_data)
        if viewers is not None:
            instance.viewers.set(viewers)
        if contributors is not None:
            instance.contributors.set(contributors)
        return instance


class TaskSerializer(serializers.ModelSerializer):
    """Serializer for Task model"""

    task_list_uuid = serializers.UUIDField(source='task_list.uuid', read_only=True)
    task_list_input = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=TaskList.objects.all(),
        source='task_list',
        write_only=True,
        required=False
    )
    assigned_to_email = serializers.ReadOnlyField(source='assigned_to.email')
    assigned_to_input = serializers.SlugRelatedField(
        slug_field='email',
        queryset=User.objects.all(),
        source='assigned_to',
        write_only=True,
        required=False,
        allow_null=True
    )
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)

    class Meta:
        model = Task
        fields = [
            'uuid', 'task_list_uuid', 'task_list_input', 'title', 'description',
            'status', 'status_display', 'priority', 'priority_display',
            'assigned_to_email', 'assigned_to_input', 'due_date', 'order',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = ['uuid', 'task_list_uuid', 'assigned_to_email', 'created_at', 'updated_at', 'completed_at']



class TaskListSerializer(serializers.ModelSerializer):
    """Serializer for TaskList model"""

    project_uuid = serializers.UUIDField(source='project.uuid', read_only=True)
    project_input = serializers.SlugRelatedField(
        slug_field='uuid',
        queryset=Project.objects.all(),
        source='project',
        write_only=True,
        required=False
    )
    project_title = serializers.ReadOnlyField(source='project.title')
    tasks_count = serializers.SerializerMethodField()
    tasks = TaskSerializer(many=True, read_only=True)

    class Meta:
        model = TaskList
        fields = [
            'uuid', 'project_uuid', 'project_input', 'project_title', 'title', 'description',
            'tasks_count', 'tasks',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'project_uuid', 'created_at', 'updated_at']


    def get_tasks_count(self, obj):
        return obj.tasks.count()


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
    project = serializers.ReadOnlyField(source='project.uuid')
    project_uuid = serializers.PrimaryKeyRelatedField(
        queryset=Project.objects.all(),
        source='project',
        write_only=True,
        pk_field=serializers.UUIDField()
    )
    project_title = serializers.ReadOnlyField(source='project.title')
    properties_count = serializers.SerializerMethodField()
    status_summary = serializers.SerializerMethodField()
    average_price = serializers.SerializerMethodField()
    highest_price = serializers.SerializerMethodField()
    lowest_price = serializers.SerializerMethodField()
    search_criteria = SearchCriteriaSerializer(read_only=True)

    class Meta:
        model = PropertyList
        fields = [
            'uuid', 'owner', 'title',
            'project', 'project_uuid', 'project_title',
            'search_criteria',
            'properties_count', 'status_summary',
            'average_price', 'highest_price', 'lowest_price',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'created_at', 'updated_at']

    def get_properties_count(self, obj):
        return obj.properties.count()

    def get_status_summary(self, obj):
        return obj.get_status_summary()

    def get_average_price(self, obj):
        from django.db.models import Avg
        result = obj.properties.aggregate(avg_price=Avg('price'))
        return round(result['avg_price'], 2) if result['avg_price'] else None

    def get_highest_price(self, obj):
        from django.db.models import Max
        result = obj.properties.aggregate(max_price=Max('price'))
        return result['max_price']

    def get_lowest_price(self, obj):
        from django.db.models import Min
        result = obj.properties.aggregate(min_price=Min('price'))
        return result['min_price']

    def create(self, validated_data):
        user = self.context['request'].user
        validated_data['owner'] = user

        # If no project provided, use or create default project
        if 'project' not in validated_data or validated_data['project'] is None:
            default_project, created = Project.objects.get_or_create(
                owner=user,
                title="My Properties",
                defaults={'description': 'Default project for standalone property lists'}
            )
            validated_data['project'] = default_project

        return super().create(validated_data)


class PropertyImageSerializer(serializers.ModelSerializer):
    """Serializer for PropertyImage model"""

    class Meta:
        model = PropertyImage
        fields = ['id', 'source_url', 'url', 'caption', 'order', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class PropertyFavoriteSerializer(serializers.ModelSerializer):
    """Serializer for PropertyFavorite model"""

    property_uuid = serializers.UUIDField(source='property.uuid', read_only=True)
    user = serializers.ReadOnlyField(source='user.username')

    class Meta:
        model = PropertyFavorite
        fields = ['uuid', 'user', 'property_uuid', 'created_at']
        read_only_fields = ['uuid', 'user', 'created_at']


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


class KeyFeatureSerializer(serializers.ModelSerializer):
    class Meta:
        model = KeyFeature
        fields = ['order', 'description']


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
    overall_rating = serializers.FloatField(allow_null=True, read_only=True)
    is_favorited = serializers.SerializerMethodField()
    key_features = KeyFeatureSerializer(many=True, read_only=True)

    class Meta:
        model = Property
        fields = [
            'uuid', 'property_lists', 'property_lists_input', 'summary',
            'state', 'state_display',
            'title', 'address_line_1', 'address_line_2', 'city', 'postcode',
            'latitude', 'longitude',
            'price', 'price_frequency', 'currency_code',
            'bedrooms', 'bathrooms', 'square_area',
            'garden', 'parking', 'furnished_status',
            'property_type', 'description',
            'council_tax_band', 'epc_rating', 'lease_length', 'floor_level',
            'child_suitable',
            'let_available_date', 'first_visible_date',
            'key_features', 'added_or_reduced', 'display_size',
            'listing_update_reason', 'listing_update_date',
            'external_id', 'external_url',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'images', 'primary_image', 'is_favorited',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'uuid', 'state', 'state_display', 'property_lists', 'currency_code', 'property_type',
            'let_available_date', 'first_visible_date',
            'key_features', 'added_or_reduced', 'display_size',
            'listing_update_reason', 'listing_update_date',
            'normalized_address', 'uprn',
            'overall_rating', 'rating_breakdown', 'disqualified', 'disqualification_reason',
            'images', 'primary_image', 'is_favorited',
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

    def get_is_favorited(self, obj):
        """Check if current user has favorited this property"""
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            return PropertyFavorite.objects.filter(user=request.user, property=obj).exists()
        return False

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
        if not self.partial:
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
        fields = ['uuid', 'user', 'name', 'postcode', 'address_line_1', 'address_line_2', 'city', 'latitude', 'longitude', 'created_at', 'updated_at']
        read_only_fields = ['uuid', 'user', 'latitude', 'longitude', 'created_at', 'updated_at']

    def validate_postcode(self, value):
        """Validate postcode is not empty"""
        if not value or not value.strip():
            raise serializers.ValidationError("Postcode cannot be empty")
        return value.strip().upper()

    def create(self, validated_data):
        validated_data['user'] = self.context['request'].user

        # Auto-geocode from postcode if lat/lng not provided
        if 'latitude' not in validated_data or 'longitude' not in validated_data:
            postcode = validated_data.get('postcode')
            if postcode:
                lat, lng = geocode_postcode(postcode)
                if lat and lng:
                    validated_data['latitude'] = lat
                    validated_data['longitude'] = lng

        return super().create(validated_data)

    def update(self, instance, validated_data):
        # If postcode changed, re-geocode
        postcode = validated_data.get('postcode')
        if postcode and postcode != instance.postcode:
            lat, lng = geocode_postcode(postcode)
            if lat and lng:
                validated_data['latitude'] = lat
                validated_data['longitude'] = lng

        return super().update(instance, validated_data)


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

    project_uuid = serializers.ReadOnlyField(source='project.uuid')
    project_title = serializers.ReadOnlyField(source='project.title')

    class Meta:
        model = ContextOptions
        fields = [
            'uuid',
            'project_uuid',
            'project_title',
            'enable_crime',
            'enable_schools',
            'school_types',
            'enable_broadband',
            'enable_mobile',
            'enable_poi',
            'enable_council_tax',
            'poi_types',
            'poi_search_radius_meters',
            'enable_saved_locations',
            'saved_location_uuids',
            'created_at',
            'updated_at',
        ]
        read_only_fields = ['uuid', 'project_uuid', 'project_title', 'created_at', 'updated_at']


# Context Report Data Serializers

class PlaceSerializer(serializers.Serializer):
    """Serializer for POI Place data"""
    place_id = serializers.CharField()
    name = serializers.CharField()
    address = serializers.CharField(required=False, allow_null=True)
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_km = serializers.FloatField()
    straight_distance_km = serializers.FloatField(required=False, allow_null=True)
    walking_distance_km = serializers.FloatField(required=False, allow_null=True)
    walking_time_min = serializers.FloatField(required=False, allow_null=True)
    driving_distance_km = serializers.FloatField(required=False, allow_null=True)
    driving_time_min = serializers.FloatField(required=False, allow_null=True)
    website_url = serializers.URLField(required=False, allow_null=True, allow_blank=True)
    phone_number = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    google_maps_url = serializers.URLField()
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
    pupil_count = serializers.IntegerField(required=False, allow_null=True)
    type = serializers.CharField()
    ofsted_url = serializers.URLField(required=False, allow_null=True)


class SchoolStatisticsSerializer(serializers.Serializer):
    """Serializer for School statistics"""
    nursery_count = serializers.IntegerField(required=False, allow_null=True)
    primary_count = serializers.IntegerField(required=False, allow_null=True)
    secondary_count = serializers.IntegerField(required=False, allow_null=True)
    all_through_count = serializers.IntegerField(required=False, allow_null=True)
    closest_nursery_km = serializers.FloatField(required=False, allow_null=True)
    closest_primary_km = serializers.FloatField(required=False, allow_null=True)
    closest_secondary_km = serializers.FloatField(required=False, allow_null=True)


class SchoolsReportDataSerializer(serializers.Serializer):
    """Serializer for Schools report data matching frontend SchoolsReportData interface"""
    statistics = SchoolStatisticsSerializer()
    nursery_schools = SchoolSerializer(many=True, required=False)
    primary_schools = SchoolSerializer(many=True, required=False)
    secondary_schools = SchoolSerializer(many=True, required=False)
    all_through_schools = SchoolSerializer(many=True, required=False)
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
    postcode_sector = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    monthly_breakdown = serializers.ListField(child=serializers.DictField(), required=False)


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
    """
    Serializer for Mobile coverage report data matching frontend MobileCoverageReportData interface

    Unified format supporting both dataset (network aggregates) and API (per-provider) sources
    """
    scores = CoverageScoresSerializer()
    four_g_coverage = serializers.DictField()
    five_g_coverage_high_confidence = serializers.DictField(required=False, allow_null=True)
    data_source = serializers.CharField()
    granularity = serializers.CharField()
    laua_name = serializers.CharField(required=False, allow_null=True)

    # Optional provider-specific data (only present when from API source)
    providers = serializers.DictField(required=False, allow_null=True)


class CouncilTaxReportDataSerializer(serializers.Serializer):
    """Serializer for Council Tax report data matching frontend CouncilTaxReportData interface"""
    band = serializers.CharField(allow_null=True)
    band_range = serializers.CharField(allow_null=True)
    local_authority = serializers.CharField(allow_null=True)
    address = serializers.CharField(required=False, allow_null=True)
    is_exact_match = serializers.BooleanField(default=True)
    country = serializers.CharField(default='England')
    retrieved_at = serializers.CharField(allow_null=True)


class SavedLocationDistanceSerializer(serializers.Serializer):
    """Serializer for individual saved location distance data"""
    location_id = serializers.IntegerField()
    location_uuid = serializers.UUIDField()
    location_name = serializers.CharField()
    address = serializers.CharField()
    postcode = serializers.CharField()
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    distance_km = serializers.FloatField()
    distance_miles = serializers.FloatField()


class SavedLocationsReportDataSerializer(serializers.Serializer):
    """Serializer for Saved Locations report data matching frontend SavedLocationsReportData interface"""
    distances = SavedLocationDistanceSerializer(many=True)
    total_locations = serializers.IntegerField()
    closest_location = SavedLocationDistanceSerializer(allow_null=True, required=False)


# ============================================================================
# Stage 3: Rating System Serializers
# ============================================================================

class CriterionSerializer(serializers.ModelSerializer):
    """Serializer for individual rating criterion"""

    class Meta:
        model = Criterion
        fields = [
            'id', 'name', 'source', 'field_name', 'saved_location_uuid', 'poi_category',
            'distance_calculation_preference', 'enabled', 'weight', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_weight(self, value):
        """Validate weight is one of allowed values"""
        allowed = [Decimal('0.25'), Decimal('0.5'), Decimal('1.0'), Decimal('1.5')]
        if value not in allowed:
            raise serializers.ValidationError(
                "Weight must be one of: 0.25 (Not Important), 0.5 (Nice to Have), 1.0 (Important), 1.5 (Very Important)"
            )
        return value

    def validate(self, data):
        """Cross-field validation"""
        # Validate source-specific fields
        if data.get('source') in ['property', 'context']:
            if not data.get('field_name'):
                raise serializers.ValidationError({
                    'field_name': 'field_name is required when source is "property" or "context"'
                })

        return data


class RatingCriteriaSerializer(serializers.ModelSerializer):
    """Serializer for rating criteria with nested criteria"""

    owner = serializers.ReadOnlyField(source='owner.username')
    criteria = CriterionSerializer(many=True, read_only=True)
    criteria_count = serializers.SerializerMethodField()

    class Meta:
        model = RatingCriteria
        fields = [
            'uuid', 'name', 'owner', 'criteria', 'criteria_count',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['uuid', 'owner', 'created_at', 'updated_at']

    def get_criteria_count(self, obj):
        return obj.criteria.count()


class RatingCriteriaCreateSerializer(serializers.ModelSerializer):
    """Serializer for creating rating criteria with nested criteria"""

    criteria = CriterionSerializer(many=True)

    class Meta:
        model = RatingCriteria
        fields = ['name', 'criteria']

    def create(self, validated_data):
        criteria_data = validated_data.pop('criteria')
        rating_criteria = RatingCriteria.objects.create(**validated_data)

        # Create criteria
        for criterion_data in criteria_data:
            Criterion.objects.create(rating_criteria=rating_criteria, **criterion_data)

        return rating_criteria

    def update(self, instance, validated_data):
        criteria_data = validated_data.pop('criteria', None)

        # Update rating criteria fields
        instance.name = validated_data.get('name', instance.name)
        instance.save()

        # Update criteria if provided
        if criteria_data is not None:
            # Delete existing criteria
            instance.criteria.all().delete()

            # Create new criteria
            for criterion_data in criteria_data:
                Criterion.objects.create(rating_criteria=instance, **criterion_data)

        return instance


class CriterionScoreSerializer(serializers.ModelSerializer):
    """Serializer for criterion score results"""

    criterion_name = serializers.ReadOnlyField(source='criterion.name')
    criterion_weight = serializers.ReadOnlyField(source='criterion.weight')

    class Meta:
        model = CriterionScore
        fields = [
            'id', 'criterion', 'criterion_name', 'criterion_weight',
            'raw_value', 'normalized_score', 'weighted_score',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class PropertyRatingSerializer(serializers.Serializer):
    """Serializer for property rating results"""

    property_id = serializers.UUIDField(source='uuid')
    overall_rating = serializers.FloatField(allow_null=True)
    rating_breakdown = serializers.JSONField(allow_null=True)
    disqualified = serializers.BooleanField()
    disqualification_reason = serializers.CharField(allow_blank=True)
    criterion_scores = CriterionScoreSerializer(many=True, read_only=True)

    # Include basic property info for context
    title = serializers.CharField()
    address_line_1 = serializers.CharField()
    postcode = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    state = serializers.CharField()


class PropertyComparisonSerializer(serializers.Serializer):
    """Serializer for property comparison view (compact)"""

    property_id = serializers.UUIDField(source='uuid')
    title = serializers.CharField()
    address_line_1 = serializers.CharField()
    postcode = serializers.CharField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    bedrooms = serializers.IntegerField(allow_null=True)
    bathrooms = serializers.IntegerField(allow_null=True)
    overall_rating = serializers.FloatField(allow_null=True)
    disqualified = serializers.BooleanField()
    disqualification_reason = serializers.CharField(allow_blank=True)
    state = serializers.CharField()


class MemberSerializer(serializers.Serializer):
    email = serializers.EmailField()
    first_name = serializers.CharField()
    last_name = serializers.CharField()


class ProjectMembersSerializer(serializers.Serializer):
    owner = MemberSerializer()
    viewers = MemberSerializer(many=True)
    contributors = MemberSerializer(many=True)


class ProjectInvitationSerializer(serializers.ModelSerializer):
    invited_by_email = serializers.ReadOnlyField(source='invited_by.email')
    invited_by_name = serializers.SerializerMethodField()
    project_title = serializers.ReadOnlyField(source='project.title')
    invite_url = serializers.SerializerMethodField()

    class Meta:
        model = ProjectInvitation
        fields = [
            'uuid', 'invited_email', 'role', 'status',
            'invited_by_email', 'invited_by_name', 'project_title',
            'invite_url', 'expires_at', 'created_at', 'accepted_at',
        ]
        read_only_fields = fields

    def get_invited_by_name(self, obj):
        return f"{obj.invited_by.first_name} {obj.invited_by.last_name}".strip() or obj.invited_by.email

    def get_invite_url(self, obj):
        return self.context.get('invite_url')


class InvitePreviewSerializer(serializers.Serializer):
    project_uuid = serializers.UUIDField()
    project_title = serializers.CharField()
    invited_by_name = serializers.CharField()
    invited_by_email = serializers.EmailField()
    role = serializers.CharField()
    expires_at = serializers.DateTimeField()


class UserSearchSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ['email', 'first_name', 'last_name']


class AppNotificationSerializer(serializers.ModelSerializer):
    actor_email = serializers.SerializerMethodField()
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = AppNotification
        fields = [
            'uuid', 'notification_type', 'title', 'message',
            'related_object_uuid', 'related_object_type',
            'is_read', 'created_at', 'actor_email', 'actor_name',
        ]
        read_only_fields = fields

    def get_actor_email(self, obj):
        return obj.actor.email if obj.actor else None

    def get_actor_name(self, obj):
        if not obj.actor:
            return None
        return f"{obj.actor.first_name} {obj.actor.last_name}".strip() or obj.actor.email



class ProjectCommentSerializer(serializers.ModelSerializer):
    author_email = serializers.ReadOnlyField(source='author.email')
    author_name = serializers.SerializerMethodField()

    class Meta:
        model = ProjectComment
        fields = ['uuid', 'body', 'author_email', 'author_name', 'created_at', 'updated_at']
        read_only_fields = ['uuid', 'author_email', 'author_name', 'created_at', 'updated_at']

    def get_author_name(self, obj):
        return f"{obj.author.first_name} {obj.author.last_name}".strip() or obj.author.email
