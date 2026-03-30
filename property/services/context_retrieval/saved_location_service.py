"""
Saved Locations distance service
"""
import logging
from typing import Dict, Any, List
from .interface import IContextService
from property.utils.geocoding import calculate_distance

logger = logging.getLogger(__name__)


class SavedLocationService(IContextService):
    """
    Calculates distances between property and user's saved locations.

    Features:
    - Accepts list of saved location IDs from ContextOptions
    - Calculates straight-line distance for each location
    - Returns sorted list by distance
    - No external API calls (uses local data)

    Cache: 30 days by property coordinates + location IDs
    Cost: FREE (no API calls)
    """

    CACHE_TTL = 86400 * 30  # 30 days

    def get_service_name(self) -> str:
        return 'saved_locations'

    def validate_property_data(self, property_obj) -> bool:
        """Check property has latitude and longitude"""
        if not property_obj.latitude or not property_obj.longitude:
            raise ValueError(
                "Property must have latitude/longitude for saved location distance calculations"
            )
        return True

    def get_cache_key(self, property_obj) -> str:
        """
        Generate cache key based on property coordinates.

        Format: saved_locations:{lat}:{lon}
        Note: saved_location_ids are not included in cache key as distances
        are calculated dynamically based on requested locations.
        """
        lat = round(float(property_obj.latitude), 4)
        lon = round(float(property_obj.longitude), 4)
        return f"saved_locations:{lat}:{lon}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        """
        Calculate distances to saved locations.

        Args:
            property_obj: Property instance
            **kwargs:
                saved_location_uuids: List of SavedLocation UUIDs to calculate distances for

        Returns:
            Dict with distances to each saved location, sorted by distance
        """
        from property.models import SavedLocation

        self.validate_property_data(property_obj)

        # Get saved location UUIDs from kwargs
        saved_location_uuids = kwargs.get('saved_location_uuids', [])

        if not saved_location_uuids:
            logger.info(f"No saved locations specified for property {property_obj.uuid}")
            return {
                'distances': [],
                'total_locations': 0
            }

        # Fetch saved locations by UUID
        saved_locations = SavedLocation.objects.filter(uuid__in=saved_location_uuids)

        if not saved_locations.exists():
            logger.warning(f"No saved locations found for UUIDs: {saved_location_uuids}")
            return {
                'distances': [],
                'total_locations': 0,
                'error': 'No saved locations found'
            }

        prop_lat = float(property_obj.latitude)
        prop_lon = float(property_obj.longitude)

        # Calculate distances
        distances = []
        for location in saved_locations:
            if location.latitude and location.longitude:
                try:
                    distance_km = calculate_distance(
                        prop_lat, prop_lon,
                        float(location.latitude), float(location.longitude)
                    )

                    distances.append({
                        'location_id': location.id,
                        'location_uuid': str(location.uuid),
                        'location_name': location.name,
                        'address': f"{location.address_line_1}, {location.postcode}",
                        'latitude': float(location.latitude),
                        'longitude': float(location.longitude),
                        'distance_km': round(distance_km, 2),
                        'distance_miles': round(distance_km * 0.621371, 2)
                    })
                except Exception as e:
                    logger.error(f"Failed to calculate distance for location {location.id}: {e}")
            else:
                logger.warning(f"Saved location {location.id} missing coordinates, skipping")

        # Sort by distance (closest first)
        distances.sort(key=lambda x: x['distance_km'])

        return {
            'distances': distances,
            'total_locations': len(distances),
            'closest_location': distances[0] if distances else None
        }
