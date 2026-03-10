from django.db import models


class BroadbandCoverage(models.Model):
    """
    Stores broadband coverage data from Ofcom Connected Nations dataset.

    Data source: Ofcom Connected Nations 2024-07 (Output Area level)
    Update frequency: Annual
    Granularity: Output Area (~125 households avg)
    """

    # Geographic identifiers
    oa_code = models.CharField(max_length=20, db_index=True, help_text="ONS Output Area code")
    laua_code = models.CharField(max_length=20, db_index=True, blank=True, help_text="Local Authority code")
    laua_name = models.CharField(max_length=100, blank=True, help_text="Local Authority name")

    # Download speeds by tier (Mbit/s)
    avg_download_under_10 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_download_10_to_30 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_download_30_to_100 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_download_100_to_300 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_download_300_to_900 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_download_over_900 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Upload speeds by tier (Mbit/s)
    avg_upload_under_10 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_upload_10_to_30 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_upload_30_to_100 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_upload_100_to_300 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_upload_300_to_900 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    avg_upload_over_900 = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    # Usage and availability
    avg_monthly_usage_gb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Average monthly data usage (GB) per connection")
    avg_monthly_usage_full_fibre_gb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True, help_text="Average monthly data usage (GB) per full-fibre connection")
    full_fibre_takeup_pct_of_coverage = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Full-fibre take-up (% of full-fibre coverage)")
    full_fibre_takeup_pct_of_all = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, help_text="Full-fibre take-up (% of all premises)")

    # Metadata
    data_date = models.DateField(help_text="Date of source dataset (YYYY-MM-01)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'broadband_coverage'
        unique_together = ('oa_code', 'data_date')
        indexes = [
            models.Index(fields=['oa_code', 'data_date']),
            models.Index(fields=['laua_code', 'data_date']),
        ]
        ordering = ['-data_date', 'oa_code']

    def __str__(self):
        return f"Broadband {self.oa_code} ({self.data_date})"

    def get_weighted_download_speed(self):
        """Calculate weighted average download speed across all tiers"""
        speeds = [
            (self.avg_download_under_10 or 0, 5),      # midpoint 5
            (self.avg_download_10_to_30 or 0, 20),     # midpoint 20
            (self.avg_download_30_to_100 or 0, 65),    # midpoint 65
            (self.avg_download_100_to_300 or 0, 200),  # midpoint 200
            (self.avg_download_300_to_900 or 0, 600),  # midpoint 600
            (self.avg_download_over_900 or 0, 1000),   # assume 1000
        ]
        total = sum(actual or midpoint for actual, midpoint in speeds)
        return total / len(speeds) if total > 0 else None

    def get_weighted_upload_speed(self):
        """Calculate weighted average upload speed across all tiers"""
        speeds = [
            (self.avg_upload_under_10 or 0, 5),
            (self.avg_upload_10_to_30 or 0, 20),
            (self.avg_upload_30_to_100 or 0, 65),
            (self.avg_upload_100_to_300 or 0, 200),
            (self.avg_upload_300_to_900 or 0, 600),
            (self.avg_upload_over_900 or 0, 1000),
        ]
        total = sum(actual or midpoint for actual, midpoint in speeds)
        return total / len(speeds) if total > 0 else None


class MobileCoverage(models.Model):
    """
    Stores mobile coverage data from Ofcom Connected Nations dataset.

    Data source: Ofcom Connected Nations 2024-09 (Local Authority level)
    Update frequency: Annual
    Granularity: Local Authority

    Coverage fields format: {technology}_{location}_{indoor/outdoor}_{0-4}
    where 0-4 represents number of networks with coverage
    """

    # Geographic identifiers
    laua_code = models.CharField(max_length=20, db_index=True, help_text="Local Authority code")
    laua_name = models.CharField(max_length=100, blank=True, help_text="Local Authority name")

    # Premise and area counts
    premise_count = models.IntegerField(null=True, blank=True, help_text="Number of premises")
    pixel_count = models.IntegerField(null=True, blank=True, help_text="Number of pixels (geographic coverage)")

    # 2G Coverage (% premises by number of networks)
    twog_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_indoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_indoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_indoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_indoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    twog_premises_indoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 3G Coverage
    threeg_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_indoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_indoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_indoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_indoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    threeg_premises_indoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 4G Coverage (most important)
    fourg_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_indoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_indoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_indoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_indoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fourg_premises_indoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 5G Coverage (high confidence)
    fiveg_high_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_high_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_high_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_high_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_high_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # 5G Coverage (very high confidence)
    fiveg_very_high_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_very_high_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_very_high_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_very_high_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    fiveg_very_high_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Voice and Data aggregate metrics
    voice_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_indoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_indoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_indoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_indoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    voice_premises_indoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    data_premises_outdoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_outdoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_outdoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_outdoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_outdoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_indoor_0 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_indoor_1 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_indoor_2 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_indoor_3 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    data_premises_indoor_4 = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Metadata
    data_date = models.DateField(help_text="Date of source dataset (YYYY-MM-01)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'mobile_coverage'
        unique_together = ('laua_code', 'data_date')
        indexes = [
            models.Index(fields=['laua_code', 'data_date']),
        ]
        ordering = ['-data_date', 'laua_code']

    def __str__(self):
        return f"Mobile {self.laua_name or self.laua_code} ({self.data_date})"

    def get_4g_coverage_score(self):
        """Calculate composite 4G coverage score (0-100)"""
        # Weight: outdoor all networks 40%, indoor all networks 30%, outdoor 3+ 20%, indoor 3+ 10%
        score = (
            float(self.fourg_premises_outdoor_4 or 0) * 0.4 +
            float(self.fourg_premises_indoor_4 or 0) * 0.3 +
            float(self.fourg_premises_outdoor_3 or 0) * 0.2 +
            float(self.fourg_premises_indoor_3 or 0) * 0.1
        )
        return round(score, 2)

    def get_5g_coverage_score(self):
        """Calculate composite 5G coverage score (0-100)"""
        # Weight: very high confidence all networks 50%, high confidence all networks 30%, very high 3+ 20%
        score = (
            float(self.fiveg_very_high_premises_outdoor_4 or 0) * 0.5 +
            float(self.fiveg_high_premises_outdoor_4 or 0) * 0.3 +
            float(self.fiveg_very_high_premises_outdoor_3 or 0) * 0.2
        )
        return round(score, 2)

    def get_overall_coverage_score(self):
        """Calculate overall mobile coverage score prioritizing 4G"""
        # 4G is most important (70%), 5G is nice to have (20%), voice reliability (10%)
        score = (
            self.get_4g_coverage_score() * 0.7 +
            self.get_5g_coverage_score() * 0.2 +
            float(self.voice_premises_indoor_4 or 0) * 0.1
        )
        return round(score, 2)
