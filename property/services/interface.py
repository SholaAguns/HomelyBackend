"""
Interface for property creation services
"""
from abc import ABC, abstractmethod
from typing import Dict, Any


class IPropertyCreationService(ABC):

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
    def extract_property_data(self, input_data: str) -> Dict[str, Any]:
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
