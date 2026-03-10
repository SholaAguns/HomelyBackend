"""
Geocoding utilities for postcode to geographic code mapping
"""
import requests
from django.core.cache import cache
from typing import Optional, Dict


class GeocodingError(Exception):
    """Raised when geocoding fails"""
    pass


def postcode_to_oa(postcode: str) -> Optional[str]:
    """
    Convert UK postcode to Output Area (OA) code using Postcodes.io API

    Args:
        postcode: UK postcode (e.g., "SW1A 1AA")

    Returns:
        OA code (e.g., "E00000001") or None if not found

    Raises:
        GeocodingError: If API call fails
    """
    # Clean and normalize postcode
    clean_postcode = postcode.upper().replace(' ', '')

    # Check cache first (cache indefinitely - OA codes rarely change)
    cache_key = f'postcode_oa:{clean_postcode}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != 'NOT_FOUND' else None

    try:
        # Call Postcodes.io API
        url = f'https://api.postcodes.io/postcodes/{clean_postcode}'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 200 and 'result' in data:
                result = data['result']
                oa_code = result.get('codes', {}).get('output_area')

                # Cache result (None cached as 'NOT_FOUND' string)
                cache.set(cache_key, oa_code if oa_code else 'NOT_FOUND', timeout=None)
                return oa_code
        elif response.status_code == 404:
            # Postcode not found - cache as NOT_FOUND
            cache.set(cache_key, 'NOT_FOUND', timeout=None)
            return None
        else:
            raise GeocodingError(f'Postcodes.io API returned status {response.status_code}')

    except requests.RequestException as e:
        raise GeocodingError(f'Failed to call Postcodes.io API: {str(e)}')

    return None


def postcode_to_laua(postcode: str) -> Optional[str]:
    """
    Convert UK postcode to Local Authority (LAUA) code using Postcodes.io API

    Args:
        postcode: UK postcode (e.g., "SW1A 1AA")

    Returns:
        LAUA code (e.g., "E09000033") or None if not found

    Raises:
        GeocodingError: If API call fails
    """
    # Clean and normalize postcode
    clean_postcode = postcode.upper().replace(' ', '')

    # Check cache first
    cache_key = f'postcode_laua:{clean_postcode}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != 'NOT_FOUND' else None

    try:
        # Call Postcodes.io API
        url = f'https://api.postcodes.io/postcodes/{clean_postcode}'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 200 and 'result' in data:
                result = data['result']
                # Try admin_district code first, fallback to admin_ward
                laua_code = result.get('codes', {}).get('admin_district')

                # Cache result
                cache.set(cache_key, laua_code if laua_code else 'NOT_FOUND', timeout=None)
                return laua_code
        elif response.status_code == 404:
            # Postcode not found
            cache.set(cache_key, 'NOT_FOUND', timeout=None)
            return None
        else:
            raise GeocodingError(f'Postcodes.io API returned status {response.status_code}')

    except requests.RequestException as e:
        raise GeocodingError(f'Failed to call Postcodes.io API: {str(e)}')

    return None


def postcode_to_geo_info(postcode: str) -> Optional[Dict]:
    """
    Get full geographic information for a postcode

    Args:
        postcode: UK postcode (e.g., "SW1A 1AA")

    Returns:
        Dict with keys: oa_code, laua_code, laua_name, latitude, longitude
        or None if postcode not found

    Raises:
        GeocodingError: If API call fails
    """
    # Clean and normalize postcode
    clean_postcode = postcode.upper().replace(' ', '')

    # Check cache first
    cache_key = f'postcode_geo_full:{clean_postcode}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != 'NOT_FOUND' else None

    try:
        # Call Postcodes.io API
        url = f'https://api.postcodes.io/postcodes/{clean_postcode}'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 200 and 'result' in data:
                result = data['result']
                codes = result.get('codes', {})

                geo_info = {
                    'oa_code': codes.get('output_area'),
                    'laua_code': codes.get('admin_district'),
                    'laua_name': result.get('admin_district'),
                    'latitude': result.get('latitude'),
                    'longitude': result.get('longitude'),
                    'postcode': result.get('postcode'),  # Formatted postcode
                }

                # Cache result
                cache.set(cache_key, geo_info, timeout=None)
                return geo_info
        elif response.status_code == 404:
            # Postcode not found
            cache.set(cache_key, 'NOT_FOUND', timeout=None)
            return None
        else:
            raise GeocodingError(f'Postcodes.io API returned status {response.status_code}')

    except requests.RequestException as e:
        raise GeocodingError(f'Failed to call Postcodes.io API: {str(e)}')

    return None
