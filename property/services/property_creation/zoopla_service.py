"""
Zoopla property listing parser service
Extracts property data from Zoopla listing pages using JSON-LD structured data
"""
import logging
import re
import json
from typing import Dict, Any, Optional
from decimal import Decimal
from datetime import datetime
from property.services.property_creation.interface import IPropertyCreationService

logger = logging.getLogger('property.services.zoopla')


class ZooplaService(IPropertyCreationService):
    """
    Service for extracting property data from Zoopla property pages.

    Uses JSON-LD structured data as primary source, with HTML fallback for additional fields.
    """

    BASE_URL = "https://www.zoopla.co.uk"

    ZOOPLA_DOMAINS = [
        'zoopla.co.uk',
        'www.zoopla.co.uk'
    ]

    HEADERS = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/135.0.0.0 Safari/537.36',
    }

    # ========================================================================
    # IPropertyCreationService Interface Methods
    # ========================================================================

    def can_handle(self, input_data: str) -> bool:
        """Check if this service can handle the input URL"""
        return any(domain in input_data.lower() for domain in self.ZOOPLA_DOMAINS)

    def extract_property_data(self, input_data: str, input_type: str = 'url') -> Dict[str, Any]:
        try:
            import requests
        except ImportError as e:
            raise ValueError(
                f"Required packages not installed: {e}. "
                "Install with: pip install requests beautifulsoup4"
            )

        # Extract listing ID from URL
        listing_id = self.extract_listing_id_from_url(input_data)
        if not listing_id:
            raise ValueError("Could not extract listing ID from URL")

        if input_type == 'url':
            # Fetch page
            response = requests.get(input_data, headers=self.HEADERS, timeout=15)
            response.raise_for_status()
            property_data = self.parse_single_property(response.content, listing_id)
            property_data['external_url'] = input_data
            return property_data

        property_data = self.parse_single_property(input_data)
        return property_data

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def extract_listing_id_from_url(self, url: str) -> Optional[str]:
        """Extract listing ID from Zoopla URL"""
        # Pattern: /to-rent/details/12345678/
        match = re.search(r'/details/(\d+)', url)
        if match:
            return match.group(1)
        return None

    def parse_single_property(self, html_response: str, listing_id: str = '') -> Dict[str, Any]:
        """Fetch and parse property data from Zoopla listing page"""
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ValueError(f"Required packages not installed: {e}")

        try:
            # Keep raw HTML for regex extraction
            if isinstance(html_response, bytes):
                raw_html = html_response.decode('utf-8', errors='replace')
            else:
                raw_html = html_response

            # Parse HTML
            soup = BeautifulSoup(raw_html, 'html.parser')

            # Extract JSON-LD structured data
            json_ld_data = self._extract_json_ld(soup)

            # Parse property data from JSON-LD
            property_data = self._parse_json_ld(json_ld_data, listing_id)

            # Extract additional data from HTML (pass raw HTML for better regex matching)
            html_data = self._extract_from_html(soup, raw_html, listing_id)

            # Merge data (JSON-LD takes precedence, except for images where HTML has more)
            for k, v in html_data.items():
                if k not in property_data or not property_data[k]:
                    property_data[k] = v
                elif k == 'images' and len(v) > len(property_data.get('images', [])):
                    # Prefer HTML images if more comprehensive
                    property_data[k] = v

            return property_data

        except requests.RequestException as e:
            logger.error("fetch_single_property request failed for listing_id=%s: %s", listing_id, e, exc_info=True)
            raise ValueError(f"Failed to fetch Zoopla property: {e}")
        except Exception as e:
            logger.error("fetch_single_property parse failed for listing_id=%s: %s", listing_id, e, exc_info=True)
            raise ValueError(f"Failed to parse Zoopla property: {e}")

    def _extract_json_ld(self, soup) -> Optional[Dict[str, Any]]:
        """Extract RealEstateListing JSON-LD structured data"""
        json_ld_scripts = soup.find_all('script', type='application/ld+json')

        for script in json_ld_scripts:
            if not script.string:
                continue

            try:
                data = json.loads(script.string)
                if data.get('@type') == 'RealEstateListing':
                    return data
            except json.JSONDecodeError:
                continue

        return None

    def _parse_json_ld(self, data: Optional[Dict[str, Any]], listing_id: str) -> Dict[str, Any]:
        """Parse JSON-LD RealEstateListing into standardized dict"""
        if not data:
            logger.warning("No JSON-LD data found for listing_id=%s", listing_id)
            return {'external_id': listing_id}

        # Extract basic fields
        name = data.get('name', '')
        description = data.get('description', '')

        # Remove HTML tags from description
        description_clean = re.sub(r'<[^>]+>', ' ', description)
        description_clean = re.sub(r'\s+', ' ', description_clean).strip()

        # Extract bedrooms and bathrooms from additionalProperty
        bedrooms = 0
        bathrooms = 0
        for prop in data.get('additionalProperty', []):
            if prop.get('name') == 'Bedrooms':
                bedrooms = int(prop.get('value', 0))
            elif prop.get('name') == 'Bathrooms':
                bathrooms = int(prop.get('value', 0))

        # Extract price info
        offers = data.get('offers', {})
        price = Decimal(str(offers.get('price', 0)))
        currency_code = offers.get('priceCurrency', 'GBP')

        # Determine price frequency from eligibleDuration
        price_frequency = ''
        duration = offers.get('eligibleDuration', {})
        if duration.get('unitCode') == 'MON':
            price_frequency = 'per_month'
        elif duration.get('unitCode') == 'WEE':
            price_frequency = 'per_week'

        # Extract date posted
        date_posted = None
        if data.get('datePosted'):
            try:
                date_posted = datetime.fromisoformat(data['datePosted'].rstrip('Z'))
                from django.utils import timezone as django_timezone
                date_posted = django_timezone.make_aware(date_posted)
            except:
                pass

        # Extract main image
        image_url = data.get('image', '')
        images = []
        if image_url:
            images.append({
                'source_url': image_url,
                'url': image_url,
                'caption': 'Main Image'
            })

        return {
            'external_id': listing_id,
            'title': name,
            'address': name,  # Full name contains address
            'summary': description_clean,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'price': price,
            'price_frequency': price_frequency,
            'currency_code': currency_code,
            'first_visible_date': date_posted,
            'images': images,
        }

    def _extract_from_html(self, soup, raw_html: str, listing_id: str) -> Dict[str, Any]:
        """Extract additional property data from HTML including embedded JSON"""
        property_data = {}

        # Use raw HTML for regex searches to avoid BeautifulSoup escaping issues
        # Extract coordinates (simple pattern that works with escaped/unescaped JSON)
        lat_match = re.search(r'latitude.*?:\s*(-?\d+\.?\d*)', raw_html)
        lng_match = re.search(r'longitude.*?:\s*(-?\d+\.?\d*)', raw_html)
        if lat_match and lng_match:
            try:
                property_data['latitude'] = float(lat_match.group(1))
                property_data['longitude'] = float(lng_match.group(1))
            except ValueError:
                pass

        # Extract postcode from embedded JSON (more accurate than text search)
        postcode_match = re.search(r'postalCode.*?:\s*\\"([^\\"]+)\\"', raw_html)
        if postcode_match:
            property_data['postcode'] = postcode_match.group(1)
        else:
            # Fallback to text search
            html_text = soup.get_text()
            postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', html_text)
            if postcode_match:
                property_data['postcode'] = postcode_match.group(1)

        # Extract property type from embedded JSON
        type_match = re.search(r'propertyType.*?:\s*[\\"]([a-z\-]+)[\\"]', raw_html)
        if type_match:
            property_data['property_type'] = type_match.group(1)
        else:
            # Fallback to title parsing
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                type_patterns = [
                    r'(\d+\s+bed)\s+(terraced|detached|semi-detached|flat|apartment|house|bungalow)',
                    r'(terraced|detached|semi-detached|flat|apartment|house|bungalow)\s+house',
                ]
                for pattern in type_patterns:
                    match = re.search(pattern, title_text, re.IGNORECASE)
                    if match:
                        property_data['property_type'] = match.group(2) if len(match.groups()) > 1 else match.group(1)
                        break

        # Extract all property images from lid.zoocdn.com
        image_hashes = set(re.findall(r'https?://lid\.zoocdn\.com/u/\d+/\d+/([a-f0-9]+)\.jpg', raw_html))
        if image_hashes:
            images = []
            for i, img_hash in enumerate(sorted(image_hashes), 1):
                # Use higher resolution (1024x768)
                images.append({
                    'source_url': f'https://lid.zoocdn.com/u/1024/768/{img_hash}.jpg',
                    'url': f'https://lid.zoocdn.com/u/1024/768/{img_hash}.jpg',
                    'caption': f'Image {i}'
                })
            property_data['images'] = images

        return property_data
