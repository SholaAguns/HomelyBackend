"""
School model for storing GIAS data
"""
from django.db import models


class School(models.Model):
    """
    School data from Get Information about Schools (GIAS).

    Ofsted ratings retrieved on-demand, not stored here.
    """

    # Primary key
    urn = models.CharField(
        max_length=10,
        unique=True,
        db_index=True,
        help_text="Unique Reference Number"
    )

    # Basic info
    name = models.CharField(max_length=255)
    establishment_number = models.CharField(max_length=10, blank=True)
    establishment_status = models.CharField(max_length=50, blank=True)

    # Location
    postcode = models.CharField(max_length=10, db_index=True)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    address_line_1 = models.CharField(max_length=255, blank=True)
    address_line_2 = models.CharField(max_length=255, blank=True)
    locality = models.CharField(max_length=100, blank=True)
    town = models.CharField(max_length=100, blank=True)
    county = models.CharField(max_length=100, blank=True)

    # School characteristics
    phase = models.CharField(
        max_length=50,
        blank=True,
        db_index=True,
        help_text="Primary, Secondary, Special, etc."
    )
    type_of_establishment = models.CharField(max_length=100, blank=True)
    type_of_establishment_code = models.CharField(max_length=10, blank=True)

    # Capacity and pupils
    pupil_count = models.IntegerField(null=True, blank=True)
    school_capacity = models.IntegerField(null=True, blank=True)

    # Age range
    statutory_low_age = models.IntegerField(null=True, blank=True)
    statutory_high_age = models.IntegerField(null=True, blank=True)

    # Demographics
    gender = models.CharField(
        max_length=20,
        blank=True,
        help_text="Mixed, Boys, Girls"
    )
    religious_character = models.CharField(max_length=100, blank=True)
    admissions_policy = models.CharField(max_length=100, blank=True)

    # Contact
    website = models.URLField(max_length=500, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    # Additional identifiers
    uprn = models.CharField(max_length=50, blank=True, help_text="Unique Property Reference Number")

    # Source tracking
    data_source_date = models.DateField(null=True, blank=True, help_text="Date of GIAS CSV")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'schools'
        ordering = ['name']
        indexes = [
            models.Index(fields=['postcode']),
            models.Index(fields=['urn']),
            models.Index(fields=['phase']),
            models.Index(fields=['establishment_status']),
            models.Index(fields=['latitude', 'longitude']),
        ]

    def __str__(self):
        return f"{self.name} ({self.urn})"

    @property
    def is_open(self):
        """Check if school is currently open"""
        return self.establishment_status and 'open' in self.establishment_status.lower()

    @property
    def ofsted_url(self):
        """Generate Ofsted report URL"""
        return f"https://reports.ofsted.gov.uk/provider/21/{self.urn}"
