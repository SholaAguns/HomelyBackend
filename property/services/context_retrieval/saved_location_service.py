"""
Saved Locations distance service
"""
import logging
from typing import Dict, Any, List
from .interface import IContextService
from property.utils.geolocation import calculate_distance, get_route_info

logger = logging.getLogger(__name__)


class SavedLocationService(IContextService):
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
        lat = round(float(property_obj.latitude), 4)
        lon = round(float(property_obj.longitude), 4)

        uuids: set = set()
        for property_list in property_obj.property_lists.all():
            project = property_list.project
            context_options = getattr(project, 'context_options', None)
            if context_options and context_options.enable_saved_locations and context_options.saved_location_uuids:
                uuids.update(context_options.saved_location_uuids)

        uuids_part = '_'.join(sorted(uuids)) if uuids else 'none'
        return f"saved_locations:{lat}:{lon}:{uuids_part}"

    def get_cache_ttl(self) -> int:
        return self.CACHE_TTL

    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        from property.models import SavedLocation
        self.ensure_coordinates(property_obj)

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
                    loc_lat = float(location.latitude)
                    loc_lon = float(location.longitude)

                    distance_km = calculate_distance(prop_lat, prop_lon, loc_lat, loc_lon)
                    driving_time, _ = get_route_info(prop_lat, prop_lon, loc_lat, loc_lon, 'driving')
                    walking_time, _ = get_route_info(prop_lat, prop_lon, loc_lat, loc_lon, 'foot')

                    distances.append({
                        'location_id': location.id,
                        'location_uuid': str(location.uuid),
                        'location_name': location.name,
                        'address': f"{location.address_line_1}, {location.postcode}",
                        'postcode': location.postcode,
                        'latitude': loc_lat,
                        'longitude': loc_lon,
                        'distance_km': round(distance_km, 2),
                        'distance_miles': round(distance_km * 0.621371, 2),
                        'driving_time_mins': driving_time,
                        'walking_time_mins': walking_time,
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
