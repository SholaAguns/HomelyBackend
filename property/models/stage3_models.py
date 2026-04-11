from django.db import models
from django.contrib.auth.models import User
import uuid
from .stage1_models import Property

class RatingCriteria(models.Model):
    """Defines a set of criteria for rating properties"""

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rating_criteria')
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rating_criteria'
        verbose_name_plural = 'Rating criteria'
        ordering = ['-created_at']
        unique_together = [['owner', 'name']]

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def uses_service(self, service_name):
        """Check if any criteria use this context service"""
        return self.criteria.filter(source='context', field_name=service_name).exists()


class Criterion(models.Model):
    """Individual criterion within rating criteria"""

    SOURCE_CHOICES = [
        ('property', 'Property Field'),
        ('context', 'Context Report Data'),
    ]


    rating_criteria = models.ForeignKey(RatingCriteria, on_delete=models.CASCADE, related_name='criteria')
    name = models.CharField(max_length=255)

    # Source configuration
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    field_name = models.CharField(max_length=100, blank=True)

    saved_location_uuid = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True, null=True, blank=True)
    poi_category = models.CharField(max_length=100, blank=True, null=True)

    # Enabled state
    enabled = models.BooleanField(default=True)

    # Weight and dealbreaker
    weight = models.DecimalField(max_digits=3, decimal_places=2, default=1.0)
    is_dealbreaker = models.BooleanField(default=False)
    dealbreaker_threshold = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'criteria'
        ordering = ['rating_criteria', 'name']
        unique_together = [['saved_location_uuid', 'rating_criteria'], ['rating_criteria', 'poi_type']]

    def __str__(self):
        return f"{self.name} ({self.rating_criteria.name})"


class CriterionScore(models.Model):
    """Stores calculated scores for individual criteria"""

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='criterion_scores')
    criterion = models.ForeignKey(Criterion, on_delete=models.CASCADE, related_name='scores')

    raw_value = models.JSONField()
    normalized_score = models.DecimalField(max_digits=5, decimal_places=2)
    weighted_score = models.DecimalField(max_digits=5, decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'criterion_scores'
        unique_together = ('property', 'criterion')

    def __str__(self):
        return f"{self.criterion.name} for {self.property.title}: {self.normalized_score}"
