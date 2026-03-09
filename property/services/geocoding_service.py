"""
Geocoding service using Postcodes.io (FREE UK postcode API)
"""
import requests
import logging
from typing import Tuple, Optional
from decimal import Decimal

logger = logging.getLogger(__name__)


class PostcodesIOService:
    """
    Free UK postcode geocoding using Postcodes.io API.

    API: https://api.postcodes.io
    Rate Limit: None (unlimited)
    Coverage: UK postcodes only
    """

    BASE_URL = "https://api.postcodes.io"

    @classmethod
    def geocode_postcode(self, postcode: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
        """
        Geocode a UK postcode to latitude/longitude.

        Args:
            postcode: UK postcode (with or without space)

        Returns:
            Tuple of (latitude, longitude) or (None, None) if not found

        Example:
            >>> lat, lng = PostcodesIOService.geocode_postcode('SW1A 1AA')
            >>> print(lat, lng)
            51.5010096 -0.1415870
        """
        if not postcode:
            return None, None

        # Clean postcode (remove extra spaces)
        postcode = postcode.strip().replace('  ', ' ')

        try:
            url = f"{self.BASE_URL}/postcodes/{requests.utils.quote(postcode)}"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()

                if data.get('status') == 200 and data.get('result'):
                    result = data['result']
                    latitude = result.get('latitude')
                    longitude = result.get('longitude')

                    if latitude and longitude:
                        logger.info(f"Geocoded {postcode}: {latitude}, {longitude}")
                        return Decimal(str(latitude)), Decimal(str(longitude))

            elif response.status_code == 404:
                logger.warning(f"Postcode not found: {postcode}")
                return None, None

            else:
                logger.error(f"Geocoding failed for {postcode}: {response.status_code}")
                return None, None

        except requests.exceptions.RequestException as e:
            logger.error(f"Geocoding error for {postcode}: {e}")
            return None, None

        except Exception as e:
            logger.error(f"Unexpected error geocoding {postcode}: {e}")
            return None, None

    @classmethod
    def bulk_geocode_postcodes(cls, postcodes: list) -> dict:
        """
        Geocode multiple postcodes in a single request.

        Postcodes.io supports bulk lookup of up to 100 postcodes.

        Args:
            postcodes: List of UK postcodes (max 100)

        Returns:
            Dict mapping postcode to (latitude, longitude) tuples

        Example:
            >>> results = PostcodesIOService.bulk_geocode_postcodes(['SW1A 1AA', 'EC1A 1BB'])
            >>> results['SW1A 1AA']
            (Decimal('51.5010096'), Decimal('-0.1415870'))
        """
        if not postcodes:
            return {}

        # Limit to 100 postcodes
        postcodes = postcodes[:100]

        # Clean postcodes
        clean_postcodes = [pc.strip().replace('  ', ' ') for pc in postcodes if pc]

        results = {}

        try:
            url = f"{cls.BASE_URL}/postcodes"
            payload = {"postcodes": clean_postcodes}

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('status') == 200 and data.get('result'):
                    for item in data['result']:
                        query_postcode = item.get('query')
                        result = item.get('result')

                        if result:
                            latitude = result.get('latitude')
                            longitude = result.get('longitude')

                            if latitude and longitude:
                                results[query_postcode] = (
                                    Decimal(str(latitude)),
                                    Decimal(str(longitude))
                                )
                        else:
                            logger.warning(f"No result for postcode: {query_postcode}")
                            results[query_postcode] = (None, None)

            else:
                logger.error(f"Bulk geocoding failed: {response.status_code}")

        except requests.exceptions.RequestException as e:
            logger.error(f"Bulk geocoding error: {e}")
        except Exception as e:
            logger.error(f"Unexpected bulk geocoding error: {e}")

        return results

    @classmethod
    def validate_postcode(cls, postcode: str) -> bool:
        """
        Validate a UK postcode format.

        Args:
            postcode: UK postcode to validate

        Returns:
            True if valid format, False otherwise
        """
        if not postcode:
            return False

        postcode = postcode.strip().replace('  ', ' ')

        try:
            url = f"{cls.BASE_URL}/postcodes/{requests.utils.quote(postcode)}/validate"
            response = requests.get(url, timeout=5)

            if response.status_code == 200:
                data = response.json()
                return data.get('result', False)

            return False

        except:
            return False
