from django.db import models
from .stage1_models import PropertyList, Property
import uuid


class ContextOptions(models.Model):
    """Configuration for which context services to enable for a property list"""

    property_list = models.OneToOneField(PropertyList, on_delete=models.CASCADE, related_name='context_options')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    # Service toggles
    enable_crime = models.BooleanField(default=False)
    enable_schools = models.BooleanField(default=False)
    enable_broadband = models.BooleanField(default=False)
    enable_mobile = models.BooleanField(default=False)
    enable_council_tax = models.BooleanField(default=False)

    # Schools configuration
    school_types = models.JSONField(default=list, blank=True)

    # POI configuration
    enable_poi = models.BooleanField(default=False)
    poi_types = models.JSONField(default=list, blank=True)
    poi_search_radius_meters = models.IntegerField(default=1600)

    # Saved locations configuration
    enable_saved_locations = models.BooleanField(default=False)
    saved_location_uuids = models.JSONField(default=list, blank=True)

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
        if self.enable_council_tax:
            services.append('council_tax')
        if self.enable_saved_locations:
            services.append('saved_locations')
        return services



class ContextData(models.Model):
    """Stores context service results and execution state"""

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETE', 'Complete'),
        ('FAILED', 'Failed'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='context_data')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    service_name = models.CharField(max_length=50)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')

    # Service result
    data = models.JSONField(null=True, blank=True)

    # Error tracking
    error_message = models.TextField(blank=True)
    error_type = models.CharField(max_length=50, blank=True)
    retry_count = models.IntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    last_attempt_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'context_data'
        unique_together = ('property', 'service_name')

    def __str__(self):
        return f"{self.service_name} for {self.property.title} ({self.status})"
