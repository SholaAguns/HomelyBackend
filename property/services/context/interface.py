"""
Interface for context retrieval services (Stage 2)
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class IContextService(ABC):
    """
    Base interface for context data retrieval services.

    Each service implements data fetching, caching strategy, and validation.
    Services run as independent Celery tasks with retry logic.
    """

    @abstractmethod
    def fetch_data(self, property_obj) -> Dict[str, Any]:
        """
        Fetch context data for a property from external API.

        Args:
            property_obj: Property model instance

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
