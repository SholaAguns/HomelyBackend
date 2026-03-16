"""
POI (Places of Interest) service using Google Maps API
"""
import logging
from typing import Dict, Any, List
from django.core.cache import cache
from django.conf import settings
from .interface import IContextService
from .googlemaps_service import GoogleMapsService
from property.models import PlaceOfInterest

logger = logging.getLogger(__name__)


class POIService(IContextService):
    """
    Retrieves Places of Interest from Google Maps API.

    Features:
    - User-configurable POI types (from ContextOptions.poi_types)
    - Returns top N closest places for each type (configurable via POI_RESULTS_LIMIT)
    - Includes distance (straight, driving, walking) and time
    - Grid-based caching (30 days) by rounded coordinates
    - Stores results in PlaceOfInterest model

    API: Google Maps (Nearby Search + Place Details + Directions)
    Cost: ~$1.70 per property (15 types, no cache)
    Cache: 30 days by rounded coordinates (3 decimal places)
    """

    CACHE_TTL = 86400 * 30  # 30 days

    def __init__(self):
        """Initialize with Google Maps service"""
        self.geo_service = GoogleMapsService()

    def get_service_name(self) -> str:
        return 'poi'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has latitude and longitude"""
        if not property_obj.latitude or not property_obj.longitude:
            raise ValueError(
                "Property must have latitude/longitude for POI data"
            )
        return True

    def get_cache_key(self, property_obj) -> str:
        """
        Generate grid-based cache key.

        Rounds coordinates to 3 decimal places (~111m precision)
        to share cache across nearby properties.

        Format: poi:{place_type}:{lat_rounded}:{lon_rounded}
        Example: poi:school:51.501:-0.142
        """
        lat_rounded = round(float(property_obj.latitude), 3)
        lon_rounded = round(float(property_obj.longitude), 3)
        return f"poi:{lat_rounded}:{lon_rounded}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        """
        Fetch POI data for a property.

        Args:
            property_obj: Property instance
            **kwargs:
                poi_types: List of POI types to search (e.g., ['school', 'hospital'])
                          If None/empty, returns empty result
                radius: Search radius in meters (default: 1600)

        Process:
        1. For each poi_type:
           - Check cache (grid-based key)
           - If not cached, search Google Maps API
           - Store top 3 in PlaceOfInterest model
           - Cache results
        2. Return formatted data

        Returns:
            Dict with POI data grouped by type
        """
        self.validate_property_data(property_obj)

        # Extract parameters from kwargs
        poi_types = kwargs.get('poi_types', [])
        radius = kwargs.get('radius', 1600)

        if not poi_types:
            logger.info(f"No POI types enabled for property {property_obj.uuid}")
            return {
                'poi_types': {},
                'search_radius_meters': radius,
                'total_pois_found': 0,
                'types_searched': []
            }

        logger.info(
            f"Fetching POI data for property {property_obj.uuid}: "
            f"{len(poi_types)} types, radius={radius}m"
        )

        # Fetch data for each POI type
        all_pois = {}
        for place_type in poi_types:
            try:
                places = self._search_poi_type(
                    property_obj, place_type, radius
                )
                if places:
                    all_pois[place_type] = places
                    logger.info(
                        f"Found {len(places)} {place_type}(s) "
                        f"for property {property_obj.uuid}"
                    )
            except Exception as e:
                logger.error(
                    f"Failed to fetch {place_type} for property "
                    f"{property_obj.uuid}: {e}"
                )
                # Continue with other types (partial success)
                continue

        # Format response
        return self._format_response(
            all_pois, poi_types, radius
        )


    def _search_poi_type(
        self,
        property_obj,
        place_type: str,
        radius: int
    ) -> List[Dict]:
        """
        Search for POIs of a specific type.

        Checks cache first, then calls Google Maps API if needed.

        Args:
            property_obj: Property instance
            place_type: Type of place ('school', 'hospital', etc.)
            radius: Search radius in meters

        Returns:
            List of place dicts (up to POI_RESULTS_LIMIT)
        """
        # Check cache (per-type cache key)
        cache_key = self._get_type_cache_key(property_obj, place_type)
        cached_data = cache.get(cache_key)

        if cached_data:
            logger.debug(f"Cache hit for {cache_key}")
            # Return cached data (already formatted)
            return cached_data

        logger.debug(f"Cache miss for {cache_key}, calling API")

        # Search Google Maps API
        places = self.geo_service.search_nearby_places(
            lat=float(property_obj.latitude),
            lon=float(property_obj.longitude),
            place_type=place_type,
            radius=radius,
            limit=settings.POI_RESULTS_LIMIT
        )

        if not places:
            logger.info(f"No {place_type}s found near property {property_obj.uuid}")
            return []

        # Store in database
        self._store_poi_data(property_obj, place_type, places)

        # Format for response
        formatted_places = [
            self._format_place(place) for place in places
        ]

        # Cache results (30 days)
        cache.set(cache_key, formatted_places, self.CACHE_TTL)
        logger.debug(f"Cached {len(formatted_places)} {place_type}(s)")

        return formatted_places

    def _get_type_cache_key(self, property_obj, place_type: str) -> str:
        """
        Generate cache key for a specific POI type.

        Format: poi:{place_type}:{lat_rounded}:{lon_rounded}
        """
        lat_rounded = round(float(property_obj.latitude), 3)
        lon_rounded = round(float(property_obj.longitude), 3)
        return f"poi:{place_type}:{lat_rounded}:{lon_rounded}"

    def _store_poi_data(
        self,
        property_obj,
        place_type: str,
        places: List[Dict]
    ):
        """
        Store POI data in PlaceOfInterest model.

        Uses get_or_create to avoid duplicates.

        Args:
            property_obj: Property instance
            place_type: Type of place
            places: List of place dicts from GoogleMapsService
        """
        for place in places:
            try:
                poi, created = PlaceOfInterest.objects.get_or_create(
                    property=property_obj,
                    place_id=place['place_id'],
                    place_type=place_type,
                    defaults={
                        'name': place['name'],
                        'address': place.get('vicinity', ''),
                        'latitude': place['geometry']['location']['lat'],
                        'longitude': place['geometry']['location']['lng'],
                        'website_url': place.get('website') or '',
                        'phone_number': place.get('phone_number') or '',
                        'google_maps_url': place['gmaps_url'],
                        'straight_distance_km': place['straight_dist'],
                        'driving_distance_km': place.get('driving_dist'),
                        'driving_time_min': place.get('driving_time'),
                        'walking_distance_km': place.get('walking_dist'),
                        'walking_time_min': place.get('walking_time'),
                    }
                )

                if created:
                    logger.debug(
                        f"Created POI: {place['name']} ({place_type}) "
                        f"for property {property_obj.uuid}"
                    )
                else:
                    logger.debug(
                        f"POI already exists: {place['name']} ({place_type})"
                    )

            except Exception as e:
                logger.error(f"Failed to store POI {place.get('name')}: {e}")
                # Continue with other places
                continue

    def _format_place(self, place: Dict) -> Dict:
        """
        Format place data for API response.

        Args:
            place: Place dict from GoogleMapsService

        Returns:
            Formatted place dict
        """
        return {
            'place_id': place['place_id'],
            'name': place['name'],
            'address': place.get('vicinity', ''),
            'latitude': place['geometry']['location']['lat'],
            'longitude': place['geometry']['location']['lng'],
            'straight_distance_km': round(place['straight_dist'], 2),
            'walking_distance_km': (
                round(place['walking_dist'], 2)
                if place.get('walking_dist') else None
            ),
            'walking_time_min': (
                round(place['walking_time'], 1)
                if place.get('walking_time') else None
            ),
            'driving_distance_km': (
                round(place['driving_dist'], 2)
                if place.get('driving_dist') else None
            ),
            'driving_time_min': (
                round(place['driving_time'], 1)
                if place.get('driving_time') else None
            ),
            'website_url': place.get('website'),
            'phone_number': place.get('phone_number'),
            'google_maps_url': place['gmaps_url'],
        }

    def _format_response(
        self,
        all_pois: Dict[str, List[Dict]],
        types_searched: List[str],
        radius: int
    ) -> Dict[str, Any]:
        """
        Format final response data for ContextData.data field.

        Args:
            all_pois: Dict mapping place_type to list of places
            types_searched: List of POI types searched
            radius: Search radius used

        Returns:
            Formatted response dict
        """
        total_pois = sum(len(places) for places in all_pois.values())

        return {
            'poi_types': all_pois,
            'search_radius_meters': radius,
            'total_pois_found': total_pois,
            'types_searched': types_searched,
        }
