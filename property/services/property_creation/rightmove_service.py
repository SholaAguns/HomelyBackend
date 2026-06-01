"""
Rightmove property listing scraper service
Supports both single property extraction and bulk search scraping
"""
import logging
import re
import json
import time
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime, timezone

from property.models.stage1_models import KeyFeature
from property.services.property_creation.interface import IPropertyCreationService

logger = logging.getLogger('property.services.rightmove')


class RightmoveService(IPropertyCreationService):
    """
    Service for extracting property data from Rightmove.

    Supports two modes:
    1. Single property from URL (extract_property_data)
    2. Bulk properties from search (scrape_properties_by_search)
    """

    BASE_URL = "https://www.rightmove.co.uk"
    PROPERTY_SEARCH_URL = BASE_URL + "/property-to-rent/find.html"
    GET_LOCATION_URL = "https://los.rightmove.co.uk/typeahead"

    RIGHTMOVE_DOMAINS = [
        'rightmove.co.uk',
        'www.rightmove.co.uk'
    ]

    PROPERTY_TYPE_MAP = {
        'house':               'detached,semi-detached,terraced',
        'flat':                'flats',
        'bungalow':            'bungalows',
        'land':                'land',
        'commercial-property': 'commercial-property',
    }

    HEADERS = {
        'Accept': '*/*',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-GB,en;q=0.6',
        'Origin': 'https://www.rightmove.co.uk',
        'Referer': 'https://www.rightmove.co.uk',
        'sec-ch-ua': '"Not(A:Brand";v="8", "Chromium";v="144", "Brave";v="144"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-site',
        'sec-gpc': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                      'AppleWebKit/537.36 (KHTML, like Gecko) '
                      'Chrome/135.0.0.0 Safari/537.36',
    }

    # ========================================================================
    # IPropertyCreationService Interface Methods
    # ========================================================================

    def can_handle(self, input_data: str) -> bool:
        """Check if this service can handle the input URL"""
        return any(domain in input_data.lower() for domain in self.RIGHTMOVE_DOMAINS)

    def extract_property_data(self, input_data: str, input_type: str) -> Dict[str, Any]:
        try:
            import requests
        except ImportError as e:
            raise ValueError(
                f"Required packages not installed: {e}. "
                "Install with: pip install requests beautifulsoup4"
            )

        # Extract property ID from URL
        property_id = self.extract_property_id_from_url(input_data)
        if not property_id:
            raise ValueError("Could not extract property ID from URL")

        # Fetch property data via API
        property_data = self.fetch_single_property(property_id)

        # Add the original URL
        property_data['external_url'] = input_data

        return property_data

    # ========================================================================
    # Helper Methods (from POC)
    # ========================================================================

    def clean_price(self, text: str) -> int:
        """Extract integer price from strings like '£1,250 pcm' or '£300 pw'."""
        if not text:
            return 0
        t = text.replace('£', '').replace(',', '').lower()
        t = t.replace('pcm', '').replace('per month', '').replace('pw', '').replace('per week', '')
        m = re.search(r'\d+', t)
        return int(m.group()) if m else 0

    def safe_int(self, v) -> int:
        """Convert to int, default to 0 on failure."""
        try:
            return int(v)
        except:
            return 0

    def clean_date(self, s: str) -> Optional[datetime]:
        """
        Parse ISO date like '2025-04-28T12:34:56Z' into datetime with timezone.
        Returns None if input is blank or invalid.
        """
        if not s:
            return None

        try:
            if s.endswith('Z'):
                dt = datetime.fromisoformat(s.rstrip('Z'))
                return dt.replace(tzinfo=timezone.utc)
            else:
                from django.utils import timezone as django_timezone
                dt = datetime.fromisoformat(s)
                return django_timezone.make_aware(dt)
        except ValueError:
            return None

    # ========================================================================
    # Single Property Methods
    # ========================================================================

    def extract_property_id_from_url(self, url: str) -> Optional[str]:
        # Try /properties/ID pattern
        match = re.search(r'/properties/(\d+)', url)
        if match:
            return match.group(1)

        # Try /property-to-rent/ID.html pattern
        match = re.search(r'/property-to-rent/(\d+)\.html', url)
        if match:
            return match.group(1)

        return None

    def fetch_single_property(self, property_id: str) -> Dict[str, Any]:
        try:
            import requests
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ValueError(f"Required packages not installed: {e}")

        try:
            # Build property URL
            url = f"{self.BASE_URL}/properties/{property_id}"

            # Fetch page
            response = requests.get(url, headers=self.HEADERS, timeout=15)
            response.raise_for_status()

            # Parse JSON from __NEXT_DATA__ script tag
            html = response.content.decode('cp1252', errors='replace')
            soup = BeautifulSoup(html, 'html.parser')
            script_tag = soup.find('script', id='__NEXT_DATA__', type='application/json')

            if not script_tag or not script_tag.string:
                # Fallback to basic HTML scraping if API data not available
                return self._extract_from_html(soup, url, property_id)

            # Parse JSON
            raw = script_tag.string.replace('\n', '').replace('\r', '')
            data = json.loads(raw)

            # Extract property data from JSON structure
            # This structure may vary, so we need to handle different paths
            property_data = self._extract_property_from_json(data, property_id)

            return property_data

        except requests.RequestException as e:
            logger.error("fetch_single_property request failed for property_id=%s: %s", property_id, e, exc_info=True)
            raise ValueError(f"Failed to fetch Rightmove property: {e}")
        except Exception as e:
            logger.error("fetch_single_property parse failed for property_id=%s: %s", property_id, e, exc_info=True)
            raise ValueError(f"Failed to parse Rightmove property: {e}")

    def _extract_property_from_json(self, data: dict, property_id: str) -> Dict[str, Any]:
        """Extract property data from __NEXT_DATA__ JSON structure"""
        # Try to find property in various possible paths
        property_info = None

        # Path 1: props.pageProps.propertyData
        if 'props' in data and 'pageProps' in data['props']:
            page_props = data['props']['pageProps']
            if 'propertyData' in page_props:
                property_info = page_props['propertyData']

        if not property_info:
            raise ValueError("Could not find property data in JSON structure")

        # Extract data (similar to POC extraction logic)
        return self._parse_property_json(property_info, property_id)

    def _parse_property_json(self, p: dict, property_id: str) -> Dict[str, Any]:
        """Parse property JSON object into standardized dict"""
        # Core fields
        external_id = p.get('id', property_id)
        address = p.get('displayAddress', '')
        summary = p.get('summary', '')
        lat = p.get('location', {}).get('latitude')
        lng = p.get('location', {}).get('longitude')

        # Pricing
        price_info = p.get('price', {})
        price_amount = price_info.get('amount') or self.clean_price(
        price_info.get('displayPrices', [{}])[0].get('displayPrice', ''))
        price_frequency = price_info.get('frequency', '')
        currency_code = price_info.get('currencyCode', 'GBP')

        # Details
        bedrooms = p.get('bedrooms', 0)
        bathrooms = p.get('bathrooms', 0)
        property_type = p.get('propertySubType', '')
        full_desc = p.get('propertyTypeFullDescription', '')
        added_or_reduced = p.get('addedOrReduced', '')
        display_size = p.get('displaySize', '')
        listing_update_reason = p.get('listingUpdateReason', '')


        # Dates
        let_date = self.clean_date(p.get('letAvailableDate', ''))
        first_vis = self.clean_date(p.get('firstVisibleDate', ''))
        listing_update_date = self.clean_date(p.get('listingUpdateDate', ''))

        # Images
        images = []
        for img in p.get('images', []):
            images.append({
                'source_url': img.get('srcUrl') or '',
                'url': img.get('url') or '',
                'caption': img.get('caption') or ''
            })
        for img in p.get('propertyImages', {}).get('images', []):
            images.append({
                'source_url': img.get('srcUrl') or '',
                'url': img.get('url') or '',
                'caption': img.get('caption') or ''
            })

        key_features = []
        for feature in p.get('keyFeatures', []):
            key_features.append({
                'order': feature.get('order') or None,
                'description': feature.get('description') or '',
            })


        return {
            'external_id': str(external_id),
            'title': address,  # Use address as title
            'address': address,
            'summary': summary,
            'latitude': lat,
            'longitude': lng,
            'price': Decimal(str(price_amount)) if price_amount else Decimal('0'),
            'price_frequency': price_frequency,
            'currency_code': currency_code,
            'bedrooms': bedrooms,
            'bathrooms': bathrooms,
            'property_type': property_type,
            'property_type_full_description': full_desc,
            'let_available_date': let_date,
            'first_visible_date': first_vis,
            'images': images,
            'key_features': key_features,
            'added_or_reduced': added_or_reduced,
            'display_size': display_size,
            'listing_update_reason': listing_update_reason,
            'listing_update_date': listing_update_date
        }

    def _extract_from_html(self, soup, url: str, property_id: str) -> Dict[str, Any]:
        """Fallback HTML extraction if JSON not available"""
        property_data = {
            'external_id': property_id,
            'external_url': url,
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
            property_data['address'] = address_text

            # Extract postcode
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

        # Check for garden
        features_section = soup.find('div', {'class': re.compile(r'key.*features', re.IGNORECASE)})
        if features_section:
            features_text = features_section.get_text(strip=True).lower()
            if 'garden' in features_text:
                property_data['garden'] = True

        return property_data

    # ========================================================================
    # Bulk Search Methods (from POC)
    # ========================================================================

    def fetch_page(self, session, params: dict):
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ValueError("BeautifulSoup not installed")

        if logger.isEnabledFor(logging.DEBUG):
            logger.debug("fetch_page request - URL: %s", self.PROPERTY_SEARCH_URL)
            logger.debug("fetch_page request - Headers: %s", json.dumps(self.HEADERS, indent=2))
            logger.debug("fetch_page request - Params: %s", json.dumps(params, indent=2))

        resp = session.get(self.PROPERTY_SEARCH_URL, headers=self.HEADERS, params=params, timeout=15)
        html = resp.content.decode('cp1252', errors='replace')
        soup = BeautifulSoup(html, 'html.parser')

        tag = soup.find('script', id='__NEXT_DATA__', type='application/json')
        if not tag or not tag.string:
            return None, None

        raw = tag.string.replace('\n', '').replace('\r', '')
        data = json.loads(raw)

        sr = data.get('props', {}) \
            .get('pageProps', {}) \
            .get('searchResults', {})

        if logger.isEnabledFor(logging.DEBUG):
            import os
            debug_file = os.path.join(os.path.dirname(__file__), 'rightmove_response_debug.json')
            with open(debug_file, 'w', encoding='utf-8') as f:
                json.dump({'searchResults': sr, 'fullData': data}, f, indent=2, default=str)
            logger.debug("fetch_page response written to: %s", debug_file)

        return sr, data

    def get_location_id(self, session, area: str) -> str:
        """
        Get Rightmove location ID from area string using typeahead API.

        Args:
            session: requests.Session
            area: Location string (e.g., "Manchester", "SW1A 1AA")

        Returns:
            Location ID string in format "TYPE^ID"
        """
        params = {
            'query': area,
            'limit': '2',
            'exclude': 'STREET',
        }

        try:
            logger.debug("get_location_id fetching typeahead for area=%s", area)
            response = session.get(self.GET_LOCATION_URL, headers=self.HEADERS, params=params, timeout=15)
            data = response.json()

            matches = data.get('matches', [])
            if matches:
                first_id = matches[0].get('id')
                first_type = matches[0].get('type')
                location_id = f'{first_type}^{first_id}'
                logger.debug("get_location_id area=%s resolved to location_id=%s", area, location_id)
                return location_id
            else:
                logger.debug("get_location_id area=%s returned no matches", area)
                return ''
        except Exception as e:
            logger.error("get_location_id failed for area=%s: %s", area, e, exc_info=True)
            raise ValueError(f"Failed to get location ID for '{area}': {e}")

    def scrape_properties_by_search(
        self,
        search_criteria: dict,
        max_properties: int = 1000,
        progress_callback=None
    ) -> List[Dict[str, Any]]:
        try:
            import requests
        except ImportError:
            raise ValueError("requests library not installed")

        session = requests.Session()

        # Get location ID
        area = search_criteria.get('area')
        if not area:
            logger.error("scrape_properties_by_search called with no area in search_criteria")
            raise ValueError("Search criteria must include 'area'")

        logger.debug("scrape_properties_by_search area=%s max_properties=%d", area, max_properties)
        location_id = self.get_location_id(session, area)
        if not location_id:
            logger.error("scrape_properties_by_search could not resolve location for area=%s", area)
            raise ValueError(f"Could not find location ID for '{area}'")

        # Build search params
        params = {
            'searchLocation': area,
            'useLocationIdentifier': 'true',
            'radius': str(search_criteria.get('radius', 30)),
            '_includeLetAgreed': 'on',
            'locationIdentifier': location_id
        }

        OPTIONAL_PARAMS = {
            'price_min': 'minPrice',
            'price_max': 'maxPrice',
            'bedrooms_min': 'minBedrooms',
            'bedrooms_max': 'maxBedrooms',
            'max_days_since_added': 'maxDaysSinceAdded',
        }

        for src, dest in OPTIONAL_PARAMS.items():
            value = search_criteria.get(src)
            if value:
                params[dest] = str(value)

        raw_type = search_criteria.get('property_types', '')
        rm_type = self.PROPERTY_TYPE_MAP.get(raw_type)
        if rm_type:
            params['propertyTypes'] = rm_type

        # Fetch first page to get total count
        first_sr, _ = self.fetch_page(session, params)
        if not first_sr:
            raise ValueError("No search results found")

        pag = first_sr.get('pagination', {})
        total = pag.get('total', 0)


        # Calculate page_size from options array (pageSize not in response)
        options = pag.get('options', [])
        logger.debug("scrape_properties_by_search pagination: total=%d, options_count=%d", total, len(options))

        if len(options) >= 2:
            page_size = int(options[1]['value']) - int(options[0]['value'])
        elif len(options) == 1:
            page_size = total if total > 0 else 24  # Default to 24 if total is 0
        else:
            page_size = 24  # Default page size

        logger.debug("scrape_properties_by_search calculated page_size=%d", page_size)

        if page_size <= 0:
            logger.warning("scrape_properties_by_search invalid page_size=%d, using default 24", page_size)
            page_size = 24

        # Calculate pages
        total_pages = (total // page_size) + (1 if total % page_size else 0) if total > 0 else 0
        properties_to_scrape = min(total, max_properties)
        pages_to_scrape = min(total_pages, (properties_to_scrape // page_size) + 1) if page_size > 0 else 0

        logger.debug("scrape_properties_by_search total=%d page_size=%d total_pages=%d pages_to_scrape=%d properties_to_scrape=%d",
                     total, page_size, total_pages, pages_to_scrape, properties_to_scrape)

        if total == 0 or pages_to_scrape == 0:
            logger.info("scrape_properties_by_search no properties to scrape")
            return []

        # Scrape pages
        all_properties = []

        for page_idx in range(pages_to_scrape):
            offset = page_idx * page_size
            params['index'] = offset
            logger.debug("scrape_properties_by_search fetching page=%d offset=%d", page_idx, offset)

            sr, _ = self.fetch_page(session, params)
            if not sr:
                logger.debug("scrape_properties_by_search page=%d returned no data, skipping", page_idx)
                continue

            for p in sr.get('properties', []):
                if len(all_properties) >= max_properties:
                    break

                # Parse property data
                property_data = self._parse_property_json(p, str(p.get('id')))
                property_data['link'] = self.BASE_URL + p.get('propertyUrl', '')

                all_properties.append(property_data)

                # Progress callback
                if progress_callback:
                    progress_callback(len(all_properties), properties_to_scrape)

            if len(all_properties) >= max_properties:
                break

            # Rate limiting - wait between pages
            if page_idx < pages_to_scrape - 1:
                time.sleep(5)

        return all_properties

    # ========================================================================
    # Property Creation Methods
    # ========================================================================

    def _map_extracted_to_property(self, property_data: dict) -> dict:
        """
        Map Rightmove property data to Property model fields.
        Override of interface method with Rightmove-specific logic.

        Args:
            property_data: Raw extracted data from Rightmove

        Returns:
            Dict with Property model field names and values
        """
        from decimal import Decimal
        import re

        # Map fields (tested logic from task)
        mapped = {
            'external_id': property_data.get('external_id', ''),
            'external_url': property_data.get('link', property_data.get('external_url', '')),
            'title': property_data.get('title', property_data.get('address', 'Untitled')),
            'address_line_1': property_data.get('address', ''),
            'address_line_2': '',
            'city': '',
            'postcode': '',
            'summary': property_data.get('summary'),
            'latitude': property_data.get('latitude'),
            'longitude': property_data.get('longitude'),
            'price': property_data.get('price', Decimal('0')) if isinstance(property_data.get('price'), Decimal) else Decimal(str(property_data.get('price', 0))),
            'bedrooms': property_data.get('bedrooms', 0),
            'bathrooms': property_data.get('bathrooms', 0),
            'garden': False,
            'parking': False,
            'furnished_status': '',
            'square_area': None,
            'property_type': property_data.get('property_type'),
            'currency_code': property_data.get('currency_code'),
            'let_available_date': property_data.get('let_available_date'),
            'first_visible_date': property_data.get('first_visible_date'),
            'display_size': property_data.get('display_size'),
            'listing_update_reason': property_data.get('listing_update_reason'),
            'listing_update_date': property_data.get('listing_update_date'),
        }

        # Try to extract postcode from address
        if property_data.get('address'):
            postcode_match = re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}', property_data['address'])
            if postcode_match:
                mapped['postcode'] = postcode_match.group(0)

        # If still no postcode, use empty string
        if not mapped['postcode']:
            mapped['postcode'] = ''

        return mapped

    def _infer_amenities_from_text(self, property_obj, key_features: list) -> None:
        texts = [
            property_obj.summary or '',
            property_obj.description or '',
            *[f.get('description', '') or '' for f in key_features],
        ]
        combined = ' '.join(texts).lower()
        if not property_obj.garden and 'garden' in combined:
            property_obj.garden = True
        if not property_obj.parking and 'parking' in combined:
            property_obj.parking = True

    def batch_create_properties(self, properties_data: list, property_list, progress_callback=None) -> dict:
        """
        Create multiple properties in batch with progress tracking.

        Args:
            properties_data: List of property data dicts from scrape
            property_list: PropertyList to add properties to
            progress_callback: Optional callback(created, updated, failed) for progress

        Returns:
            Dict with counts: {created, updated, failed, errors}
        """
        from property.models import Property, PropertyImage
        from django.db import transaction
        from decimal import Decimal
        from datetime import datetime, date

        created_count = 0
        updated_count = 0
        failed_count = 0
        errors = []

        for idx, prop_data in enumerate(properties_data):
            try:
                with transaction.atomic():
                    # Extract images before mapping
                    images_data = prop_data.pop('images', [])
                    key_features = prop_data.pop('key_features', [])

                    # Map service data to Property model fields
                    property_fields = self._map_extracted_to_property(prop_data)

                    # Check for existing property by external_id
                    external_id = property_fields.get('external_id')
                    property_obj = None

                    if external_id:
                        existing = Property.objects.filter(external_id=external_id).first()
                        if existing:
                            # Update existing property
                            for field, value in property_fields.items():
                                if field not in ['uuid', 'created_at']:
                                    setattr(existing, field, value)
                            existing.save()

                            # Add to property list if not already there
                            if not existing.property_lists.filter(uuid=property_list.uuid).exists():
                                existing.property_lists.add(property_list)

                            property_obj = existing
                            updated_count += 1
                            logger.debug("batch_create_properties updated external_id=%s", external_id)
                        else:
                            # Create new property
                            property_obj = Property.objects.create(**property_fields)
                            property_obj.property_lists.add(property_list)
                            created_count += 1
                            logger.debug("batch_create_properties created external_id=%s", external_id)
                    else:
                        # No external_id, create new
                        property_obj = Property.objects.create(**property_fields)
                        property_obj.property_lists.add(property_list)
                        created_count += 1
                        logger.debug("batch_create_properties created property (no external_id)")

                    # Infer garden/parking from text fields
                    if property_obj:
                        self._infer_amenities_from_text(property_obj, key_features)
                        property_obj.save()

                    # Create/update images
                    if property_obj and images_data:
                        # Clear existing images
                        property_obj.images.all().delete()

                        # Create new images
                        for img_idx, image_data in enumerate(images_data):
                            PropertyImage.objects.create(
                                property=property_obj,
                                source_url=image_data.get('source_url') or image_data.get('srcUrl') or '',
                                url=image_data.get('url') or '',
                                caption=image_data.get('caption') or '',
                                order=img_idx
                            )

                    # Create/update features
                    if property_obj and key_features:
                        # Clear existing images
                        property_obj.key_features.all().delete()

                        # Create new features
                        for feature_data in key_features:
                            KeyFeature.objects.create(
                                property=property_obj,
                                description=feature_data.get('description'),
                                order=feature_data.get('order')
                            )

                    # Progress callback
                    if progress_callback:
                        progress_callback(created_count, updated_count, failed_count)

            except Exception as e:
                logger.error("batch_create_properties failed for property: %s", e, exc_info=True)
                failed_count += 1

                # Convert non-JSON-serializable types for error logging
                serializable_data = {}
                for k, v in prop_data.items():
                    if isinstance(v, Decimal):
                        serializable_data[k] = str(v)
                    elif isinstance(v, (datetime, date)):
                        serializable_data[k] = v.isoformat()
                    elif isinstance(v, list):
                        serializable_data[k] = str(v)
                    else:
                        serializable_data[k] = v

                errors.append({
                    'error': str(e),
                    'property_data': serializable_data
                })
                continue

        return {
            'created': created_count,
            'updated': updated_count,
            'failed': failed_count,
            'errors': errors
        }
