"""
Interface for geo-location services (Google Maps, OpenStreetMap, etc.)
"""
from abc import ABC, abstractmethod
from typing import List, Dict, Tuple, Optional


class IGeoService(ABC):
    """
    Base interface for geographic/mapping services.

    Used by POI service to search for nearby places and calculate routes.
    Implementations: GoogleMapsService, OpenStreetMapService (future)
    """

    @abstractmethod
    def search_nearby_places(
        self,
        lat: float,
        lon: float,
        place_type: str,
        radius: int,
        limit: int = 3
    ) -> List[Dict]:
        """
        Search for nearby places of a specific type.

        Args:
            lat: Property latitude
            lon: Property longitude
            place_type: Type of place ('school', 'hospital', etc.)
            radius: Search radius in meters
            limit: Maximum number of results to return

        Returns:
            List of place dicts with keys:
                - place_id: Unique identifier
                - name: Place name
                - vicinity/address: Address
                - geometry: {'location': {'lat': float, 'lng': float}}
                - straight_dist: Straight-line distance in km
                - website: Website URL (optional)
                - phone_number: Phone number (optional)
                - gmaps_url: Google Maps link

        Raises:
            ValueError: If place_type is unknown
            requests.exceptions.RequestException: If API call fails
        """
        pass

    @abstractmethod
    def get_route_info(
        self,
        orig_lat: float,
        orig_lon: float,
        dest_lat: float,
        dest_lon: float,
        profile: str
    ) -> Tuple[Optional[float], Optional[float]]:
        """
        Calculate route distance and time between two points.

        Args:
            orig_lat: Origin latitude
            orig_lon: Origin longitude
            dest_lat: Destination latitude
            dest_lon: Destination longitude
            profile: Travel mode ('driving' or 'walking')

        Returns:
            Tuple of (time_minutes, distance_km)
            Returns (None, None) if route not found

        Raises:
            requests.exceptions.RequestException: If API call fails
        """
        pass
