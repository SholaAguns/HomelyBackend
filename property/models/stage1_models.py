from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django_fsm import FSMField, transition
import uuid
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Project(models.Model):
    """Top-level container for organizing property lists and housing applications"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='projects')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    # Collaboration
    viewers = models.ManyToManyField(User, related_name='viewable_projects', blank=True)
    contributors = models.ManyToManyField(User, related_name='editable_projects', blank=True)

    # Rating criteria (moved from PropertyList)
    rating_criteria = models.ForeignKey(
        'RatingCriteria',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='projects'
    )
    rating_criteria_source = models.ForeignKey(
        'RatingCriteria',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='derived_projects',
        help_text='Source criteria if this was created via copy-on-write'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'projects'
        ordering = ['-created_at']
        unique_together = [['owner', 'title']]

    def __str__(self):
        return f"{self.title} ({self.owner.username})"


class TaskList(models.Model):
    """Project-level task list for managing tasks"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='task_lists')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'task_lists'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.title} ({self.project.title})"


class Task(models.Model):
    """Individual task within a task list"""

    STATUS_CHOICES = [
        ('TODO', 'To Do'),
        ('IN_PROGRESS', 'In Progress'),
        ('DONE', 'Done'),
        ('CANCELLED', 'Cancelled'),
    ]

    PRIORITY_CHOICES = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    task_list = models.ForeignKey('TaskList', on_delete=models.CASCADE, related_name='tasks')
    title = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='TODO')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='MEDIUM')

    # Optional associations
    assigned_to = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name='assigned_tasks')
    due_date = models.DateField(null=True, blank=True)

    # Ordering
    order = models.IntegerField(default=0, help_text="Display order within task list")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'tasks'
        ordering = ['order', '-created_at']
        indexes = [
            models.Index(fields=['task_list', 'status']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"


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

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    project = models.ForeignKey('Project', on_delete=models.CASCADE, related_name='property_lists')
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='property_lists')
    title = models.CharField(max_length=255)

    # Optional configurations
    search_criteria = models.ForeignKey(SearchCriteria, null=True, blank=True, on_delete=models.SET_NULL, related_name='property_lists')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_lists'
        ordering = ['-created_at']
        unique_together = [['project', 'title']]

    def __str__(self):
        return f"{self.title} ({self.project.title})"

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
    property_lists = models.ManyToManyField(PropertyList, related_name='properties')
    state = FSMField(default='NEW', choices=STATE_CHOICES)

    # Basic property details
    title = models.CharField(max_length=255)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True)
    postcode = models.CharField(max_length=10, blank=True)
    summary = models.TextField(blank=True, null=True)

    # Location coordinates
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    # Property characteristics
    price = models.DecimalField(max_digits=12, decimal_places=2)
    price_frequency = models.CharField(max_length=30, blank=True, null=True)
    currency_code = models.CharField(max_length=3, blank=True, null=True)
    bedrooms = models.IntegerField(blank=True, null=True)
    bathrooms = models.IntegerField(blank=True, null=True)
    square_area = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    garden = models.BooleanField(default=False)
    parking = models.BooleanField(default=False)
    furnished_status = models.CharField(max_length=50, blank=True)
    property_type = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)

    # Additional details
    council_tax_band = models.CharField(max_length=1, blank=True)
    epc_rating = models.CharField(max_length=1, blank=True)
    lease_length = models.IntegerField(null=True, blank=True)
    floor_level = models.IntegerField(null=True, blank=True)
    child_suitable = models.BooleanField(default=False)
    let_available_date = models.DateField(null=True, blank=True)
    first_visible_date = models.DateField(null=True, blank=True)
    added_or_reduced = models.CharField(max_length=100, blank=True)
    display_size = models.CharField(max_length=100, blank=True)
    listing_update_reason = models.CharField(max_length=100, blank=True)
    listing_update_date = models.DateField(null=True, blank=True)

    # External references
    external_id = models.CharField(max_length=100, blank=True)
    external_url = models.URLField(max_length=500, blank=True)

    # Deduplication
    normalized_address = models.CharField(max_length=500, blank=True, db_index=True)
    uprn = models.CharField(max_length=50, blank=True, db_index=True)

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

    @transition(field=state, source=['NEW', 'STAGE2_COMPLETE'], target='STAGE2_IN_PROGRESS')
    def run_stage2(self):
        """User triggers Stage 2 context retrieval"""
        # Clear existing stage2 data if re-running
        self.context_data.all().delete()
        self.places_of_interest.all().delete()

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
        # Get enabled services from project
        enabled_services = set()
        for prop_list in self.property_lists.all():
            project = prop_list.project
            if hasattr(project, 'context_options'):
                enabled_services.update(project.context_options.get_enabled_services())
                break  # All lists in same project share context_options

        if not enabled_services:
            return True

        completed = self.context_data.filter(status__in=['COMPLETE', 'FAILED']).count()
        return completed == len(enabled_services)


class PropertyFavorite(models.Model):
    """User's favorited properties"""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='favorited_properties')
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='favorited_by')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'property_favorites'
        unique_together = [['user', 'property']]
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', 'created_at']),
        ]

    def __str__(self):
        return f"{self.user.username} → {self.property.title}"

class KeyFeature(models.Model):
    property = models.ForeignKey(
        Property,
        on_delete=models.CASCADE,
        related_name='key_features'
    )

    order = models.IntegerField(default=0, help_text="Display order (0 = primary)")
    description = models.CharField(max_length=255, blank=True, null=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'property_key_features'
        ordering = ['order', 'created_at']
        indexes = [
            models.Index(fields=['property', 'order'])
        ]

    def __str__(self):
        return f"{self.property.title} - Feature {self.order}"

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
    postcode = models.CharField(max_length=10)
    address_line_1 = models.CharField(max_length=255)
    address_line_2 = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

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


class ProjectInvitation(models.Model):
    """Tracks share invitations sent to users (existing or not yet registered)"""

    ROLE_CHOICES = [
        ('viewer', 'Viewer'),
        ('contributor', 'Contributor'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('revoked', 'Revoked'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name='invitations')
    invited_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_invitations')
    invited_email = models.EmailField(db_index=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    token_hash = models.CharField(max_length=64, unique=True, db_index=True)
    accepted_by = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='accepted_invitations'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'project_invitations'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['project', 'status']),
            models.Index(fields=['invited_email', 'status']),
        ]

    def __str__(self):
        return f"{self.invited_email} → {self.project.title} ({self.status})"


class AppNotification(models.Model):
    """In-app notifications for users — extensible to any event type"""

    NOTIFICATION_TYPE_CHOICES = [
        ('invite_received', 'Invite Received'),
        ('invite_accepted', 'Invite Accepted'),
        ('invite_declined', 'Invite Declined'),
        ('member_removed', 'Member Removed'),
    ]

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    actor = models.ForeignKey(
        User, null=True, blank=True,
        on_delete=models.SET_NULL,
        related_name='triggered_notifications'
    )
    notification_type = models.CharField(max_length=50, choices=NOTIFICATION_TYPE_CHOICES)
    title = models.CharField(max_length=255)
    message = models.TextField()
    related_object_uuid = models.UUIDField(null=True, blank=True)
    related_object_type = models.CharField(max_length=50, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'app_notifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['recipient', 'is_read', 'created_at']),
        ]

    def __str__(self):
        return f"{self.notification_type} → {self.recipient.username}"
