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

        return response.json()

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

    def _parse_api_response(self, api_data: list, postcode: str) -> Dict[str, Any]:
        """
        Parse Ofcom API response into standard format.

        API Response Format:
        [{
            "PostCode": "SW1A1AA",
            "Availability": [{
                "UPRN": 12345,
                "AddressShortDescription": "10 DOWNING STREET",
                "PostCode": "SW1A1AA",
                "EEVoiceOutdoor": 4,
                "EEVoiceIndoor": 4,
                "EEDataOutdoor": 4,
                "EEDataIndoor": 3,
                ... (similar for H3, TF, VO providers)
            }]
        }]

        Returns:
            Standardized format with coverage scores
        """
        if not api_data or not isinstance(api_data, list):
            raise ValueError("Invalid API response: expected array")

        if not api_data or 'Availability' not in api_data[0]:
            raise ValueError("Invalid API response: missing Availability data")

        availability_list = api_data[0]['Availability']
        if not availability_list:
            raise ValueError(f"No mobile coverage data for postcode {postcode}")

        # Aggregate scores for different categories
        voice_outdoor = self._aggregate_provider_scores(availability_list, 'VoiceOutdoor')
        voice_indoor = self._aggregate_provider_scores(availability_list, 'VoiceIndoor')
        data_outdoor = self._aggregate_provider_scores(availability_list, 'DataOutdoor')
        data_indoor = self._aggregate_provider_scores(availability_list, 'DataIndoor')

        # Calculate composite scores
        overall_score = (
            voice_outdoor['average'] * 0.2 +
            voice_indoor['average'] * 0.2 +
            data_outdoor['average'] * 0.3 +
            data_indoor['average'] * 0.3
        )

        return {
            'postcode': postcode,

            # Composite scores
            'scores': {
                'overall_coverage': round(overall_score, 2),
                'voice_coverage': round((voice_outdoor['average'] + voice_indoor['average']) / 2, 2),
                'data_coverage': round((data_outdoor['average'] + data_indoor['average']) / 2, 2),
            },

            # Voice coverage by provider
            'voice_coverage': {
                'outdoor': voice_outdoor,
                'indoor': voice_indoor,
            },

            # Data coverage by provider
            'data_coverage': {
                'outdoor': data_outdoor,
                'indoor': data_indoor,
            },

            # Network provider breakdown
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
        """
        Fetch mobile coverage data from Ofcom API with fallback to dataset.

        Process:
        1. Validate property has postcode
        2. Try API call with primary key
        3. If primary fails, try secondary key
        4. If both API keys fail, fallback to dataset service
        5. Return formatted data

        Returns:
            Dict with mobile coverage metrics and metadata
        """
        self.validate_property_data(property_obj)

        postcode = property_obj.postcode

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
