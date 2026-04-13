"""
Tests for GoogleMapsService
"""
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from django.test import TestCase, override_settings
import requests

from property.services.context_retrieval.googlemaps_service import GoogleMapsService


@override_settings(GOOGLE_MAPS_API_KEY='test_api_key_12345')
class GoogleMapsServiceTest(TestCase):
    """Test GoogleMapsService implementation"""

    def setUp(self):
        """Set up test fixtures"""
        self.service = GoogleMapsService()

    def test_initialization_with_api_key(self):
        """Test service initializes with API key from settings"""
        self.assertEqual(self.service.api_key, 'test_api_key_12345')

    @override_settings(GOOGLE_MAPS_API_KEY='')
    def test_initialization_without_api_key(self):
        """Test service raises error without API key"""
        with self.assertRaises(ValueError) as context:
            GoogleMapsService()
        self.assertIn('GOOGLE_MAPS_API_KEY', str(context.exception))

    def test_place_type_mapping(self):
        """Test PLACE_TYPE_GOOGLE mapping exists"""
        self.assertIn('school', self.service.PLACE_TYPE_GOOGLE)
        self.assertIn('hospital', self.service.PLACE_TYPE_GOOGLE)
        self.assertIn('station', self.service.PLACE_TYPE_GOOGLE)

        # Station maps to multiple types
        self.assertEqual(
            self.service.PLACE_TYPE_GOOGLE['station'],
            ['train_station', 'bus_station']
        )

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    @patch('property.services.context_retrieval.googlemaps_service.calculate_distance')
    def test_search_nearby_places_success(self, mock_distance, mock_get):
        """Test successful nearby places search"""
        # Mock distance calculation
        mock_distance.return_value = 0.5  # 500m

        # Mock Nearby Search API response
        mock_nearby = Mock()
        mock_nearby.json.return_value = {
            'results': [
                {
                    'place_id': 'ChIJ123',
                    'name': 'Test School',
                    'vicinity': '123 School St',
                    'geometry': {
                        'location': {'lat': 51.5080, 'lng': -0.1290}
                    }
                }
            ]
        }
        mock_nearby.raise_for_status = Mock()

        # Mock Place Details API response
        mock_details = Mock()
        mock_details.json.return_value = {
            'result': {
                'website': 'https://testschool.com',
                'formatted_phone_number': '+44 20 1234 5678'
            }
        }
        mock_details.raise_for_status = Mock()

        # Mock Directions API responses (driving and walking)
        mock_directions_driving = Mock()
        mock_directions_driving.json.return_value = {
            'routes': [{
                'legs': [{
                    'duration': {'value': 180},  # 3 minutes in seconds
                    'distance': {'value': 600}    # 600m
                }]
            }]
        }
        mock_directions_driving.raise_for_status = Mock()

        mock_directions_walking = Mock()
        mock_directions_walking.json.return_value = {
            'routes': [{
                'legs': [{
                    'duration': {'value': 360},  # 6 minutes
                    'distance': {'value': 500}   # 500m
                }]
            }]
        }
        mock_directions_walking.raise_for_status = Mock()

        # Set up mock to return different responses for different calls
        mock_get.side_effect = [
            mock_nearby,          # Nearby search
            mock_details,         # Place details
            mock_directions_driving,  # Driving directions
            mock_directions_walking   # Walking directions
        ]

        # Call the service
        results = self.service.search_nearby_places(
            lat=51.5074,
            lon=-0.1278,
            place_type='school',
            radius=1000,
            limit=3
        )

        # Verify results
        self.assertEqual(len(results), 1)
        result = results[0]

        self.assertEqual(result['place_id'], 'ChIJ123')
        self.assertEqual(result['name'], 'Test School')
        self.assertEqual(result['vicinity'], '123 School St')
        self.assertEqual(result['website'], 'https://testschool.com')
        self.assertEqual(result['phone_number'], '+44 20 1234 5678')
        self.assertEqual(result['straight_dist'], 0.5)
        self.assertEqual(result['driving_time'], 3.0)
        self.assertEqual(result['driving_dist'], 0.6)
        self.assertEqual(result['walking_time'], 6.0)
        self.assertEqual(result['walking_dist'], 0.5)
        self.assertIn('gmaps_url', result)

    def test_search_nearby_places_invalid_type(self):
        """Test search with invalid place type"""
        with self.assertRaises(ValueError) as context:
            self.service.search_nearby_places(
                lat=51.5074,
                lon=-0.1278,
                place_type='invalid_type',
                radius=1000,
                limit=3
            )
        self.assertIn('Unknown place_type', str(context.exception))

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_search_nearby_places_deduplication(self, mock_get):
        """Test deduplication when place appears in multiple types"""
        # Mock response with same place appearing twice
        mock_response = Mock()
        mock_response.json.return_value = {
            'results': [
                {
                    'place_id': 'ChIJ_duplicate',
                    'name': 'Station',
                    'vicinity': 'Main St',
                    'geometry': {'location': {'lat': 51.508, 'lng': -0.129}}
                }
            ]
        }
        mock_response.raise_for_status = Mock()

        # Return same response for both train_station and bus_station
        mock_get.return_value = mock_response

        with patch('property.services.context_retrieval.googlemaps_service.calculate_distance', return_value=0.3):
            with patch.object(self.service, '_get_place_details', return_value=(None, None)):
                with patch.object(self.service, 'get_route_info', return_value=(None, None)):
                    results = self.service.search_nearby_places(
                        lat=51.5074,
                        lon=-0.1278,
                        place_type='station',  # Maps to both train and bus
                        radius=1000,
                        limit=3
                    )

        # Should only return one result (deduplicated)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]['place_id'], 'ChIJ_duplicate')

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_get_route_info_success(self, mock_get):
        """Test successful route info retrieval"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'routes': [{
                'legs': [{
                    'duration': {'value': 600},   # 10 minutes
                    'distance': {'value': 2000}   # 2km
                }]
            }]
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        time_min, dist_km = self.service.get_route_info(
            orig_lat=51.5074,
            orig_lon=-0.1278,
            dest_lat=51.5100,
            dest_lon=-0.1300,
            profile='driving'
        )

        self.assertEqual(time_min, 10.0)
        self.assertEqual(dist_km, 2.0)

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_get_route_info_no_routes(self, mock_get):
        """Test route info when no routes found"""
        mock_response = Mock()
        mock_response.json.return_value = {'routes': []}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        time_min, dist_km = self.service.get_route_info(
            orig_lat=51.5074,
            orig_lon=-0.1278,
            dest_lat=51.5100,
            dest_lon=-0.1300,
            profile='walking'
        )

        self.assertIsNone(time_min)
        self.assertIsNone(dist_km)

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_get_place_details_success(self, mock_get):
        """Test successful place details retrieval"""
        mock_response = Mock()
        mock_response.json.return_value = {
            'result': {
                'website': 'https://example.com',
                'formatted_phone_number': '+44 20 9876 5432'
            }
        }
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        website, phone = self.service._get_place_details('ChIJ_test')

        self.assertEqual(website, 'https://example.com')
        self.assertEqual(phone, '+44 20 9876 5432')

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_get_place_details_missing_data(self, mock_get):
        """Test place details with missing data"""
        mock_response = Mock()
        mock_response.json.return_value = {'result': {}}
        mock_response.raise_for_status = Mock()
        mock_get.return_value = mock_response

        website, phone = self.service._get_place_details('ChIJ_test')

        self.assertIsNone(website)
        self.assertIsNone(phone)

    @patch('property.services.context_retrieval.googlemaps_service.requests.get')
    def test_get_place_details_api_error(self, mock_get):
        """Test place details gracefully handles API errors"""
        mock_get.side_effect = requests.exceptions.RequestException('API Error')

        # Should not raise, just return None
        website, phone = self.service._get_place_details('ChIJ_test')

        self.assertIsNone(website)
        self.assertIsNone(phone)

    def test_build_google_maps_url(self):
        """Test Google Maps URL generation"""
        url = self.service._build_google_maps_url(
            'Test School',
            'ChIJ123'
        )

        self.assertIn('https://www.google.com/maps/search/', url)
        self.assertIn('api=1', url)
        self.assertIn('query=Test', url)
        self.assertIn('query_place_id=ChIJ123', url)

    def test_build_google_maps_url_special_chars(self):
        """Test URL encoding of special characters"""
        url = self.service._build_google_maps_url(
            "Bob's Café & Restaurant",
            'ChIJ456'
        )

        # Should properly encode special characters
        self.assertIn('https://www.google.com/maps/search/', url)
        self.assertIn('query_place_id=ChIJ456', url)
        # Should not contain raw special chars
        self.assertNotIn('&', url.split('query=')[1].split('&')[0])
