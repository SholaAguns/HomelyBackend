"""
Place of Interest (POI) model for storing Google Maps places data
"""
from django.db import models
import uuid


class PlaceOfInterest(models.Model):
    """
    Places of Interest from Google Maps (schools, hospitals, parks, etc.)

    Stores data from Google Maps Places API (Nearby Search + Place Details + Directions).
    One property can have multiple POIs of different types.
    """

    # Primary key
    uuid = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        primary_key=True
    )

    # Foreign keys
    property = models.ForeignKey(
        'Property',
        on_delete=models.CASCADE,
        related_name='places_of_interest'
    )

    # Google Maps identifiers
    place_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Google Place ID (unique identifier)"
    )

    place_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Type of place (school, hospital, park, etc.)"
    )

    # Basic info
    name = models.CharField(max_length=255)
    address = models.TextField()

    # Location
    latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        db_index=True
    )
    longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        db_index=True
    )

    # Contact details (from Place Details API)
    website_url = models.URLField(max_length=500, blank=True)
    phone_number = models.CharField(max_length=50, blank=True)

    # Google Maps link
    google_maps_url = models.URLField(
        max_length=1000,
        help_text="Shareable Google Maps URL"
    )

    # Distance calculations
    straight_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Straight-line distance from property"
    )

    driving_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Driving distance from property"
    )

    driving_time_min = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Driving time in minutes"
    )

    walking_distance_km = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Walking distance from property"
    )

    walking_time_min = models.DecimalField(
        max_digits=6,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Walking time in minutes"
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'places_of_interest'
        ordering = ['place_type', 'straight_distance_km']
        unique_together = [['property', 'place_id', 'place_type']]
        indexes = [
            models.Index(fields=['place_id']),
            models.Index(fields=['place_type']),
            models.Index(fields=['property', 'place_type']),
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.name} ({self.place_type}) - {self.straight_distance_km}km"

    def has_driving_info(self):
        """Check if driving distance/time data is available"""
        return self.driving_distance_km is not None and self.driving_time_min is not None

    def has_walking_info(self):
        """Check if walking distance/time data is available"""
        return self.walking_distance_km is not None and self.walking_time_min is not None
