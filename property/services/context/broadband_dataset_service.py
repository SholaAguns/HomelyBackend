"""
Broadband coverage service using Ofcom Connected Nations static dataset
"""
import logging
from typing import Dict, Any
from .interface import IContextService

logger = logging.getLogger(__name__)


class BroadbandDatasetService(IContextService):
    """
    Retrieves broadband coverage data from local Ofcom dataset.

    Data source: BroadbandCoverage table (imported from Ofcom CSV)
    Cache: 90 days (Ofcom data updated annually)
    Query: Postcode → OA code → database lookup
    """

    CACHE_TTL = 86400 * 90  # 90 days (Ofcom updates annually)

    def get_service_name(self) -> str:
        return 'broadband'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required postcode"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for broadband data lookup")
        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode (data is at OA level)"""
        return f"broadband:{property_obj.postcode}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj) -> Dict[str, Any]:
        """
        Fetch broadband coverage data for property's Output Area.

        Process:
        1. Extract postcode from property
        2. Map postcode → OA code using Postcodes.io
        3. Query BroadbandCoverage table for latest data
        4. Return formatted data

        Returns:
            Dict with broadband metrics and metadata
        """
        from property.models import BroadbandCoverage
        from property.utils.geocoding import postcode_to_oa, GeocodingError

        self.validate_property_data(property_obj)

        postcode = property_obj.postcode

        # Step 1: Map postcode to OA code
        try:
            oa_code = postcode_to_oa(postcode)
        except GeocodingError as e:
            logger.error(f"Geocoding failed for postcode {postcode}: {e}")
            raise ValueError(f"Failed to map postcode to Output Area: {e}")

        if not oa_code:
            raise ValueError(f"No Output Area found for postcode {postcode}")

        # Step 2: Query database for most recent data for this OA
        coverage = BroadbandCoverage.objects.filter(
            oa_code=oa_code
        ).order_by('-data_date').first()

        if not coverage:
            raise ValueError(f"No broadband data found for Output Area {oa_code}")

        # Step 3: Format response
        return {
            'postcode': postcode,
            'oa_code': coverage.oa_code,
            'laua_code': coverage.laua_code,
            'laua_name': coverage.laua_name,

            # Maximum available speeds
            'max_download_mbps': float(coverage.get_max_download_speed() or 0),
            'max_upload_mbps': float(coverage.get_max_upload_speed() or 0),

            # Speed tiers (download)
            'download_speeds': {
                'under_10_mbps': float(coverage.avg_download_under_10 or 0),
                '10_to_30_mbps': float(coverage.avg_download_10_to_30 or 0),
                '30_to_100_mbps': float(coverage.avg_download_30_to_100 or 0),
                '100_to_300_mbps': float(coverage.avg_download_100_to_300 or 0),
                '300_to_900_mbps': float(coverage.avg_download_300_to_900 or 0),
                'over_900_mbps': float(coverage.avg_download_over_900 or 0),
            },

            # Speed tiers (upload)
            'upload_speeds': {
                'under_10_mbps': float(coverage.avg_upload_under_10 or 0),
                '10_to_30_mbps': float(coverage.avg_upload_10_to_30 or 0),
                '30_to_100_mbps': float(coverage.avg_upload_30_to_100 or 0),
                '100_to_300_mbps': float(coverage.avg_upload_100_to_300 or 0),
                '300_to_900_mbps': float(coverage.avg_upload_300_to_900 or 0),
                'over_900_mbps': float(coverage.avg_upload_over_900 or 0),
            },

            # Full fibre availability
            'full_fibre': {
                'takeup_pct_of_coverage': float(coverage.full_fibre_takeup_pct_of_coverage or 0),
                'takeup_pct_of_all_premises': float(coverage.full_fibre_takeup_pct_of_all or 0),
            },

            # Usage
            'avg_monthly_usage_gb': float(coverage.avg_monthly_usage_gb or 0),
            'avg_monthly_usage_full_fibre_gb': float(coverage.avg_monthly_usage_full_fibre_gb or 0),

            # Metadata
            'data_source': 'Ofcom Connected Nations Dataset',
            'data_date': coverage.data_date.isoformat(),
            'granularity': 'Output Area (~125 households)',
            'last_updated': coverage.updated_at.isoformat(),
        }
