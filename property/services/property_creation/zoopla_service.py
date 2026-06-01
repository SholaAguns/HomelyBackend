import logging
import re
import json
import time
from typing import Dict, Any, List, Optional
from decimal import Decimal
from datetime import datetime

from property.services.property_creation.interface import IPropertyCreationService
from property.services.flaresolverr_service import FlareSolverrService

logger = logging.getLogger('property.services.zoopla')


class ZooplaService(IPropertyCreationService):

    BASE_URL = "https://www.zoopla.co.uk"
    ZOOPLA_SEARCH_URL = "https://www.zoopla.co.uk/to-rent/property/{area}/"
    DELAY_BETWEEN_PAGES = 4

    ZOOPLA_DOMAINS = [
        'zoopla.co.uk',
        'www.zoopla.co.uk'
    ]

    MAX_DAYS_TO_ADDED = {
        1: '1day',
        3: '3days',
        7: '1week',
        14: '2weeks',
        30: '1month',
    }

    PROPERTY_TYPE_MAP = {
        'house':               'detached,semi-detached,terraced',
        'flat':                'flats',
        'bungalow':            'bungalows',
        'land':                'land',
    }

    def __init__(self, flaresolverr: FlareSolverrService = None):
        self._fs = flaresolverr or FlareSolverrService()

    # ========================================================================
    # IPropertyCreationService Interface Methods
    # ========================================================================

    def can_handle(self, input_data: str) -> bool:
        return any(domain in input_data.lower() for domain in self.ZOOPLA_DOMAINS)

    def extract_property_data(self, input_data: str, input_type: str = 'url') -> Dict[str, Any]:
        listing_id = self.extract_listing_id_from_url(input_data)
        if not listing_id:
            raise ValueError("Could not extract listing ID from URL")

        html = self._fs.fetch(input_data)
        property_data = self.parse_single_property(html, listing_id)
        property_data['external_url'] = input_data
        return property_data

    # ========================================================================
    # Single Property Methods
    # ========================================================================

    def extract_listing_id_from_url(self, url: str) -> Optional[str]:
        match = re.search(r'/details/(\d+)', url)
        if match:
            return match.group(1)
        return None

    def parse_single_property(self, html_response: str, listing_id: str = '') -> Dict[str, Any]:
        try:
            from bs4 import BeautifulSoup
        except ImportError as e:
            raise ValueError(f"Required packages not installed: {e}")

        try:
            if isinstance(html_response, bytes):
                raw_html = html_response.decode('utf-8', errors='replace')
            else:
                raw_html = html_response

            soup = BeautifulSoup(raw_html, 'html.parser')
            json_ld_data = self._extract_json_ld(soup)
            property_data = self._parse_json_ld(json_ld_data, listing_id)
            html_data = self._extract_from_html(soup, raw_html, listing_id)

            for k, v in html_data.items():
                if k not in property_data or not property_data[k]:
                    property_data[k] = v
                elif k == 'images' and len(v) > len(property_data.get('images', [])):
                    property_data[k] = v

            return property_data

        except Exception as e:
            logger.error("parse_single_property failed listing_id=%s: %s", listing_id, e, exc_info=True)
            raise ValueError(f"Failed to parse Zoopla property: {e}")

    def _extract_json_ld(self, soup) -> Optional[Dict[str, Any]]:
        for script in soup.find_all('script', type='application/ld+json'):
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
        if not data:
            logger.warning("No JSON-LD data found for listing_id=%s", listing_id)
            return {'external_id': listing_id}

        name = data.get('name', '')
        description = data.get('description', '')
        description_clean = re.sub(r'<[^>]+>', ' ', description)
        description_clean = re.sub(r'\s+', ' ', description_clean).strip()

        bedrooms = 0
        bathrooms = 0
        for prop in data.get('additionalProperty', []):
            if prop.get('name') == 'Bedrooms':
                bedrooms = int(prop.get('value', 0))
            elif prop.get('name') == 'Bathrooms':
                bathrooms = int(prop.get('value', 0))

        offers = data.get('offers', {})
        price = Decimal(str(offers.get('price', 0)))
        currency_code = offers.get('priceCurrency', 'GBP')

        price_frequency = ''
        duration = offers.get('eligibleDuration', {})
        if duration.get('unitCode') == 'MON':
            price_frequency = 'per_month'
        elif duration.get('unitCode') == 'WEE':
            price_frequency = 'per_week'

        date_posted = None
        if data.get('datePosted'):
            try:
                date_posted = datetime.fromisoformat(data['datePosted'].rstrip('Z'))
                from django.utils import timezone as django_timezone
                date_posted = django_timezone.make_aware(date_posted)
            except Exception:
                pass

        image_url = data.get('image', '')
        images = []
        if image_url:
            images.append({'source_url': image_url, 'url': image_url, 'caption': 'Main Image'})

        return {
            'external_id': listing_id,
            'title': name,
            'address': name,
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
        property_data = {}

        lat_match = re.search(r'latitude.*?:\s*(-?\d+\.?\d*)', raw_html)
        lng_match = re.search(r'longitude.*?:\s*(-?\d+\.?\d*)', raw_html)
        if lat_match and lng_match:
            try:
                property_data['latitude'] = float(lat_match.group(1))
                property_data['longitude'] = float(lng_match.group(1))
            except ValueError:
                pass

        postcode_match = re.search(r'postalCode.*?:\s*\\"([^\\"]+)\\"', raw_html)
        if postcode_match:
            property_data['postcode'] = postcode_match.group(1)
        else:
            html_text = soup.get_text()
            postcode_match = re.search(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2})\b', html_text)
            if postcode_match:
                property_data['postcode'] = postcode_match.group(1)

        type_match = re.search(r'propertyType.*?:\s*[\\"]([a-z\-]+)[\\"]', raw_html)
        if type_match:
            property_data['property_type'] = type_match.group(1)
        else:
            title_tag = soup.find('title')
            if title_tag:
                title_text = title_tag.get_text()
                for pattern in [
                    r'(\d+\s+bed)\s+(terraced|detached|semi-detached|flat|apartment|house|bungalow)',
                    r'(terraced|detached|semi-detached|flat|apartment|house|bungalow)\s+house',
                ]:
                    match = re.search(pattern, title_text, re.IGNORECASE)
                    if match:
                        property_data['property_type'] = match.group(2) if len(match.groups()) > 1 else match.group(1)
                        break

        image_hashes = set(re.findall(r'https?://lid\.zoocdn\.com/u/\d+/\d+/([a-f0-9]+)\.jpg', raw_html))
        if image_hashes:
            images = []
            for i, img_hash in enumerate(sorted(image_hashes), 1):
                images.append({
                    'source_url': f'https://lid.zoocdn.com/u/1024/768/{img_hash}.jpg',
                    'url': f'https://lid.zoocdn.com/u/1024/768/{img_hash}.jpg',
                    'caption': f'Image {i}'
                })
            property_data['images'] = images

        return property_data

    # ========================================================================
    # Search Page Methods
    # ========================================================================

    def _get_jsonld_by_type(self, soup, schema_type: str) -> Optional[Dict]:
        for tag in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(tag.string or "")
            except json.JSONDecodeError:
                continue
            if data.get("@type") == schema_type:
                return data
            for node in data.get("@graph", []):
                if node.get("@type") == schema_type:
                    return node
        return None

    def _parse_search_listing(self, item: dict) -> Optional[Dict[str, Any]]:
        product = item.get("item", {})
        if not product:
            return None

        related = product.get("isRelatedTo", {})
        offers = product.get("offers", {})
        geo = related.get("geo", {})

        url = product.get("url", "")
        listing_id = ""
        id_match = re.search(r'/details/(\d+)', url)
        if id_match:
            listing_id = id_match.group(1)

        try:
            price = Decimal(str(offers.get("price", 0)))
        except Exception:
            price = Decimal("0")

        try:
            bedrooms = int(related.get("numberOfBedrooms", 0))
        except (ValueError, TypeError):
            bedrooms = 0

        try:
            bathrooms = int(related.get("numberOfBathroomsTotal", 0))
        except (ValueError, TypeError):
            bathrooms = 0

        try:
            latitude = float(geo["latitude"]) if geo.get("latitude") is not None else None
            longitude = float(geo["longitude"]) if geo.get("longitude") is not None else None
        except (ValueError, TypeError):
            latitude = longitude = None

        address = related.get("address", product.get("name", ""))
        image_url = product.get("image", "")

        return {
            "external_id": listing_id,
            "external_url": url,
            "title": product.get("name", address),
            "address": address,
            "price": price,
            "price_frequency": "per_month",
            "currency_code": offers.get("priceCurrency", "GBP"),
            "bedrooms": bedrooms,
            "bathrooms": bathrooms,
            "latitude": latitude,
            "longitude": longitude,
            "images": [{"source_url": image_url, "url": image_url, "caption": "Main image"}] if image_url else [],
            "key_features": [],
        }

    # ========================================================================
    # Bulk Search Methods
    # ========================================================================

    def scrape_properties_by_search(
        self,
        search_criteria: dict,
        max_properties: int = 100,
        progress_callback=None,
    ) -> List[Dict[str, Any]]:
        from bs4 import BeautifulSoup

        area = search_criteria.get("area", "")
        if not area:
            raise ValueError("Search criteria must include 'area'")

        area_slug = area.lower().replace(" ", "-")
        base_url = self.ZOOPLA_SEARCH_URL.format(area=area_slug)

        params: dict = {}
        if search_criteria.get("bedrooms_min"):
            params["beds_min"] = str(search_criteria["bedrooms_min"])
        if search_criteria.get("bedrooms_max"):
            params["beds_max"] = str(search_criteria["bedrooms_max"])
        if search_criteria.get("price_min"):
            params["price_min"] = str(search_criteria["price_min"])
        if search_criteria.get("price_max"):
            params["price_max"] = str(search_criteria["price_max"])
        if search_criteria.get("radius"):
            params["radius"] = str(search_criteria["radius"])

        raw_type = search_criteria.get("property_types", "")
        zoopla_type = self.PROPERTY_TYPE_MAP.get(raw_type)
        if zoopla_type:
            params["property_sub_type"] = zoopla_type

        days = search_criteria.get("max_days_since_added")
        if days:
            for threshold in sorted(self.MAX_DAYS_TO_ADDED):
                if days <= threshold:
                    params["added"] = self.MAX_DAYS_TO_ADDED[threshold]
                    break

        session_id = self._fs.create_session()
        logger.debug("scrape_properties_by_search area=%s session=%s", area, session_id)

        all_properties = []
        page_num = 1

        try:
            while len(all_properties) < max_properties:
                page_params = {**params, "pn": str(page_num)}
                param_str = "&".join(f"{k}={v}" for k, v in page_params.items())
                url = f"{base_url}?{param_str}"
                logger.debug("scrape_properties_by_search page=%d url=%s", page_num, url)

                html = self._fs.fetch(url, session_id=session_id)
                soup = BeautifulSoup(html, "html.parser")

                if page_num == 1:
                    zad_tag = soup.find("script", {"id": "__ZAD_TARGETING__"})
                    if zad_tag:
                        try:
                            zad = json.loads(zad_tag.string or "")
                            total_available = int(zad.get("search_results_count", 0))
                            logger.debug("scrape_properties_by_search total_available=%d", total_available)
                            if progress_callback:
                                progress_callback(0, min(total_available, max_properties))
                        except (json.JSONDecodeError, ValueError):
                            pass

                sr_page = self._get_jsonld_by_type(soup, "SearchResultsPage")
                if not sr_page:
                    logger.debug("scrape_properties_by_search page=%d no SearchResultsPage JSON-LD", page_num)
                    break

                items = sr_page.get("mainEntity", {}).get("itemListElement", [])
                if not items:
                    logger.debug("scrape_properties_by_search page=%d no items", page_num)
                    break

                for item in items:
                    if len(all_properties) >= max_properties:
                        break
                    parsed = self._parse_search_listing(item)
                    if parsed:
                        all_properties.append(parsed)
                        if progress_callback:
                            progress_callback(len(all_properties), max_properties)

                if len(all_properties) >= max_properties or len(items) == 0:
                    break

                page_num += 1
                time.sleep(self.DELAY_BETWEEN_PAGES)

        finally:
            self._fs.destroy_session(session_id)

        logger.debug("scrape_properties_by_search area=%s returned %d properties", area, len(all_properties))
        return all_properties

    # ========================================================================
    # Property Creation Methods
    # ========================================================================

    def _map_extracted_to_property(self, property_data: dict) -> dict:
        import re as _re
        from decimal import Decimal as _Decimal

        postcode = property_data.get('postcode', '')
        if not postcode and property_data.get('address'):
            postcode_match = _re.search(
                r'[A-Z]{1,2}\d{1,2}[A-Z]?\s?\d[A-Z]{2}',
                property_data['address']
            )
            if postcode_match:
                postcode = postcode_match.group(0)

        return {
            'external_id': property_data.get('external_id', ''),
            'external_url': property_data.get('external_url', property_data.get('link', '')),
            'title': property_data.get('title', property_data.get('address', 'Untitled')),
            'address_line_1': property_data.get('address', ''),
            'address_line_2': '',
            'city': '',
            'postcode': postcode,
            'latitude': property_data.get('latitude'),
            'longitude': property_data.get('longitude'),
            'price': _Decimal(str(property_data.get('price', 0))),
            'price_frequency': property_data.get('price_frequency', ''),
            'currency_code': property_data.get('currency_code', 'GBP'),
            'bedrooms': property_data.get('bedrooms', 0),
            'bathrooms': property_data.get('bathrooms', 0),
            'garden': False,
            'parking': False,
            'furnished_status': '',
            'square_area': None,
            'property_type': property_data.get('property_type', ''),
            'summary': property_data.get('description', ''),
            'first_visible_date': property_data.get('first_visible_date'),
        }

    def _infer_amenities_from_text(self, property_obj, key_features: list) -> None:
        texts = [
            property_obj.summary or '',
            *[f.get('description', '') or '' for f in key_features],
        ]
        combined = ' '.join(texts).lower()
        if not property_obj.garden and 'garden' in combined:
            property_obj.garden = True
        if not property_obj.parking and 'parking' in combined:
            property_obj.parking = True

    def batch_create_properties(self, properties_data: list, property_list, progress_callback=None) -> dict:
        from property.models import Property, PropertyImage
        from property.models.stage1_models import KeyFeature
        from django.db import transaction
        from decimal import Decimal
        from datetime import datetime, date

        created_count = 0
        updated_count = 0
        failed_count = 0
        errors = []

        for prop_data in properties_data:
            try:
                with transaction.atomic():
                    images_data = prop_data.pop('images', [])
                    key_features = prop_data.pop('key_features', [])

                    property_fields = self._map_extracted_to_property(prop_data)
                    external_id = property_fields.get('external_id')
                    property_obj = None

                    if external_id:
                        existing = Property.objects.filter(external_id=external_id).first()
                        if existing:
                            for field, value in property_fields.items():
                                if field not in ['uuid', 'created_at']:
                                    setattr(existing, field, value)
                            existing.save()
                            if not existing.property_lists.filter(uuid=property_list.uuid).exists():
                                existing.property_lists.add(property_list)
                            property_obj = existing
                            updated_count += 1
                        else:
                            property_obj = Property.objects.create(**property_fields)
                            property_obj.property_lists.add(property_list)
                            created_count += 1
                    else:
                        property_obj = Property.objects.create(**property_fields)
                        property_obj.property_lists.add(property_list)
                        created_count += 1

                    if property_obj:
                        self._infer_amenities_from_text(property_obj, key_features)
                        property_obj.save()

                    if property_obj and images_data:
                        property_obj.images.all().delete()
                        for idx, image_data in enumerate(images_data):
                            PropertyImage.objects.create(
                                property=property_obj,
                                source_url=image_data.get('source_url') or '',
                                url=image_data.get('url') or '',
                                caption=image_data.get('caption') or '',
                                order=idx
                            )

                    if property_obj and key_features:
                        property_obj.key_features.all().delete()
                        for feature_data in key_features:
                            KeyFeature.objects.create(
                                property=property_obj,
                                description=feature_data.get('description'),
                                order=feature_data.get('order')
                            )

                    if progress_callback:
                        progress_callback(created_count, updated_count, failed_count)

            except Exception as e:
                logger.error("batch_create_properties failed: %s", e, exc_info=True)
                failed_count += 1
                serializable_data = {}
                for k, v in prop_data.items():
                    if isinstance(v, Decimal):
                        serializable_data[k] = str(v)
                    elif isinstance(v, (datetime, date)):
                        serializable_data[k] = v.isoformat()
                    else:
                        serializable_data[k] = str(v)
                errors.append({'error': str(e), 'property_data': serializable_data})

        return {'created': created_count, 'updated': updated_count, 'failed': failed_count, 'errors': errors}
