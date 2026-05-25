"""
Interface for context retrieval services (Stage 2)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any
from property.utils.geolocation import validate_postcode, reverse_geocode, geocode_postcode, GeocodingError
import logging

logger = logging.getLogger(__name__)


class IContextService(ABC):
    """
    Base interface for context data retrieval services.

    Each service implements data fetching, caching strategy, and validation.
    Services run as independent Celery tasks with retry logic.
    """

    @abstractmethod
    def fetch_data(self, property_obj, **kwargs) -> Dict[str, Any]:
        """
        Fetch context data for a property from external API.

        Args:
            property_obj: Property model instance
            **kwargs: Service-specific parameters (e.g., poi_types for POI service)

        Returns:
            Dict containing service-specific data

        Raises:
            ValueError: If property data is invalid/incomplete
            requests.exceptions.RequestException: If API call fails
        """
        pass

    @abstractmethod
    def get_cache_key(self, property_obj) -> str:
        """
        Generate cache key for this property.

        Different services use different cache key strategies:
        - Crime: postcode sector (broader area)
        - Broadband: UPRN (property-specific)
        - Schools: full postcode
        - POI: rounded coordinates (grid-based)

        Args:
            property_obj: Property model instance

        Returns:
            String cache key
        """
        pass

    @abstractmethod
    def get_cache_ttl(self) -> int:
        """
        Get cache time-to-live in seconds.

        Different services have different data volatility:
        - Crime: 30 days (2592000 seconds)
        - Schools: 90 days (7776000 seconds)
        - Broadband: 7 days (604800 seconds)
        - POI: 30 days (2592000 seconds)

        Returns:
            TTL in seconds
        """
        pass

    @abstractmethod
    def validate_property_data(self, property_obj) -> bool:
        """
        Check if property has required fields for this service.

        Args:
            property_obj: Property model instance

        Returns:
            True if property data is valid for this service

        Raises:
            ValueError: If property data is invalid (with specific message)
        """
        pass

    @abstractmethod
    def get_service_name(self) -> str:
        """
        Get the service identifier.

        Returns:
            Service name ('crime', 'schools', 'broadband', etc.)
        """
        pass

    def ensure_postcode(self, property_obj) -> bool:
        # Check if postcode exists and is valid
        if property_obj.postcode and validate_postcode(property_obj.postcode):
            return True

        # If no valid postcode, try to populate from coordinates
        if property_obj.latitude and property_obj.longitude:
            try:
                postcode = reverse_geocode(
                    float(property_obj.latitude),
                    float(property_obj.longitude)
                )
                if postcode:
                    property_obj.postcode = postcode
                    property_obj.save(update_fields=['postcode'])
                    logger.info(f"Populated postcode {postcode} for property {property_obj.uuid}")
                    return True
                else:
                    logger.warning(f"No postcode found for coordinates {property_obj.latitude}, {property_obj.longitude}")
                    return False
            except GeocodingError as e:
                logger.error(f"Failed to reverse geocode property {property_obj.uuid}: {e}")
                return False

        logger.warning(f"Property {property_obj.uuid} has no valid postcode or coordinates")
        return False

    def ensure_coordinates(self, property_obj) -> bool:
        # Check if coordinates already exist
        if property_obj.latitude and property_obj.longitude:
            return True

        # If no coordinates, try to populate from postcode
        if property_obj.postcode:
            try:
                latitude, longitude = geocode_postcode(property_obj.postcode)
                if latitude and longitude:
                    property_obj.latitude = latitude
                    property_obj.longitude = longitude
                    property_obj.save(update_fields=['latitude', 'longitude'])
                    logger.info(f"Populated coordinates ({latitude}, {longitude}) for property {property_obj.uuid}")
                    return True
                else:
                    logger.warning(f"No coordinates found for postcode {property_obj.postcode}")
                    return False
            except Exception as e:
                logger.error(f"Failed to geocode property {property_obj.uuid}: {e}")
                return False

        logger.warning(f"Property {property_obj.uuid} has no coordinates or postcode")
        return False
