"""
Google Maps API service implementation
"""
import requests
import logging
from urllib.parse import quote_plus
from typing import List, Dict, Tuple, Optional
from django.conf import settings
from .igeoservice import IGeoService
from property.utils.geocoding import calculate_distance

logger = logging.getLogger(__name__)


class GoogleMapsService(IGeoService):
    """
    IGeoService implementation using Google Places & Directions APIs.

    APIs used:
    - Places Nearby Search: Find places by type near location
    - Place Details: Get website, phone number
    - Directions API: Get driving/walking distance and time

    Rate limits: 100 QPS per project (default)
    Cost: See https://mapsplatform.google.com/pricing/
    """

    PLACES_NEARBY_URL = "https://maps.googleapis.com/maps/api/place/nearbysearch/json"
    PLACE_DETAILS_URL = "https://maps.googleapis.com/maps/api/place/details/json"
    DIRECTIONS_URL = "https://maps.googleapis.com/maps/api/directions/json"

    # Map our internal place_type keys to Google Place types
    # Some types map to multiple Google types for better coverage
    PLACE_TYPE_GOOGLE = {
        'school': ['school'],
        'hospital': ['hospital'],
        'park': ['park'],
        'supermarket': ['supermarket'],
        'grocery': ['grocery_or_supermarket'],
        'restaurant': ['restaurant'],
        'gym': ['gym'],
        'pharmacy': ['pharmacy'],
        'train_station': ['train_station'],
        'bus_station': ['bus_station'],
        'petrol_station': ['gas_station'],
        'mosque': ['mosque'],
        'church': ['church'],
        'temple': ['hindu_temple'],
        'library': ['library'],
        'shopping': ['shopping_mall'],
        'airport': ['airport'],
        'cafe': ['cafe'],
        'bank': ['bank'],
        'pub': ['pub'],
        'dentist': ['dentist'],
    }

    def __init__(self):
        """Initialize with API key from settings"""
        self.api_key = settings.GOOGLE_MAPS_API_KEY
        if not self.api_key:
            raise ValueError("GOOGLE_MAPS_API_KEY not configured in settings")

    def search_nearby_places(
        self,
        lat: float,
        lon: float,
        place_type: str,
        radius: int,
        limit: int = 3
    ) -> List[Dict]:
        google_types = self.PLACE_TYPE_GOOGLE.get(place_type)
        if not google_types:
            raise ValueError(f"Unknown place_type: {place_type}")

        logger.info(f"Searching for {place_type} near ({lat}, {lon})")

        seen = {}  # Deduplicate by place_id

        # Search for each Google type (e.g., both train_station and bus_station)
        for google_type in google_types:
            try:
                params = {
                    'location': f"{lat},{lon}",
                    'rankby': 'distance',  # More efficient, ignores radius
                    'type': google_type,
                    'key': self.api_key,
                }

                logger.debug(f"Calling Nearby Search API for type={google_type}")
                response = requests.get(
                    self.PLACES_NEARBY_URL,
                    params=params,
                    timeout=10
                )
                response.raise_for_status()

                results = response.json().get('results', [])
                logger.debug(f"Found {len(results)} results for {google_type}")

                for item in results:
                    pid = item['place_id']

                    # Skip if already seen (deduplication)
                    if pid in seen:
                        continue

                    # Extract location
                    lat_place = item['geometry']['location']['lat']
                    lon_place = item['geometry']['location']['lng']

                    # Calculate straight-line distance
                    dist_km = calculate_distance(
                        lat, lon, lat_place, lon_place
                    )

                    # Fetch Place Details for website and phone
                    website, phone = self._get_place_details(pid)

                    # Fetch Directions for driving and walking
                    driving_time, driving_dist = self.get_route_info(
                        lat, lon, lat_place, lon_place, 'driving'
                    )
                    walking_time, walking_dist = self.get_route_info(
                        lat, lon, lat_place, lon_place, 'walking'
                    )

                    # Build Google Maps URL
                    gmaps_url = self._build_google_maps_url(
                        item.get('name', ''), pid
                    )

                    seen[pid] = {
                        'place_id': pid,
                        'name': item.get('name', 'Unknown'),
                        'vicinity': item.get('vicinity', ''),
                        'geometry': {
                            'location': {'lat': lat_place, 'lng': lon_place}
                        },
                        'straight_dist': dist_km,
                        'website': website,
                        'phone_number': phone,
                        'driving_dist': driving_dist,
                        'driving_time': driving_time,
                        'walking_dist': walking_dist,
                        'walking_time': walking_time,
                        'gmaps_url': gmaps_url,
                    }

            except requests.exceptions.HTTPError as e:
                if e.response.status_code == 429:
                    # Rate limit exceeded
                    logger.error(f"Google Maps API rate limit exceeded")
                    raise
                elif e.response.status_code in [401, 403]:
                    # Auth error
                    logger.error(f"Google Maps API auth error: {e}")
                    raise
                else:
                    logger.error(f"Google Maps API HTTP error: {e}")
                    raise
            except requests.exceptions.RequestException as e:
                logger.error(f"Failed to search {google_type}: {e}")
                raise

        # Sort by distance and return top N
        places = sorted(seen.values(), key=lambda x: x['straight_dist'])
        return places[:limit]

    def get_route_info(
        self,
        orig_lat: float,
        orig_lon: float,
        dest_lat: float,
        dest_lon: float,
        profile: str
    ) -> Tuple[Optional[float], Optional[float]]:
        mode = 'driving' if profile == 'driving' else 'walking'

        try:
            params = {
                'origin': f"{orig_lat},{orig_lon}",
                'destination': f"{dest_lat},{dest_lon}",
                'mode': mode,
                'key': self.api_key,
            }

            logger.debug(f"Calling Directions API (mode={mode})")
            response = requests.get(
                self.DIRECTIONS_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            routes = data.get('routes', [])

            if not routes:
                logger.warning(f"No {mode} route found")
                return None, None

            leg = routes[0]['legs'][0]
            time_min = leg['duration']['value'] / 60.0  # seconds to minutes
            dist_km = leg['distance']['value'] / 1000.0  # meters to km

            return time_min, dist_km

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to get route info: {e}")
            # Return None instead of raising - route info is optional
            return None, None

    def _get_place_details(self, place_id: str) -> Tuple[Optional[str], Optional[str]]:
        try:
            params = {
                'place_id': place_id,
                'fields': 'website,formatted_phone_number',
                'key': self.api_key,
            }

            logger.debug(f"Calling Place Details API for {place_id}")
            response = requests.get(
                self.PLACE_DETAILS_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            result = response.json().get('result', {})
            website = result.get('website')
            phone = result.get('formatted_phone_number')

            return website, phone

        except requests.exceptions.RequestException as e:
            logger.warning(f"Failed to get place details for {place_id}: {e}")
            return None, None

    def _build_google_maps_url(self, name: str, place_id: str) -> str:
        return (
            f"https://www.google.com/maps/search/?api=1"
            f"&query={quote_plus(name)}"
            f"&query_place_id={place_id}"
        )
