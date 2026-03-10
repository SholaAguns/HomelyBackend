"""
Tests for RightmoveService without making actual HTTP requests.
Uses mocks to simulate Rightmove API responses.
"""
from django.test import TestCase
from unittest.mock import patch, MagicMock
from decimal import Decimal

from property.services.property_creation.rightmove_service import RightmoveService
from property.tests.mocks.rightmove_mock import (
    MockRightmoveService,
    mock_requests_get,
    mock_rightmove_session
)


class RightmoveServiceTest(TestCase):
    """Test RightmoveService methods with mocked responses"""

    def setUp(self):
        self.service = RightmoveService()

    def test_can_handle_rightmove_url(self):
        """Service identifies Rightmove URLs correctly"""
        self.assertTrue(self.service.can_handle('https://www.rightmove.co.uk/properties/123456'))
        self.assertTrue(self.service.can_handle('https://rightmove.co.uk/property-to-rent/123.html'))
        self.assertFalse(self.service.can_handle('https://www.zoopla.co.uk/properties/123456'))

    def test_extract_property_id_from_url(self):
        """Extract property ID from various URL formats"""
        # Format 1: /properties/ID
        url1 = 'https://www.rightmove.co.uk/properties/123456789'
        self.assertEqual(self.service.extract_property_id_from_url(url1), '123456789')

        # Format 2: /property-to-rent/ID.html
        url2 = 'https://www.rightmove.co.uk/property-to-rent/987654321.html'
        self.assertEqual(self.service.extract_property_id_from_url(url2), '987654321')

        # Invalid URL
        url3 = 'https://www.rightmove.co.uk/search'
        self.assertIsNone(self.service.extract_property_id_from_url(url3))

    def test_clean_price(self):
        """Clean price strings to integers"""
        self.assertEqual(self.service.clean_price('£1,250 pcm'), 1250)
        self.assertEqual(self.service.clean_price('£300 pw'), 300)
        self.assertEqual(self.service.clean_price('£2000 per month'), 2000)
        self.assertEqual(self.service.clean_price(''), 0)

    def test_safe_int(self):
        """Convert values to int safely"""
        self.assertEqual(self.service.safe_int('123'), 123)
        self.assertEqual(self.service.safe_int(456), 456)
        self.assertEqual(self.service.safe_int('invalid'), 0)
        self.assertEqual(self.service.safe_int(None), 0)

    def test_clean_date(self):
        """Parse ISO date strings"""
        date_str = '2026-01-28T10:30:00Z'
        result = self.service.clean_date(date_str)
        self.assertIsNotNone(result)
        self.assertEqual(result.year, 2026)
        self.assertEqual(result.month, 1)
        self.assertEqual(result.day, 28)

        # Invalid date
        self.assertIsNone(self.service.clean_date(''))
        self.assertIsNone(self.service.clean_date('invalid'))

    @patch('requests.get')
    def test_fetch_single_property(self, mock_get):
        """Fetch single property from mocked Rightmove API"""
        mock_html = MockRightmoveService.get_mock_next_data_html('123456')
        mock_get.return_value = MagicMock(
            content=mock_html.encode('cp1252'),
            status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        property_data = self.service.fetch_single_property('123456')

        self.assertEqual(property_data['external_id'], '123456')
        self.assertIn('Manchester', property_data['title'])
        self.assertEqual(property_data['bedrooms'], 3)
        self.assertEqual(property_data['bathrooms'], 2)
        self.assertEqual(property_data['price'], Decimal('1200.00'))
        self.assertIsNotNone(property_data['latitude'])
        self.assertIsNotNone(property_data['longitude'])
        self.assertIsInstance(property_data['images'], list)
        self.assertGreater(len(property_data['images']), 0)

    @patch('requests.get')
    def test_extract_property_data(self, mock_get):
        """Extract property data from URL using mocked response"""
        # Setup mock
        mock_html = MockRightmoveService.get_mock_next_data_html('123456')
        mock_get.return_value = MagicMock(
            content=mock_html.encode('cp1252'),
            status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        # Test
        url = 'https://www.rightmove.co.uk/properties/123456'
        property_data = self.service.extract_property_data(url)

        
        self.assertEqual(property_data['external_id'], '123456')
        self.assertEqual(property_data['external_url'], url)
        self.assertIn('title', property_data)
        self.assertIn('price', property_data)
        self.assertIn('bedrooms', property_data)

    @patch('requests.Session')
    def test_get_location_id(self, mock_session_class):
        """Get location ID from typeahead API"""
        # Setup mock
        mock_session = MagicMock()
        mock_response = MagicMock()
        mock_response.json.return_value = MockRightmoveService.get_mock_typeahead_response('Manchester')
        mock_session.get.return_value = mock_response
        mock_session_class.return_value = mock_session

        # Test
        session = mock_session
        location_id = self.service.get_location_id(session, 'Manchester')

        
        self.assertIsNotNone(location_id)
        self.assertIn('REGION', location_id)
        self.assertIn('12345', location_id)

    @patch('requests.Session')
    def test_scrape_properties_by_search(self, mock_session_class):
        """Scrape multiple properties from search with mocked responses"""
        mock_session = MagicMock()

        mock_typeahead = MagicMock()
        mock_typeahead.json.return_value = MockRightmoveService.get_mock_typeahead_response('Manchester')

        mock_search_html = MockRightmoveService.get_mock_search_page_html(num_properties=5)
        mock_search_page = MagicMock(
            content=mock_search_html.encode('cp1252'),
            status_code=200
        )

        # Configure session.get to return different responses
        def mock_get(url, *args, **kwargs):
            if 'typeahead' in url:
                return mock_typeahead
            else:
                return mock_search_page

        mock_session.get = mock_get
        mock_session_class.return_value = mock_session

        search_criteria = {
            'area': 'Manchester',
            'bedrooms_min': 2,
            'bedrooms_max': 4,
            'price_max': 2000
        }

        properties = self.service.scrape_properties_by_search(
            search_criteria,
            max_properties=10
        )

        
        self.assertIsInstance(properties, list)
        self.assertGreater(len(properties), 0)
        self.assertLessEqual(len(properties), 10)

        first_prop = properties[0]
        self.assertIn('external_id', first_prop)
        self.assertIn('title', first_prop)
        self.assertIn('address', first_prop)
        self.assertIn('price', first_prop)
        self.assertIn('bedrooms', first_prop)
        self.assertIn('bathrooms', first_prop)
        self.assertIn('link', first_prop)

    @patch('requests.Session')
    def test_scrape_with_progress_callback(self, mock_session_class):
        """Progress callback is called during scraping"""
        # Setup mock
        mock_session = MagicMock()

        mock_typeahead = MagicMock()
        mock_typeahead.json.return_value = MockRightmoveService.get_mock_typeahead_response('Manchester')

        mock_search_html = MockRightmoveService.get_mock_search_page_html(num_properties=3)
        mock_search_page = MagicMock(
            content=mock_search_html.encode('cp1252'),
            status_code=200
        )

        def mock_get(url, *args, **kwargs):
            if 'typeahead' in url:
                return mock_typeahead
            else:
                return mock_search_page

        mock_session.get = mock_get
        mock_session_class.return_value = mock_session

        # Track progress calls
        progress_calls = []

        def progress_callback(created, total):
            progress_calls.append((created, total))

        # Test
        search_criteria = {'area': 'Manchester'}
        properties = self.service.scrape_properties_by_search(
            search_criteria,
            max_properties=10,
            progress_callback=progress_callback
        )

        
        self.assertGreater(len(progress_calls), 0)
        # Last call should have created = len(properties)
        last_call = progress_calls[-1]
        self.assertEqual(last_call[0], len(properties))

    def test_scrape_without_area_raises_error(self):
        """Scraping without area raises ValueError"""
        search_criteria = {'bedrooms_min': 2}

        with self.assertRaises(ValueError) as context:
            self.service.scrape_properties_by_search(search_criteria)

        self.assertIn('area', str(context.exception))

    @patch('requests.get')
    def test_extract_property_data_handles_errors(self, mock_get):
        """Extract property data handles HTTP errors gracefully"""
        # Setup mock to raise exception
        mock_get.side_effect = Exception('Network error')

        # Test
        url = 'https://www.rightmove.co.uk/properties/123456'

        with self.assertRaises(ValueError) as context:
            self.service.extract_property_data(url)

        self.assertIn('Failed to parse', str(context.exception))


class RightmoveServiceEdgeCasesTest(TestCase):
    """Test edge cases and error handling"""

    def setUp(self):
        self.service = RightmoveService()

    def test_parse_property_with_missing_fields(self):
        """Parse property data with missing optional fields"""
        minimal_data = {
            'id': '123',
            'displayAddress': 'Test Address',
            'price': {'amount': 1000}
        }

        result = self.service._parse_property_json(minimal_data, '123')

        # Should not crash, should use defaults
        self.assertEqual(result['external_id'], '123')
        self.assertEqual(result['bedrooms'], 0)
        self.assertEqual(result['bathrooms'], 0)
        self.assertIsNone(result['latitude'])

    def test_extract_property_id_with_trailing_slash(self):
        """Handle URLs with trailing slashes"""
        url = 'https://www.rightmove.co.uk/properties/123456/'
        result = self.service.extract_property_id_from_url(url)
        self.assertEqual(result, '123456')

    def test_clean_price_with_various_formats(self):
        """Clean price handles various input formats"""
        test_cases = [
            ('£1,250 pcm', 1250),
            ('£300 pw', 300),
            ('1500', 1500),
            ('£2,000', 2000),
            ('invalid', 0),
            (None, 0),
            ('', 0)
        ]

        for input_val, expected in test_cases:
            result = self.service.clean_price(input_val)
            self.assertEqual(result, expected, f"Failed for input: {input_val}")
