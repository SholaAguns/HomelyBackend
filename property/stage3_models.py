from django.db import models
from django.contrib.auth.models import User
from stage1_models import Property

class RatingCriteria(models.Model):
    """Defines a set of criteria for rating properties"""

    name = models.CharField(max_length=255)
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='rating_criteria')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'rating_criteria'
        verbose_name_plural = 'Rating criteria'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} ({self.owner.username})"

    def uses_service(self, service_name):
        """Check if any criteria use this context service"""
        return self.criteria.filter(source='context', service_name=service_name).exists()


class Criterion(models.Model):
    """Individual criterion within rating criteria"""

    SOURCE_CHOICES = [
        ('property', 'Property Field'),
        ('context', 'Context Data'),
        ('calculated', 'Calculated Value'),
    ]

    STRATEGY_CHOICES = [
        ('min_max', 'Min-Max Normalization'),
        ('inverted', 'Inverted Min-Max'),
        ('ordinal', 'Ordinal Mapping'),
        ('boolean', 'Boolean'),
        ('threshold', 'Threshold-Based'),
    ]

    rating_criteria = models.ForeignKey(RatingCriteria, on_delete=models.CASCADE, related_name='criteria')
    name = models.CharField(max_length=255)

    # Source configuration
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    field_name = models.CharField(max_length=100, blank=True)
    service_name = models.CharField(max_length=50, blank=True)
    data_path = models.CharField(max_length=255, blank=True)

    # Scoring configuration
    scoring_strategy = models.CharField(max_length=50, choices=STRATEGY_CHOICES)
    ordinal_mapping = models.JSONField(null=True, blank=True)
    thresholds = models.JSONField(null=True, blank=True)
    boolean_true_is_better = models.BooleanField(default=True)

    # Weight and dealbreaker
    weight = models.DecimalField(max_digits=3, decimal_places=1, default=1.0)
    is_dealbreaker = models.BooleanField(default=False)
    dealbreaker_threshold = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'criteria'
        ordering = ['rating_criteria', 'name']

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
