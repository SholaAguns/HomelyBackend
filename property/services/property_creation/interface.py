"""
Interface for property creation services
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple


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

    def create_property(self, input_data: str, input_type: str, property_list) -> Tuple[Any, bool]:
        """
        Extract property data and create Property model with images.

        Args:
            input_data: The input string (URL or text)
            input_type: Type of input ('url' or 'text')
            property_list: PropertyList instance to add property to

        Returns:
            Tuple of (Property instance, created: bool)
            created is True if new property, False if existing property was updated

        Raises:
            ValueError: If extraction or creation fails
        """
        # Default implementation - can be overridden by services
        from property.models import Property, PropertyImage
        from decimal import Decimal
        import re

        # Extract property data
        property_data = self.extract_property_data(input_data, input_type)

        # Extract images before mapping
        images_data = property_data.pop('images', [])

        # Map extracted data to Property model fields
        property_fields = self._map_extracted_to_property(property_data)

        # Check if property exists globally by external_id
        property_obj = None
        created = False

        if property_fields.get('external_id'):
            existing = Property.objects.filter(
                external_id=property_fields['external_id']
            ).first()

            if existing:
                # Add to current list if not already there
                if not existing.property_lists.filter(uuid=property_list.uuid).exists():
                    existing.property_lists.add(property_list)

                # Update property fields
                for field, value in property_fields.items():
                    if field not in ['uuid', 'created_at']:
                        setattr(existing, field, value)
                existing.save()
                property_obj = existing

                # Update images
                if images_data:
                    property_obj.images.all().delete()
                    for idx, image_data in enumerate(images_data):
                        PropertyImage.objects.create(
                            property=property_obj,
                            source_url=image_data.get('source_url') or image_data.get('srcUrl') or '',
                            url=image_data.get('url') or '',
                            caption=image_data.get('caption') or '',
                            order=idx
                        )

                return property_obj, False

        # Create new property
        property_obj = Property.objects.create(**property_fields)
        property_obj.property_lists.add(property_list)

        # Create images
        if images_data:
            for idx, image_data in enumerate(images_data):
                PropertyImage.objects.create(
                    property=property_obj,
                    source_url=image_data.get('source_url', image_data.get('srcUrl', '')),
                    url=image_data.get('url', ''),
                    caption=image_data.get('caption', ''),
                    order=idx
                )

        return property_obj, True

    def parse_single_property_html(self, html: str) -> Dict[str, Any]:
        """
        Parse raw HTML of a single property detail page and return extracted data.
        Default implementation raises NotImplementedError; override in services that support it.
        """
        raise NotImplementedError(f"{self.__class__.__name__} does not support HTML parsing")

    def _map_extracted_to_property(self, property_data: dict) -> dict:
        """
        Map extracted property data to Property model fields.

        Args:
            property_data: Raw extracted data from service

        Returns:
            Dict with Property model field names and values
        """
        from decimal import Decimal
        import re

        # Handle postcode extraction from address if not present
        postcode = property_data.get('postcode', '')
        if not postcode and property_data.get('address'):
            postcode_match = re.search(
                r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}',
                property_data['address']
            )
            if postcode_match:
                postcode = postcode_match.group(0)

        if not postcode:
            postcode = ''

        return {
            'external_id': property_data.get('external_id', ''),
            'external_url': property_data.get('external_url', property_data.get('link', '')),
            'title': property_data.get('title', property_data.get('address', 'Untitled')),
            'address_line_1': property_data.get('address', property_data.get('address_line_1', '')),
            'address_line_2': property_data.get('address_line_2', ''),
            'city': property_data.get('city', ''),
            'postcode': postcode,
            'latitude': property_data.get('latitude'),
            'longitude': property_data.get('longitude'),
            'price': Decimal(str(property_data.get('price', 0))),
            'bedrooms': property_data.get('bedrooms', 0),
            'bathrooms': property_data.get('bathrooms', 0),
            'garden': property_data.get('garden', False),
            'parking': property_data.get('parking', False),
            'furnished_status': property_data.get('furnished_status', ''),
            'square_area': property_data.get('square_area'),
        }

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
