from decimal import Decimal
from datetime import datetime, timezone


class MockRightmoveResponse:

    def __init__(self, content, status_code=200):
        self.content = content.encode('utf-8')
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockRightmoveService:

    @staticmethod
    def get_mock_single_property_data(property_id='123456'):
        """Return mock data for single property extraction"""
        return {
            'external_id': property_id,
            'title': '3 Bedroom House in Manchester',
            'address': '123 Example Street, Manchester, M1 1AA',
            'summary': 'Beautiful 3 bedroom house in the heart of Manchester',
            'latitude': Decimal('53.4808'),
            'longitude': Decimal('-2.2426'),
            'price': Decimal('1200.00'),
            'price_frequency': 'monthly',
            'currency_code': 'GBP',
            'bedrooms': 3,
            'bathrooms': 2,
            'property_type': 'terraced',
            'property_type_full_description': 'Terraced House',
            'let_available_date': datetime(2026, 2, 1, tzinfo=timezone.utc),
            'first_visible_date': datetime(2026, 1, 15, tzinfo=timezone.utc),
            'images': [
                {
                    'source_url': 'https://example.com/image1.jpg',
                    'url': 'https://example.com/image1_medium.jpg',
                    'caption': 'Living Room'
                },
                {
                    'source_url': 'https://example.com/image2.jpg',
                    'url': 'https://example.com/image2_medium.jpg',
                    'caption': 'Kitchen'
                }
            ]
        }

    @staticmethod
    def get_mock_search_results(num_properties=5):
        """Return mock data for bulk search scraping"""
        properties = []

        for i in range(num_properties):
            property_id = f'prop_{100 + i}'
            properties.append({
                'external_id': property_id,
                'title': f'Property {i+1} in Manchester',
                'address': f'{100 + i} Test Street, Manchester, M{i+1} 1AA',
                'summary': f'Nice {2+i} bedroom property',
                'latitude': Decimal(f'53.{4800 + i}'),
                'longitude': Decimal(f'-2.{2400 + i}'),
                'price': Decimal(f'{1000 + (i * 100)}.00'),
                'price_frequency': 'monthly',
                'currency_code': 'GBP',
                'bedrooms': 2 + i,
                'bathrooms': 1 + (i // 2),
                'property_type': 'flat' if i % 2 == 0 else 'terraced',
                'property_type_full_description': 'Flat' if i % 2 == 0 else 'Terraced House',
                'let_available_date': datetime(2026, 2, 1 + (i % 28), tzinfo=timezone.utc),
                'first_visible_date': datetime(2026, 1, 1 + (i % 31), tzinfo=timezone.utc),
                'link': f'https://www.rightmove.co.uk/properties/{property_id}',
                'images': [
                    {
                        'source_url': f'https://example.com/{property_id}_1.jpg',
                        'url': f'https://example.com/{property_id}_1_medium.jpg',
                        'caption': 'Main Image'
                    }
                ]
            })

        return properties

    @staticmethod
    def get_mock_next_data_html(property_id='123456'):
        """Return mock HTML with __NEXT_DATA__ script tag"""
        property_data = MockRightmoveService.get_mock_single_property_data(property_id)

        json_data = {
            'props': {
                'pageProps': {
                    'propertyData': {
                        'id': property_id,
                        'displayAddress': property_data['address'],
                        'summary': property_data['summary'],
                        'location': {
                            'latitude': float(property_data['latitude']),
                            'longitude': float(property_data['longitude'])
                        },
                        'price': {
                            'amount': float(property_data['price']),
                            'frequency': property_data['price_frequency'],
                            'currencyCode': property_data['currency_code'],
                            'displayPrices': [
                                {'displayPrice': f"£{property_data['price']} pcm"}
                            ]
                        },
                        'bedrooms': property_data['bedrooms'],
                        'bathrooms': property_data['bathrooms'],
                        'propertySubType': property_data['property_type'],
                        'propertyTypeFullDescription': property_data['property_type_full_description'],
                        'letAvailableDate': property_data['let_available_date'].isoformat(),
                        'firstVisibleDate': property_data['first_visible_date'].isoformat(),
                        'images': property_data['images'],
                        'propertyImages': {'images': []}
                    }
                }
            }
        }

        import json
        json_str = json.dumps(json_data)

        html = f'''
        <!DOCTYPE html>
        <html>
        <head><title>Property</title></head>
        <body>
            <script id="__NEXT_DATA__" type="application/json">{json_str}</script>
        </body>
        </html>
        '''

        return html

    @staticmethod
    def get_mock_search_page_html(num_properties=5, total=50, page_size=24):
        """Return mock search results page HTML with __NEXT_DATA__"""
        properties = []

        for i in range(num_properties):
            property_id = f'prop_{100 + i}'
            properties.append({
                'id': property_id,
                'displayAddress': f'{100 + i} Test Street, Manchester, M{i+1} 1AA',
                'summary': f'Nice {2+i} bedroom property',
                'location': {
                    'latitude': 53.4800 + (i * 0.01),
                    'longitude': -2.2400 + (i * 0.01)
                },
                'price': {
                    'amount': 1000 + (i * 100),
                    'frequency': 'monthly',
                    'currencyCode': 'GBP',
                    'displayPrices': [{'displayPrice': f'£{1000 + (i * 100)} pcm'}]
                },
                'bedrooms': 2 + i,
                'bathrooms': 1 + (i // 2),
                'propertySubType': 'flat' if i % 2 == 0 else 'terraced',
                'propertyTypeFullDescription': 'Flat' if i % 2 == 0 else 'Terraced House',
                'letAvailableDate': f'2026-02-{1 + i:02d}T00:00:00Z',
                'firstVisibleDate': f'2026-01-{15 + i:02d}T00:00:00Z',
                'propertyUrl': f'/properties/{property_id}',
                'images': [
                    {
                        'srcUrl': f'https://example.com/{property_id}_1.jpg',
                        'url': f'https://example.com/{property_id}_1_medium.jpg',
                        'caption': 'Main Image'
                    }
                ]
            })

        json_data = {
            'props': {
                'pageProps': {
                    'searchResults': {
                        'properties': properties,
                        'pagination': {
                            'total': total,
                            'pageSize': page_size
                        }
                    }
                }
            }
        }

        import json
        json_str = json.dumps(json_data)

        html = f'''
        <!DOCTYPE html>
        <html>
        <head><title>Search Results</title></head>
        <body>
            <script id="__NEXT_DATA__" type="application/json">{json_str}</script>
        </body>
        </html>
        '''

        return html

    @staticmethod
    def get_mock_typeahead_response(area='Manchester'):
        """Return mock typeahead API response for location search"""
        return {
            'matches': [
                {
                    'id': '12345',
                    'type': 'REGION',
                    'displayName': area,
                    'locationIdentifier': f'REGION^{area}'
                }
            ]
        }


def mock_requests_get(url, *args, **kwargs):
    """
    Mock requests.get function for testing.
    Returns appropriate mock response based on URL.
    """
    # Mock typeahead API
    if 'los.rightmove.co.uk/typeahead' in url:
        class MockTypeaheadResponse:
            status_code = 200
            def json(self):
                return MockRightmoveService.get_mock_typeahead_response()
        return MockTypeaheadResponse()

    # Mock property page
    if '/properties/' in url:
        html = MockRightmoveService.get_mock_next_data_html()
        return MockRightmoveResponse(html)

    # Mock search page
    if '/property-to-rent/find.html' in url or 'searchLocation' in str(kwargs.get('params', {})):
        html = MockRightmoveService.get_mock_search_page_html()
        return MockRightmoveResponse(html)

    # Default
    return MockRightmoveResponse('<html></html>', status_code=404)


def mock_rightmove_session():
    """Return a mock requests.Session with patched get method"""
    from unittest.mock import MagicMock

    session = MagicMock()
    session.get = mock_requests_get

    return session
