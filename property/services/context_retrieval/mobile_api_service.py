"""
Mobile coverage service using Ofcom Connected Nations API
"""
import logging
import requests
from typing import Dict, Any
from django.conf import settings
from .interface import IContextService
from .mobile_dataset_service import MobileDatasetService

logger = logging.getLogger(__name__)


class MobileApiService(IContextService):
    """
    Retrieves mobile coverage data from Ofcom Connected Nations API.

    API: https://api-proxy.ofcom.org.uk/mobile/coverage/{PostCode}
    Auth: Primary/Secondary API Keys (subscription-based)
    Fallback: MobileDatasetService (local dataset)
    Cache: 30 days (API data is current, but coverage doesn't change rapidly)

    Coverage ratings:
    0 = None (you should not expect coverage)
    3 = Limited (coverage may be limited)
    4 = Likely (you are likely to have coverage)
    """

    BASE_URL = 'https://api-proxy.ofcom.org.uk/mobile/coverage'
    CACHE_TTL = 86400 * 30  # 30 days

    # Network provider codes
    PROVIDERS = ['EE', 'H3', 'TF', 'VO']  # EE, Three (H3), O2 (TF), Vodafone (VO)

    def __init__(self):
        self.fallback_service = MobileDatasetService()
        self.primary_key = getattr(settings, 'OFCOM_MOBILE_API_KEY_PRIMARY', None)
        self.secondary_key = getattr(settings, 'OFCOM_MOBILE_API_KEY_SECONDARY', None)

    def get_service_name(self) -> str:
        return 'mobile'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required postcode"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for mobile coverage lookup")
        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode (API returns per-postcode data)"""
        return f"mobile_api:{property_obj.postcode}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def _call_api(self, postcode: str, api_key: str) -> Dict[str, Any]:
        """
        Call Ofcom API with given API key.

        Args:
            postcode: UK postcode (spaces removed)
            api_key: API subscription key

        Returns:
            API response data (array wrapper)

        Raises:
            requests.exceptions.RequestException: If API call fails
        """
        # Remove spaces from postcode
        postcode_clean = postcode.replace(' ', '').upper()

        headers = {
            'Ocp-Apim-Subscription-Key': api_key,
            'Accept': 'application/json',
        }

        url = f"{self.BASE_URL}/{postcode_clean}"
        logger.info(f"Calling Ofcom Mobile API: {url}")

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        api_data = response.json()

        # Debug logging to see actual response structure
        logger.debug(f"Mobile API Response Type: {type(api_data)}")
        logger.debug(f"Mobile API Response: {api_data}")

        return api_data

    def _calculate_coverage_percentage(self, rating: int) -> float:
        """
        Convert Ofcom rating (0/3/4) to percentage.

        0 = None → 0%
        3 = Limited → 50%
        4 = Likely → 100%
        """
        if rating == 4:
            return 100.0
        elif rating == 3:
            return 50.0
        else:
            return 0.0

    def _aggregate_provider_scores(self, availability_list: list, field_suffix: str) -> Dict[str, float]:
        """
        Aggregate scores across providers for a given field.

        Args:
            availability_list: List of address data from API
            field_suffix: e.g., "VoiceOutdoor", "DataIndoor"

        Returns:
            Dict with per-provider percentages and aggregates
        """
        provider_scores = {}

        for provider in self.PROVIDERS:
            field_name = f"{provider}{field_suffix}"
            scores = [
                self._calculate_coverage_percentage(addr.get(field_name, 0))
                for addr in availability_list
            ]
            provider_scores[provider.lower()] = sum(scores) / len(scores) if scores else 0.0

        # Calculate average across all providers
        all_scores = list(provider_scores.values())
        provider_scores['average'] = sum(all_scores) / len(all_scores) if all_scores else 0.0

        return provider_scores

    def _calculate_network_aggregates(self, availability_list: list, metric: str) -> Dict[str, float]:
        """
        Calculate network count aggregates from per-address provider ratings.

        Converts provider-level data (EE/H3/TF/VO with ratings 0/3/4) into
        network count buckets (0/1/2/3/4 networks coverage) to match dataset format.

        Args:
            availability_list: List of address data from API
            metric: e.g., "DataOutdoor", "DataIndoor"

        Returns:
            Dict with network count percentages: all_4_networks, three_networks, etc.
        """
        network_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}

        for address in availability_list:
            # Count how many providers have "likely" (4) coverage for this address
            providers_with_coverage = 0
            for provider in self.PROVIDERS:
                field_name = f"{provider}{metric}"
                rating = address.get(field_name, 0)
                if rating == 4:  # Only count "likely" coverage
                    providers_with_coverage += 1

            # Increment the count for this network bucket
            network_counts[providers_with_coverage] += 1

        # Convert counts to percentages
        total_addresses = len(availability_list)
        network_percentages = {
            'all_4_networks': round((network_counts[4] / total_addresses) * 100, 2) if total_addresses else 0,
            'three_networks': round((network_counts[3] / total_addresses) * 100, 2) if total_addresses else 0,
            'two_networks': round((network_counts[2] / total_addresses) * 100, 2) if total_addresses else 0,
            'one_network': round((network_counts[1] / total_addresses) * 100, 2) if total_addresses else 0,
            'no_coverage': round((network_counts[0] / total_addresses) * 100, 2) if total_addresses else 0,
        }

        return network_percentages

    def _parse_api_response(self, api_data: Dict[str, Any], postcode: str) -> Dict[str, Any]:
        if not api_data or not isinstance(api_data, dict):
            raise ValueError(f"Invalid API response: expected dict, got {type(api_data)}")

        if 'Availability' not in api_data:
            raise ValueError("Invalid API response: missing Availability data")

        availability_list = api_data['Availability']
        if not availability_list:
            raise ValueError(f"No mobile coverage data for postcode {postcode}")

        # Calculate network count aggregates (to match dataset format)
        data_outdoor_agg = self._calculate_network_aggregates(availability_list, 'DataOutdoor')
        data_indoor_agg = self._calculate_network_aggregates(availability_list, 'DataIndoor')

        # Calculate 4G coverage score (matching dataset service logic)
        # Weight: outdoor all networks 40%, indoor all networks 30%, outdoor 3+ 20%, indoor 3+ 10%
        four_g_score = (
            data_outdoor_agg['all_4_networks'] * 0.4 +
            data_indoor_agg['all_4_networks'] * 0.3 +
            data_outdoor_agg['three_networks'] * 0.2 +
            data_indoor_agg['three_networks'] * 0.1
        )

        # 5G estimation: API doesn't provide explicit 5G data
        # Use heuristic: areas with high 4G coverage likely have some 5G
        # Conservative estimate: 0 for now (can be refined)
        five_g_score = 0.0

        # Overall score: prioritize 4G (70%), 5G (20%), voice reliability (10%)
        # For voice, use data coverage as proxy (API doesn't distinguish 4G voice clearly)
        overall_score = (
            four_g_score * 0.7 +
            five_g_score * 0.2 +
            data_indoor_agg['all_4_networks'] * 0.1
        )

        # Aggregate provider scores (for optional provider breakdown)
        voice_outdoor = self._aggregate_provider_scores(availability_list, 'VoiceOutdoor')
        voice_indoor = self._aggregate_provider_scores(availability_list, 'VoiceIndoor')
        data_outdoor = self._aggregate_provider_scores(availability_list, 'DataOutdoor')
        data_indoor = self._aggregate_provider_scores(availability_list, 'DataIndoor')

        return {
            'postcode': postcode,

            # Composite scores (REQUIRED)
            'scores': {
                'four_g_coverage': round(four_g_score, 2),
                'five_g_coverage': round(five_g_score, 2),
                'overall_coverage': round(overall_score, 2),
            },

            # Network count aggregates (REQUIRED - matches dataset format)
            'four_g_coverage': {
                'outdoor': data_outdoor_agg,
                'indoor': data_indoor_agg,
            },

            # 5G coverage (OPTIONAL - not available from API, set to None)
            'five_g_coverage_high_confidence': None,

            # Network provider breakdown (OPTIONAL - API-specific detail)
            'providers': {
                'ee': {
                    'voice_outdoor': voice_outdoor.get('ee', 0),
                    'voice_indoor': voice_indoor.get('ee', 0),
                    'data_outdoor': data_outdoor.get('ee', 0),
                    'data_indoor': data_indoor.get('ee', 0),
                },
                'three': {
                    'voice_outdoor': voice_outdoor.get('h3', 0),
                    'voice_indoor': voice_indoor.get('h3', 0),
                    'data_outdoor': data_outdoor.get('h3', 0),
                    'data_indoor': data_indoor.get('h3', 0),
                },
                'o2': {
                    'voice_outdoor': voice_outdoor.get('tf', 0),
                    'voice_indoor': voice_indoor.get('tf', 0),
                    'data_outdoor': data_outdoor.get('tf', 0),
                    'data_indoor': data_indoor.get('tf', 0),
                },
                'vodafone': {
                    'voice_outdoor': voice_outdoor.get('vo', 0),
                    'voice_indoor': voice_indoor.get('vo', 0),
                    'data_outdoor': data_outdoor.get('vo', 0),
                    'data_indoor': data_indoor.get('vo', 0),
                },
            },

            # Metadata
            'data_source': 'Ofcom Connected Nations API',
            'granularity': 'Postcode (Address-level aggregated)',
            'address_count': len(availability_list),
        }

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        self.ensure_postcode(property_obj)
        self.validate_property_data(property_obj)

        postcode = property_obj.postcode.replace(" ", "")

        # Try API first (if keys are configured)
        if self.primary_key or self.secondary_key:
            # Try primary key
            if self.primary_key:
                try:
                    api_data = self._call_api(postcode, self.primary_key)
                    result = self._parse_api_response(api_data, postcode)
                    logger.info(f"Mobile data retrieved via API (primary) for {postcode}")
                    return result
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Postcode {postcode} not found in Ofcom Mobile API")
                    else:
                        logger.warning(f"Primary API key failed for {postcode}: {e}")
                except Exception as e:
                    logger.warning(f"Primary API call failed for {postcode}: {e}")

            # Try secondary key
            if self.secondary_key:
                try:
                    api_data = self._call_api(postcode, self.secondary_key)
                    result = self._parse_api_response(api_data, postcode)
                    logger.info(f"Mobile data retrieved via API (secondary) for {postcode}")
                    return result
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Postcode {postcode} not found in Ofcom Mobile API (secondary)")
                    else:
                        logger.warning(f"Secondary API key failed for {postcode}: {e}")
                except Exception as e:
                    logger.warning(f"Secondary API call failed for {postcode}: {e}")

        # Fallback to dataset service
        logger.info(f"Falling back to dataset service for mobile data: {postcode}")
        return self.fallback_service.fetch_data(property_obj, **kwargs)
