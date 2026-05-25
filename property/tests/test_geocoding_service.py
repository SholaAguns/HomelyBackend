"""
Tests for geocoding utilities
"""
from unittest.mock import Mock, patch
from decimal import Decimal
from django.test import TestCase

from property.utils.geolocation import geocode_postcode, bulk_geocode_postcodes, validate_postcode


class GeocodingTest(TestCase):
    """Test geocoding utilities"""

    @patch('property.utils.geocoding.requests.get')
    def test_geocode_postcode_success(self, mock_get):
        """Test successful postcode geocoding"""
        # Mock API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 200,
            'result': {
                'postcode': 'SW1A 1AA',
                'latitude': 51.5010096,
                'longitude': -0.1415870,
            }
        }
        mock_get.return_value = mock_response

        # Test
        lat, lng = geocode_postcode('SW1A 1AA')

        # Verify
        self.assertEqual(lat, Decimal('51.5010096'))
        self.assertEqual(lng, Decimal('-0.1415870'))
        mock_get.assert_called_once()

    @patch('property.utils.geocoding.requests.get')
    def test_geocode_postcode_not_found(self, mock_get):
        """Test postcode not found"""
        # Mock 404 response
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Test
        lat, lng = geocode_postcode('INVALID')

        # Verify
        self.assertIsNone(lat)
        self.assertIsNone(lng)

    @patch('property.utils.geocoding.requests.get')
    def test_geocode_postcode_network_error(self, mock_get):
        """Test network error handling"""
        # Mock network error
        mock_get.side_effect = Exception('Network error')

        # Test
        lat, lng = geocode_postcode('SW1A 1AA')

        # Verify
        self.assertIsNone(lat)
        self.assertIsNone(lng)

    def test_geocode_postcode_empty_input(self):
        """Test empty postcode returns None"""
        lat, lng = geocode_postcode('')

        self.assertIsNone(lat)
        self.assertIsNone(lng)

    @patch('property.utils.geocoding.requests.post')
    def test_bulk_geocode_postcodes_success(self, mock_post):
        """Test bulk geocoding success"""
        # Mock bulk API response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 200,
            'result': [
                {
                    'query': 'SW1A 1AA',
                    'result': {
                        'postcode': 'SW1A 1AA',
                        'latitude': 51.5010096,
                        'longitude': -0.1415870
                    }
                },
                {
                    'query': 'EC1A 1BB',
                    'result': {
                        'postcode': 'EC1A 1BB',
                        'latitude': 51.5177,
                        'longitude': -0.1039
                    }
                }
            ]
        }
        mock_post.return_value = mock_response

        # Test
        postcodes = ['SW1A 1AA', 'EC1A 1BB']
        results = bulk_geocode_postcodes(postcodes)

        # Verify
        self.assertEqual(len(results), 2)
        self.assertIn('SW1A 1AA', results)
        self.assertIn('EC1A 1BB', results)

        sw1a_lat, sw1a_lng = results['SW1A 1AA']
        self.assertEqual(sw1a_lat, Decimal('51.5010096'))
        self.assertEqual(sw1a_lng, Decimal('-0.1415870'))

    @patch('property.utils.geocoding.requests.post')
    def test_bulk_geocode_postcodes_partial_success(self, mock_post):
        """Test bulk geocoding with some failures"""
        # Mock bulk API response with one success, one failure
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'status': 200,
            'result': [
                {
                    'query': 'SW1A 1AA',
                    'result': {
                        'postcode': 'SW1A 1AA',
                        'latitude': 51.5010096,
                        'longitude': -0.1415870
                    }
                },
                {
                    'query': 'INVALID',
                    'result': None  # Not found
                }
            ]
        }
        mock_post.return_value = mock_response

        # Test
        postcodes = ['SW1A 1AA', 'INVALID']
        results = bulk_geocode_postcodes(postcodes)

        # Verify
        self.assertEqual(len(results), 2)
        self.assertIn('SW1A 1AA', results)
        self.assertIn('INVALID', results)

        # Valid postcode has coords
        lat, lng = results['SW1A 1AA']
        self.assertIsNotNone(lat)
        self.assertIsNotNone(lng)

        # Invalid postcode has None
        lat, lng = results['INVALID']
        self.assertIsNone(lat)
        self.assertIsNone(lng)

    def test_bulk_geocode_empty_list(self):
        """Test bulk geocode with empty list"""
        results = bulk_geocode_postcodes([])

        self.assertEqual(results, {})

    @patch('property.utils.geocoding.requests.post')
    def test_bulk_geocode_respects_limit(self, mock_post):
        """Test bulk geocode limits to 100 postcodes"""
        # Create 150 postcodes
        postcodes = [f'SW1A {i}AA' for i in range(150)]

        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'status': 200, 'result': []}
        mock_post.return_value = mock_response

        # Test
        bulk_geocode_postcodes(postcodes)

        # Verify only 100 were sent
        call_args = mock_post.call_args
        sent_postcodes = call_args[1]['json']['postcodes']
        self.assertEqual(len(sent_postcodes), 100)

    @patch('property.utils.geocoding.requests.get')
    def test_validate_postcode_valid(self, mock_get):
        """Test postcode validation for valid postcode"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': True}
        mock_get.return_value = mock_response

        # Test
        is_valid = validate_postcode('SW1A 1AA')

        # Verify
        self.assertTrue(is_valid)

    @patch('property.utils.geocoding.requests.get')
    def test_validate_postcode_invalid(self, mock_get):
        """Test postcode validation for invalid postcode"""
        # Mock response
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'result': False}
        mock_get.return_value = mock_response

        # Test
        is_valid = validate_postcode('INVALID')

        # Verify
        self.assertFalse(is_valid)

    def test_validate_postcode_empty(self):
        """Test validation of empty postcode"""
        is_valid = validate_postcode('')

        self.assertFalse(is_valid)
