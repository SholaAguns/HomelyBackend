"""
Geocoding utilities for postcode to geographic code mapping
"""
import requests
from django.core.cache import cache
from typing import Optional, Dict, Tuple
from decimal import Decimal
import logging
import math

logger = logging.getLogger(__name__)


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


def geocode_postcode(postcode: str) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    """
    Geocode a UK postcode to latitude/longitude using Postcodes.io API.

    Args:
        postcode: UK postcode (with or without space)

    Returns:
        Tuple of (latitude, longitude) or (None, None) if not found

    Example:
        >>> lat, lng = geocode_postcode('SW1A 1AA')
        >>> print(lat, lng)
        51.5010096 -0.1415870
    """
    if not postcode:
        return None, None

    # Clean postcode (remove extra spaces)
    clean_postcode = postcode.strip().replace('  ', ' ')

    try:
        url = f"https://api.postcodes.io/postcodes/{requests.utils.quote(clean_postcode)}"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()

            if data.get('status') == 200 and data.get('result'):
                result = data['result']
                latitude = result.get('latitude')
                longitude = result.get('longitude')

                if latitude and longitude:
                    logger.info(f"Geocoded {clean_postcode}: {latitude}, {longitude}")
                    return Decimal(str(latitude)), Decimal(str(longitude))

        elif response.status_code == 404:
            logger.warning(f"Postcode not found: {clean_postcode}")
            return None, None

        else:
            logger.error(f"Geocoding failed for {clean_postcode}: {response.status_code}")
            return None, None

    except requests.exceptions.RequestException as e:
        logger.error(f"Geocoding error for {clean_postcode}: {e}")
        return None, None

    except Exception as e:
        logger.error(f"Unexpected error geocoding {clean_postcode}: {e}")
        return None, None


def bulk_geocode_postcodes(postcodes: list) -> dict:
    """
    Geocode multiple postcodes in a single request.

    Postcodes.io supports bulk lookup of up to 100 postcodes.

    Args:
        postcodes: List of UK postcodes (max 100)

    Returns:
        Dict mapping postcode to (latitude, longitude) tuples

    Example:
        >>> results = bulk_geocode_postcodes(['SW1A 1AA', 'EC1A 1BB'])
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
        url = "https://api.postcodes.io/postcodes"
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


def validate_postcode(postcode: str) -> bool:
    """
    Validate a UK postcode format using Postcodes.io API.

    Args:
        postcode: UK postcode to validate

    Returns:
        True if valid format, False otherwise
    """
    if not postcode:
        return False

    clean_postcode = postcode.strip().replace('  ', ' ')

    try:
        url = f"https://api.postcodes.io/postcodes/{requests.utils.quote(clean_postcode)}/validate"
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            return data.get('result', False)

        return False

    except Exception:
        return False


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:

    # Convert decimal degrees to radians
    lat1, lon1, lat2, lon2 = map(math.radians, [float(lat1), float(lon1), float(lat2), float(lon2)])

    # Haversine formula
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a))
    r = 6371  # Radius of earth in kilometers
    return c * r


OSRM_BASE = "http://router.project-osrm.org"


def get_route_info(orig_lat, orig_lon, dest_lat, dest_lon, profile: str) -> Tuple[Optional[float], Optional[float]]:
    """
    Returns (duration_mins, distance_km) via OSRM for 'driving' or 'foot'.
    Returns (None, None) on any error so callers degrade gracefully.
    """
    coords = f"{orig_lon},{orig_lat};{dest_lon},{dest_lat}"
    url = f"{OSRM_BASE}/route/v1/{profile}/{coords}"
    try:
        resp = requests.get(url, params={'overview': 'false'}, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get('routes'):
            rt = data['routes'][0]
            return round(rt['duration'] / 60.0, 1), round(rt['distance'] / 1000.0, 2)
    except Exception as e:
        logger.warning(f"OSRM {profile} route lookup failed ({orig_lat},{orig_lon} -> {dest_lat},{dest_lon}): {e}")
    return None, None


def reverse_geocode(latitude: float, longitude: float, limit: int = 1) -> Optional[str]:
    # Cache key based on rounded coordinates (to avoid cache bloat)
    cache_key = f'reverse_geo:{round(latitude, 5)}:{round(longitude, 5)}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached if cached != 'NOT_FOUND' else None

    try:
        url = f'https://api.postcodes.io/postcodes?lon={longitude}&lat={latitude}&limit={limit}'
        response = requests.get(url, timeout=5)

        if response.status_code == 200:
            data = response.json()
            if data.get('status') == 200 and data.get('result'):
                results = data['result']
                if results and len(results) > 0:
                    postcode = results[0].get('postcode')
                    cache.set(cache_key, postcode if postcode else 'NOT_FOUND', timeout=None)
                    return postcode

            # No results found
            cache.set(cache_key, 'NOT_FOUND', timeout=None)
            return None
        else:
            raise GeocodingError(f'Postcodes.io API returned status {response.status_code}')

    except requests.RequestException as e:
        raise GeocodingError(f'Failed to call Postcodes.io API: {str(e)}')

    return None
