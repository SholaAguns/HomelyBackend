"""
Interface for property creation services
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional


class IPropertyCreationService(ABC):
    """
    Base interface for property creation services.

    Services can implement either:
    1. Single property extraction (required)
    2. Bulk search scraping (optional)
    """

    @abstractmethod
    def can_handle(self, input_data: str) -> bool:
        """
        Determine if this service can handle the given input.

        Args:
            input_data: The input string (URL or text)
            input_type: Type of input ('url' or 'text')

        Returns:
            bool: True if this service can process the input
        """
        pass

    @abstractmethod
    def extract_property_data(self, input_data: str, input_type: str) -> Dict[str, Any]:
        """
        Extract property data from the input source.

        Args:
            input_data: The input string (URL or text)

        Returns:
            Dict containing property data matching Property model fields
            (unsaved Property model structure)

        Raises:
            ValueError: If extraction fails or data is invalid
        """
        pass

    # Optional methods for bulk search services

    def scrape_properties_by_search(
        self,
        search_criteria: dict,
        max_properties: int = 100,
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        """
        Optional: Scrape multiple properties based on search criteria.

        Not all services need to implement this. Only services that support
        bulk search scraping (like Rightmove) should implement this method.

        Args:
            search_criteria: Dict with service-specific search parameters
            max_properties: Maximum number of properties to scrape
            progress_callback: Optional callback(created, total) for progress updates

        Returns:
            List of property data dicts

        Raises:
            NotImplementedError: If service doesn't support bulk search
            ValueError: If search fails
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} does not support bulk search scraping"
        )
