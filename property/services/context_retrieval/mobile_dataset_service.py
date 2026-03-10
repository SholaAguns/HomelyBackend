"""
Mobile coverage service using Ofcom Connected Nations static dataset
"""
import logging
from typing import Dict, Any
from .interface import IContextService

logger = logging.getLogger(__name__)


class MobileDatasetService(IContextService):
    """
    Retrieves mobile coverage data from local Ofcom dataset.

    Data source: MobileCoverage table (imported from Ofcom CSV)
    Cache: 90 days (Ofcom data updated annually)
    Query: Postcode → LAUA code → database lookup
    """

    CACHE_TTL = 86400 * 90  # 90 days (Ofcom updates annually)

    def get_service_name(self) -> str:
        return 'mobile'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required postcode"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for mobile coverage lookup")
        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode (data is at LAUA level)"""
        return f"mobile:{property_obj.postcode}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        """
        Fetch mobile coverage data for property's Local Authority.

        Process:
        1. Extract postcode from property
        2. Map postcode → LAUA code using Postcodes.io
        3. Query MobileCoverage table for latest data
        4. Return formatted data with composite scores

        Returns:
            Dict with mobile coverage metrics and scores
        """
        from property.models import MobileCoverage
        from property.utils.geocoding import postcode_to_laua, GeocodingError

        self.validate_property_data(property_obj)

        postcode = property_obj.postcode

        # Step 1: Map postcode to LAUA code
        try:
            laua_code = postcode_to_laua(postcode)
        except GeocodingError as e:
            logger.error(f"Geocoding failed for postcode {postcode}: {e}")
            raise ValueError(f"Failed to map postcode to Local Authority: {e}")

        if not laua_code:
            raise ValueError(f"No Local Authority found for postcode {postcode}")

        # Step 2: Query database for most recent data for this LAUA
        coverage = MobileCoverage.objects.filter(
            laua_code=laua_code
        ).order_by('-data_date').first()

        if not coverage:
            raise ValueError(f"No mobile coverage data found for Local Authority {laua_code}")

        # Step 3: Format response with composite scores
        return {
            'postcode': postcode,
            'laua_code': coverage.laua_code,
            'laua_name': coverage.laua_name,
            'premise_count': coverage.premise_count,

            # Composite scores (0-100)
            'scores': {
                '4g_coverage': coverage.get_4g_coverage_score(),
                '5g_coverage': coverage.get_5g_coverage_score(),
                'overall_coverage': coverage.get_overall_coverage_score(),
            },

            # 4G Coverage breakdown
            '4g_coverage': {
                'outdoor': {
                    'all_4_networks': float(coverage.fourg_premises_outdoor_4 or 0),
                    '3_networks': float(coverage.fourg_premises_outdoor_3 or 0),
                    '2_networks': float(coverage.fourg_premises_outdoor_2 or 0),
                    '1_network': float(coverage.fourg_premises_outdoor_1 or 0),
                    'no_coverage': float(coverage.fourg_premises_outdoor_0 or 0),
                },
                'indoor': {
                    'all_4_networks': float(coverage.fourg_premises_indoor_4 or 0),
                    '3_networks': float(coverage.fourg_premises_indoor_3 or 0),
                    '2_networks': float(coverage.fourg_premises_indoor_2 or 0),
                    '1_network': float(coverage.fourg_premises_indoor_1 or 0),
                    'no_coverage': float(coverage.fourg_premises_indoor_0 or 0),
                },
            },

            # 5G Coverage (high confidence)
            '5g_coverage_high_confidence': {
                'outdoor': {
                    'all_4_networks': float(coverage.fiveg_high_premises_outdoor_4 or 0),
                    '3_networks': float(coverage.fiveg_high_premises_outdoor_3 or 0),
                    '2_networks': float(coverage.fiveg_high_premises_outdoor_2 or 0),
                    '1_network': float(coverage.fiveg_high_premises_outdoor_1 or 0),
                    'no_coverage': float(coverage.fiveg_high_premises_outdoor_0 or 0),
                },
            },

            # 5G Coverage (very high confidence)
            '5g_coverage_very_high_confidence': {
                'outdoor': {
                    'all_4_networks': float(coverage.fiveg_very_high_premises_outdoor_4 or 0),
                    '3_networks': float(coverage.fiveg_very_high_premises_outdoor_3 or 0),
                    '2_networks': float(coverage.fiveg_very_high_premises_outdoor_2 or 0),
                    '1_network': float(coverage.fiveg_very_high_premises_outdoor_1 or 0),
                    'no_coverage': float(coverage.fiveg_very_high_premises_outdoor_0 or 0),
                },
            },

            # Voice coverage
            'voice_coverage': {
                'outdoor': {
                    'all_4_networks': float(coverage.voice_premises_outdoor_4 or 0),
                    '3_networks': float(coverage.voice_premises_outdoor_3 or 0),
                    '2_networks': float(coverage.voice_premises_outdoor_2 or 0),
                    '1_network': float(coverage.voice_premises_outdoor_1 or 0),
                    'no_coverage': float(coverage.voice_premises_outdoor_0 or 0),
                },
                'indoor': {
                    'all_4_networks': float(coverage.voice_premises_indoor_4 or 0),
                    '3_networks': float(coverage.voice_premises_indoor_3 or 0),
                    '2_networks': float(coverage.voice_premises_indoor_2 or 0),
                    '1_network': float(coverage.voice_premises_indoor_1 or 0),
                    'no_coverage': float(coverage.voice_premises_indoor_0 or 0),
                },
            },

            # Data coverage
            'data_coverage': {
                'outdoor': {
                    'all_4_networks': float(coverage.data_premises_outdoor_4 or 0),
                    '3_networks': float(coverage.data_premises_outdoor_3 or 0),
                    '2_networks': float(coverage.data_premises_outdoor_2 or 0),
                    '1_network': float(coverage.data_premises_outdoor_1 or 0),
                    'no_coverage': float(coverage.data_premises_outdoor_0 or 0),
                },
                'indoor': {
                    'all_4_networks': float(coverage.data_premises_indoor_4 or 0),
                    '3_networks': float(coverage.data_premises_indoor_3 or 0),
                    '2_networks': float(coverage.data_premises_indoor_2 or 0),
                    '1_network': float(coverage.data_premises_indoor_1 or 0),
                    'no_coverage': float(coverage.data_premises_indoor_0 or 0),
                },
            },

            # Metadata
            'data_source': 'Ofcom Connected Nations Dataset',
            'data_date': coverage.data_date.isoformat(),
            'granularity': 'Local Authority',
            'last_updated': coverage.updated_at.isoformat(),
        }
