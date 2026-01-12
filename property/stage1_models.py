from django.db import models
from django.contrib.auth.models import User
from django_fsm import FSMField, transition
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class PropertyList(models.Model):
    """Container for a collection of properties with shared configuration"""

    STATE_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
    ]

    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_lists')
    title = models.CharField(max_length=255)
    state = FSMField(default='DRAFT', choices=STATE_CHOICES)

    # Optional configurations
    rating_criteria = models.ForeignKey('RatingCriteria', null=True, blank=True, on_delete=models.SET_NULL, related_name='property_lists')
    rating_criteria_source = models.ForeignKey('RatingCriteria', null=True, blank=True, on_delete=models.SET_NULL, related_name='derived_lists')

    # Collaboration
    viewers = models.ManyToManyField(User, related_name='viewable_lists', blank=True)
    contributors = models.ManyToManyField(User, related_name='editable_lists', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_lists'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.owner.username})"

    @transition(field=state, source='DRAFT', target='ACTIVE')
    def activate(self):
        """Transition from Draft to Active"""
        pass

    def get_status_summary(self):
        """Returns aggregated status of all properties in list"""
        properties = self.properties.all()
        return {
            'total': properties.count(),
            'new': properties.filter(state='NEW').count(),
            'stage2_in_progress': properties.filter(state='STAGE2_IN_PROGRESS').count(),
            'stage2_complete': properties.filter(state='STAGE2_COMPLETE').count(),
            'stage3_in_progress': properties.filter(state='STAGE3_IN_PROGRESS').count(),
            'stage3_complete': properties.filter(state='STAGE3_COMPLETE').count(),
        }


class ContextOptions(models.Model):
    """Configuration for which context services to enable for a property list"""

    property_list = models.OneToOneField(PropertyList, on_delete=models.CASCADE, related_name='context_options')

    # Service toggles
    enable_crime = models.BooleanField(default=False)
    enable_schools = models.BooleanField(default=False)
    enable_broadband = models.BooleanField(default=False)
    enable_mobile = models.BooleanField(default=False)

    # POI configuration
    enable_poi = models.BooleanField(default=False)
    poi_types = models.JSONField(default=list, blank=True)
    poi_search_radius_meters = models.IntegerField(default=1600)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'context_options'

    def __str__(self):
        return f"Context Options for {self.property_list.title}"

    def get_enabled_services(self):
        """Returns list of enabled service names"""
        services = []
        if self.enable_crime:
            services.append('crime')
        if self.enable_schools:
            services.append('schools')
        if self.enable_broadband:
            services.append('broadband')
        if self.enable_mobile:
            services.append('mobile')
        if self.enable_poi:
            services.append('poi')
        return services


class Property(models.Model):
    """Individual property with state tracking through stages"""

    STATE_CHOICES = [
        ('NEW', 'New'),
        ('STAGE2_IN_PROGRESS', 'Stage 2 In Progress'),
        ('STAGE2_COMPLETE', 'Stage 2 Complete'),
        ('STAGE3_IN_PROGRESS', 'Stage 3 In Progress'),
        ('STAGE3_COMPLETE', 'Stage 3 Complete'),
    ]

    property_list = models.ForeignKey(PropertyList, on_delete=models.CASCADE, related_name='properties')
    state = FSMField(default='NEW', choices=STATE_CHOICES)

    # Basic property details
    title = models.CharField(max_length=255)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=10)

    # Location coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Property characteristics
    price = models.DecimalField(max_digits=12, decimal_places=2)
    bedrooms = models.IntegerField()
    bathrooms = models.IntegerField()
    square_area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    garden = models.BooleanField(default=False)
    parking = models.BooleanField(default=False)
    furnished_status = models.CharField(max_length=50, blank=True)

    # Additional details
    council_tax_band = models.CharField(max_length=1, blank=True)
    epc_rating = models.CharField(max_length=1, blank=True)
    lease_length = models.IntegerField(null=True, blank=True)
    floor_level = models.IntegerField(null=True, blank=True)
    child_suitable = models.BooleanField(default=False)
    completion_date = models.DateField(null=True, blank=True)

    # External references
    external_id = models.CharField(max_length=100, blank=True)
    external_url = models.URLField(max_length=500, blank=True)

    # Deduplication
    normalized_address = models.CharField(max_length=500, blank=True)
    uprn = models.CharField(max_length=50, blank=True)

    # Stage 3 results
    overall_rating = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    rating_breakdown = models.JSONField(null=True, blank=True)
    disqualified = models.BooleanField(default=False)
    disqualification_reason = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'properties'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} - {self.postcode}"

    @transition(field=state, source='NEW', target='STAGE2_IN_PROGRESS')
    def run_stage2(self):
        """User triggers Stage 2 context retrieval"""
        pass

    @transition(field=state, source='STAGE2_IN_PROGRESS', target='STAGE2_COMPLETE')
    def complete_stage2(self):
        """All context services complete/failed"""
        pass

    @transition(field=state, source=['STAGE2_COMPLETE', 'STAGE3_COMPLETE'], target='STAGE3_IN_PROGRESS')
    def run_stage3(self):
        """User triggers Stage 3 rating calculation"""
        pass

    @transition(field=state, source='STAGE3_IN_PROGRESS', target='STAGE3_COMPLETE')
    def complete_stage3(self):
        """Rating calculation complete"""
        pass

    @transition(field=state, source=['STAGE2_COMPLETE', 'STAGE3_IN_PROGRESS', 'STAGE3_COMPLETE'], target='STAGE2_IN_PROGRESS')
    def rerun_services(self):
        """Rerun context services (field change or manual retry)"""
        pass

    def check_all_services_complete(self):
        """Check if all context services have completed or failed"""
        if not hasattr(self.property_list, 'context_options'):
            return False

        enabled_services = self.property_list.context_options.get_enabled_services()
        if not enabled_services:
            return True

        completed = self.context_data.filter(status__in=['COMPLETE', 'FAILED']).count()
        return completed == len(enabled_services)

class SavedLocation(models.Model):
    """User's saved locations for distance calculations"""

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='saved_locations')
    name = models.CharField(max_length=255)
    address = models.CharField(max_length=500)
    latitude = models.DecimalField(max_digits=9, decimal_places=6)
    longitude = models.DecimalField(max_digits=9, decimal_places=6)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'saved_locations'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.user.username})"


class StateTransitionLog(models.Model):
    """Audit trail for state transitions"""

    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    from_state = models.CharField(max_length=30)
    to_state = models.CharField(max_length=30)
    transition_name = models.CharField(max_length=50)

    triggered_by = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL)
    triggered_by_system = models.BooleanField(default=False)

    timestamp = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = 'state_transition_logs'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.from_state} → {self.to_state} ({self.timestamp})"
