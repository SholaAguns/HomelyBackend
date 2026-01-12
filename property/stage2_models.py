from django.db import models
from stage1_models import PropertyList, Property, ContextOptions

class ContextData(models.Model):
    """Stores context service results and execution state"""

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('COMPLETE', 'Complete'),
        ('FAILED', 'Failed'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='context_data')
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
