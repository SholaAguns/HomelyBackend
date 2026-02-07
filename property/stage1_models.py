from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django_fsm import FSMField, transition
import uuid


class SearchCriteria(models.Model):
    """Search criteria for bulk property scraping from listing sites"""

    area = models.CharField(max_length=100)
    bedrooms_min = models.PositiveIntegerField(null=True, blank=True)
    bedrooms_max = models.PositiveIntegerField(null=True, blank=True)
    bathrooms_min = models.PositiveIntegerField(null=True, blank=True)
    bathrooms_max = models.PositiveIntegerField(null=True, blank=True)
    price_min = models.PositiveIntegerField(null=True, blank=True)
    price_max = models.PositiveIntegerField(null=True, blank=True)
    radius = models.PositiveIntegerField(null=True, blank=True, help_text="Search radius in miles")
    property_types = models.CharField(max_length=100, null=True, blank=True,
                                      help_text="Comma-separated property types")
    max_days_since_added = models.PositiveIntegerField(null=True, blank=True,
                                                        help_text="Only properties added within X days")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'search_criteria'
        verbose_name_plural = 'Search criteria'

    def __str__(self):
        return f"{self.area} - {self.bedrooms_min or 'any'}-{self.bedrooms_max or 'any'} beds"


class PropertyList(models.Model):
    """Container for a collection of properties with shared configuration"""

    STATE_CHOICES = [
        ('DRAFT', 'Draft'),
        ('ACTIVE', 'Active'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_lists')
    title = models.CharField(max_length=255)
    state = FSMField(default='DRAFT', choices=STATE_CHOICES)

    # Optional configurations
    rating_criteria = models.ForeignKey('RatingCriteria', null=True, blank=True, on_delete=models.SET_NULL, related_name='property_lists')
    rating_criteria_source = models.ForeignKey('RatingCriteria', null=True, blank=True, on_delete=models.SET_NULL, related_name='derived_lists')
    search_criteria = models.ForeignKey(SearchCriteria, null=True, blank=True, on_delete=models.SET_NULL, related_name='property_lists')

    # Collaboration
    viewers = models.ManyToManyField(User, related_name='viewable_lists', blank=True)
    contributors = models.ManyToManyField(User, related_name='editable_lists', blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_lists'
        ordering = ['-created_at']
        unique_together = [['owner', 'title']]

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


class Property(models.Model):
    """Individual property with state tracking through stages"""

    STATE_CHOICES = [
        ('NEW', 'New'),
        ('STAGE2_IN_PROGRESS', 'Stage 2 In Progress'),
        ('STAGE2_COMPLETE', 'Stage 2 Complete'),
        ('STAGE3_IN_PROGRESS', 'Stage 3 In Progress'),
        ('STAGE3_COMPLETE', 'Stage 3 Complete'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
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


class PropertyImage(models.Model):
    """Images for a property from external sources"""

    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='images'
    )

    # Image URLs (not storing files, just external URLs)
    source_url = models.URLField(max_length=1000, help_text="Original/high-res image URL")
    url = models.URLField(max_length=1000, help_text="Display/medium size image URL")

    # Metadata
    caption = models.CharField(max_length=255, blank=True, null=True)
    order = models.IntegerField(default=0, help_text="Display order (0 = primary)")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_images'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['property', 'order'])
        ]

    def __str__(self):
        return f"{self.property.title} - Image {self.order}"


class SavedLocation(models.Model):
    """User's saved locations for distance calculations"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
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


class PropertyListTask(models.Model):
    """Tracks async tasks for property list operations (bulk scraping, etc)"""

    STATUS_CHOICES = [
        ('QUEUED', 'Queued'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETED', 'Completed'),
        ('FAILED', 'Failed'),
        ('CANCELLED', 'Cancelled'),
    ]

    TASK_TYPE_CHOICES = [
        ('SCRAPE_SEARCH', 'Scrape from Search'),
        ('BULK_STAGE2', 'Bulk Stage 2'),
        ('BULK_STAGE3', 'Bulk Stage 3'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    property_list = models.ForeignKey(PropertyList, on_delete=models.CASCADE, related_name='tasks')
    task_type = models.CharField(max_length=50, choices=TASK_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='QUEUED')

    # Celery task tracking
    celery_task_id = models.CharField(max_length=255, null=True, blank=True)

    # Progress tracking
    total_items = models.IntegerField(default=0)
    completed_items = models.IntegerField(default=0)
    failed_items = models.IntegerField(default=0)

    # Error tracking
    errors = models.JSONField(default=list, blank=True)
    error_message = models.TextField(blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'property_list_tasks'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property_list', 'status']),
            models.Index(fields=['celery_task_id']),
        ]

    def __str__(self):
        return f"{self.get_task_type_display()} - {self.get_status_display()} ({self.property_list.title})"

    @property
    def progress_percentage(self):
        """Calculate progress percentage"""
        if self.total_items == 0:
            return 0
        return int((self.completed_items / self.total_items) * 100)

    def add_error(self, error_msg, context=None):
        """Add an error to the errors list"""
        error_entry = {
            'message': error_msg,
            'timestamp': timezone.now().isoformat(),
        }
        if context:
            error_entry['context'] = context

        if not isinstance(self.errors, list):
            self.errors = []

        self.errors.append(error_entry)
        self.save(update_fields=['errors', 'updated_at'])
