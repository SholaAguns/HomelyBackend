"""
Broadband coverage service using Ofcom Connected Nations API
"""
import logging
import requests
from typing import Dict, Any
from django.conf import settings
from .interface import IContextService
from .broadband_dataset_service import BroadbandDatasetService

logger = logging.getLogger(__name__)


class BroadbandApiService(IContextService):
    """
    Retrieves broadband coverage data from Ofcom Connected Nations API.

    API: https://api-proxy.ofcom.org.uk/broadband/coverage/{PostCode}
    Auth: Primary/Secondary API Keys (subscription-based)
    Fallback: BroadbandDatasetService (local dataset)
    Cache: 30 days (API data is current, but broadband doesn't change often)
    """

    BASE_URL = 'https://api-proxy.ofcom.org.uk/broadband/coverage'
    CACHE_TTL = 86400 * 30  # 30 days

    def __init__(self):
        self.fallback_service = BroadbandDatasetService()
        self.primary_key = getattr(settings, 'OFCOM_BROADBAND_API_KEY_PRIMARY', None)
        self.secondary_key = getattr(settings, 'OFCOM_BROADBAND_API_KEY_SECONDARY', None)

    def get_service_name(self) -> str:
        return 'broadband'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has required postcode"""
        if not property_obj.postcode:
            raise ValueError("Property must have postcode for broadband data lookup")
        return True

    def get_cache_key(self, property_obj) -> str:
        """Cache by postcode (API returns per-postcode data)"""
        return f"broadband_api:{property_obj.postcode}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def _call_api(self, postcode: str, api_key: str) -> Dict[str, Any]:
        """
        Call Ofcom API with given API key.

        Args:
            postcode: UK postcode (spaces removed)
            api_key: API subscription key

        Returns:
            API response data

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
        logger.info(f"Calling Ofcom Broadband API: {url}")

        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()

        api_data = response.json()

        # Debug logging to see actual response structure
        #logger.debug(f"Broadband API Response Type: {type(api_data)}")
        #logger.debug(f"Broadband API Response: {api_data}")

        return api_data

    def _parse_api_response(self, api_data: Dict[str, Any], postcode: str) -> Dict[str, Any]:
        """
        Parse Ofcom API response into standard format.

        API Response Format:
        {
            "PostCode": "SW1A1AA",
            "Availability": [{
                "UPRN": 12345,
                "AddressShortDescription": "10 DOWNING STREET",
                "PostCode": "SW1A1AA",
                "MaxBbPredictedDown": 10.0,
                "MaxBbPredictedUp": 1.0,
                "MaxSfbbPredictedDown": 80.0,
                "MaxSfbbPredictedUp": 20.0,
                "MaxUfbbPredictedDown": 1000.0,
                "MaxUfbbPredictedUp": 220.0,
                "MaxPredictedDown": 1000.0,
                "MaxPredictedUp": 220.0
            }]
        }

        Returns:
            Standardized format matching dataset service
        """
        if not api_data or 'Availability' not in api_data:
            raise ValueError("Invalid API response: missing Availability data")

        availability_list = api_data['Availability']
        if not availability_list:
            raise ValueError(f"No broadband availability data for postcode {postcode}")

        # Aggregate max speeds across all addresses in postcode
        max_download = 0.0
        max_upload = 0.0
        max_bb_down = 0.0
        max_bb_up = 0.0
        max_sfbb_down = 0.0
        max_sfbb_up = 0.0
        max_ufbb_down = 0.0
        max_ufbb_up = 0.0

        for address in availability_list:
            max_download = max(max_download, address.get('MaxPredictedDown', 0) or 0)
            max_upload = max(max_upload, address.get('MaxPredictedUp', 0) or 0)
            max_bb_down = max(max_bb_down, address.get('MaxBbPredictedDown', 0) or 0)
            max_bb_up = max(max_bb_up, address.get('MaxBbPredictedUp', 0) or 0)
            max_sfbb_down = max(max_sfbb_down, address.get('MaxSfbbPredictedDown', 0) or 0)
            max_sfbb_up = max(max_sfbb_up, address.get('MaxSfbbPredictedUp', 0) or 0)
            max_ufbb_down = max(max_ufbb_down, address.get('MaxUfbbPredictedDown', 0) or 0)
            max_ufbb_up = max(max_ufbb_up, address.get('MaxUfbbPredictedUp', 0) or 0)

        # Map API speeds to our tier structure
        # Bb = Basic (<30 Mbps), Sfbb = Superfast (30-300 Mbps), Ufbb = Ultrafast (>=300 Mbps)

        # Estimate full fibre availability (API doesn't provide take-up data)
        # Ultrafast (>=300 Mbps) is typically full fibre
        full_fibre_data = None
        if max_ufbb_down >= 300:
            # Estimate 100% availability since API returned ultrafast for this postcode
            # Note: take_up_pct is unknown from API, set to 0
            full_fibre_data = {
                'availability_pct': 100.0,
                'take_up_pct': 0.0,  # Unknown from API
            }

        return {
            'postcode': postcode,
            'max_download_mbps': float(max_download),
            'max_upload_mbps': float(max_upload),

            # Full fibre availability (estimated from ultrafast presence)
            'full_fibre': full_fibre_data,

            # Metadata
            'data_source': 'Ofcom Connected Nations API',
            'granularity': 'Postcode (Address-level aggregated)',
            'address_count': len(availability_list),
        }

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:

        self.ensure_postcode(property_obj)
        self.validate_property_data(property_obj)

        postcode = property_obj.postcode

        # Try API first (if keys are configured)
        if self.primary_key or self.secondary_key:
            # Try primary key
            if self.primary_key:
                try:
                    api_data = self._call_api(postcode, self.primary_key)
                    result = self._parse_api_response(api_data, postcode)
                    logger.info(f"Broadband data retrieved via API (primary) for {postcode}")
                    return result
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Postcode {postcode} not found in Ofcom API")
                    else:
                        logger.warning(f"Primary API key failed for {postcode}: {e}")
                except Exception as e:
                    logger.warning(f"Primary API call failed for {postcode}: {e}")

            # Try secondary key
            if self.secondary_key:
                try:
                    api_data = self._call_api(postcode, self.secondary_key)
                    result = self._parse_api_response(api_data, postcode)
                    logger.info(f"Broadband data retrieved via API (secondary) for {postcode}")
                    return result
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code == 404:
                        logger.warning(f"Postcode {postcode} not found in Ofcom API (secondary)")
                    else:
                        logger.warning(f"Secondary API key failed for {postcode}: {e}")
                except Exception as e:
                    logger.warning(f"Secondary API call failed for {postcode}: {e}")

        # Fallback to dataset service
        logger.info(f"Falling back to dataset service for broadband data: {postcode}")
        return self.fallback_service.fetch_data(property_obj, **kwargs)
