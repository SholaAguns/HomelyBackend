"""
Rightmove property listing scraper service
"""
import re
from typing import Dict, Any
from decimal import Decimal
from property.services.interface import IPropertyCreationService


class RightmoveService(IPropertyCreationService):

    RIGHTMOVE_DOMAINS = [
        'rightmove.co.uk',
        'www.rightmove.co.uk'
    ]

    def can_handle(self, input_data: str) -> bool:
        return any(domain in input_data.lower() for domain in self.RIGHTMOVE_DOMAINS)

    def extract_property_data(self, input_data: str) -> Dict[str, Any]:
        try:
            # Import here to avoid dependency issues if packages not installed
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ValueError(
                f"Required packages not installed: {e}. "
                "Install with: pip install requests beautifulsoup4"
            )

        try:
            # Fetch the page
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(input_data, headers=headers, timeout=10)
            response.raise_for_status()

            # Parse HTML
            soup = BeautifulSoup(response.content, 'html.parser')

            # Extract data using Rightmove's HTML structure
            property_data = {
                'external_url': input_data,
            }

            # Extract title
            title_elem = soup.find('h1', {'itemprop': 'name'}) or soup.find('h1')
            if title_elem:
                property_data['title'] = title_elem.get_text(strip=True)

            # Extract price
            price_elem = soup.find('span', {'class': 'property-header-price'})
            if not price_elem:
                price_elem = soup.find(string=re.compile(r'£[\d,]+'))
            if price_elem:
                price_text = price_elem.get_text(strip=True) if hasattr(price_elem, 'get_text') else str(price_elem)
                price_match = re.search(r'£([\d,]+)', price_text)
                if price_match:
                    property_data['price'] = Decimal(price_match.group(1).replace(',', ''))

            # Extract address
            address_elem = soup.find('address', {'itemprop': 'address'}) or soup.find('address')
            if address_elem:
                address_text = address_elem.get_text(strip=True)
                # Split address into components (simple heuristic)
                address_parts = [p.strip() for p in address_text.split(',')]
                if len(address_parts) > 0:
                    property_data['address_line_1'] = address_parts[0]
                if len(address_parts) > 1:
                    property_data['city'] = address_parts[-2] if len(address_parts) > 2 else address_parts[-1]
                # Extract postcode (UK format)
                postcode_match = re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}', address_text)
                if postcode_match:
                    property_data['postcode'] = postcode_match.group(0)

            # Extract bedrooms
            bedrooms_elem = soup.find(string=re.compile(r'\d+\s*bedroom', re.IGNORECASE))
            if bedrooms_elem:
                bedrooms_match = re.search(r'(\d+)\s*bedroom', str(bedrooms_elem), re.IGNORECASE)
                if bedrooms_match:
                    property_data['bedrooms'] = int(bedrooms_match.group(1))

            # Extract bathrooms
            bathrooms_elem = soup.find(string=re.compile(r'\d+\s*bathroom', re.IGNORECASE))
            if bathrooms_elem:
                bathrooms_match = re.search(r'(\d+)\s*bathroom', str(bathrooms_elem), re.IGNORECASE)
                if bathrooms_match:
                    property_data['bathrooms'] = int(bathrooms_match.group(1))

            # Extract property type and other details from key features
            features_section = soup.find('div', {'class': re.compile(r'key.*features', re.IGNORECASE)})
            if features_section:
                features_text = features_section.get_text(strip=True).lower()

                # Check for garden
                if 'garden' in features_text:
                    property_data['garden'] = True

                # Check for parking
                if any(word in features_text for word in ['parking', 'garage', 'drive']):
                    property_data['parking'] = True

                # Extract furnished status
                if 'furnished' in features_text:
                    if 'unfurnished' in features_text:
                        property_data['furnished_status'] = 'Unfurnished'
                    elif 'part furnished' in features_text or 'part-furnished' in features_text:
                        property_data['furnished_status'] = 'Part Furnished'
                    else:
                        property_data['furnished_status'] = 'Furnished'

            # Extract property ID from URL
            property_id_match = re.search(r'/properties/(\d+)', input_data)
            if property_id_match:
                property_data['external_id'] = property_id_match.group(1)

            # Validate minimum required fields
            if 'title' not in property_data:
                raise ValueError("Could not extract property title from Rightmove listing")

            # Set default postcode if not found (will need manual entry)
            if 'postcode' not in property_data:
                property_data['postcode'] = 'UNKNOWN'

            return property_data

        except requests.RequestException as e:
            raise ValueError(f"Failed to fetch Rightmove listing: {e}")
        except Exception as e:
            raise ValueError(f"Failed to parse Rightmove listing: {e}")
