"""
Validate Rightmove search areas before creating PropertyLists.
"""

from typing import Tuple, List
import requests
from django.core.cache import cache


def validate_rightmove_area(area: str) -> Tuple[bool, str]:
    """
    Validate that area exists on Rightmove.

    Uses Rightmove's location autocomplete API to check if area is valid.
    Caches results for 7 days to avoid repeated API calls.

    Args:
        area: Location string (e.g., "Manchester", "SW1A 1AA")

    Returns:
        Tuple of (is_valid, error_message)
        - (True, "") if valid
        - (False, "error message") if invalid

    Examples:
        >>> validate_rightmove_area("Manchester")
        (True, "")

        >>> validate_rightmove_area("NotARealPlace12345")
        (False, "Location not found on Rightmove")
    """
    cache_key = f"rightmove_area_valid:{area.lower()}"

    # Check cache first
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    try:
        # Rightmove autocomplete API
        response = requests.get(
            "https://www.rightmove.co.uk/api/_autocomplete",
            params={
                'query': area,
                'limit': 1
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()

            # Check if any results returned
            if data.get('results') and len(data['results']) > 0:
                result = (True, "")
                cache.set(cache_key, result, timeout=60*60*24*7)  # 7 days
                return result
            else:
                result = (False, f"Location '{area}' not found on Rightmove")
                cache.set(cache_key, result, timeout=60*60*24)  # 1 day
                return result
        else:
            # API error, allow creation but warn
            return (True, "")  # Don't block on API errors

    except requests.RequestException:
        # Network error, allow creation
        return (True, "")  # Don't block on network errors


def get_area_suggestions(area: str, limit: int = 5) -> List[str]:
    """
    Get suggested areas similar to input (for typo correction).

    Args:
        area: Invalid area string
        limit: Max number of suggestions

    Returns:
        List of suggested area names

    Examples:
        >>> get_area_suggestions("Mancester")  # Typo
        ["Manchester", "Manchester City Centre", "Manchester Piccadilly"]
    """
    try:
        response = requests.get(
            "https://www.rightmove.co.uk/api/_autocomplete",
            params={
                'query': area,
                'limit': limit
            },
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            return [
                result.get('displayName', result.get('name', ''))
                for result in data.get('results', [])
            ]
    except requests.RequestException:
        pass

    return []
