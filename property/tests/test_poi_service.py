"""
Tests for POIService
"""
from unittest.mock import Mock, patch, MagicMock
from decimal import Decimal
from django.test import TestCase, override_settings
from django.contrib.auth.models import User
from django.core.cache import cache

from property.models import Property, PropertyList, ContextOptions, PlaceOfInterest
from property.services.context_retrieval import POIService


@override_settings(GOOGLE_MAPS_API_KEY='test_api_key')
class POIServiceTest(TestCase):
    """Test POIService implementation"""

    def setUp(self):
        """Set up test fixtures"""
        # Clear cache before each test
        cache.clear()

        # Create user and property list
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

        # Create context options
        self.context_options = ContextOptions.objects.create(
            property_list=self.property_list,
            enable_poi=True,
            poi_types=['school', 'hospital'],
            poi_search_radius_meters=1600
        )

        # Create test property
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test Street',
            city='London',
            postcode='SW1A 1AA',
            latitude=Decimal('51.5074'),
            longitude=Decimal('-0.1278'),
            price=Decimal('500000.00')
        )
        self.property.property_lists.add(self.property_list)

        self.service = POIService()

    def test_service_name(self):
        """Test service name returns 'poi'"""
        self.assertEqual(self.service.get_service_name(), 'poi')

    def test_cache_key_format(self):
        """Test cache key uses grid-based rounding"""
        cache_key = self.service.get_cache_key(self.property)
        # Should round to 3 decimal places
        self.assertEqual(cache_key, 'poi:51.507:-0.128')

    def test_cache_key_rounding(self):
        """Test cache key rounds coordinates correctly"""
        # Create property with precise coordinates
        prop = Property.objects.create(
            title='Precise Property',
            address_line_1='456 Precise St',
            city='London',
            postcode='SW1A 2BB',
            latitude=Decimal('51.50749999'),  # Should round to 51.507
            longitude=Decimal('-0.12784567'),  # Should round to -0.128
            price=Decimal('400000.00')
        )

        cache_key = self.service.get_cache_key(prop)
        self.assertEqual(cache_key, 'poi:51.507:-0.128')

    def test_cache_ttl(self):
        """Test cache TTL is 30 days"""
        expected_ttl = 86400 * 30  # 30 days
        self.assertEqual(self.service.get_cache_ttl(), expected_ttl)

    def test_validate_property_data_success(self):
        """Test validation passes with valid coordinates"""
        result = self.service.validate_property_data(self.property)
        self.assertTrue(result)

    def test_validate_property_data_missing_coordinates(self):
        """Test validation fails without coordinates"""
        prop_no_coords = Property.objects.create(
            title='No Coords',
            address_line_1='789 No Coords St',
            city='London',
            postcode='SW1A 3CC',
            price=Decimal('350000.00')
        )

        with self.assertRaises(ValueError) as context:
            self.service.validate_property_data(prop_no_coords)

        self.assertIn('latitude', str(context.exception).lower())

    @patch.object(POIService, '_search_poi_type')
    def test_fetch_data_with_poi_types(self, mock_search):
        """Test fetch_data with POI types provided"""
        # Mock search results
        mock_search.return_value = [
            {
                'place_id': 'ChIJ123',
                'name': 'Test School',
                'address': '123 School St',
                'latitude': 51.5080,
                'longitude': -0.1290,
                'straight_distance_km': 0.5,
                'walking_distance_km': 0.6,
                'walking_time_min': 7.5,
                'driving_distance_km': 0.7,
                'driving_time_min': 2.5,
                'website_url': None,
                'phone_number': None,
                'google_maps_url': 'https://maps.google.com/?cid=1'
            }
        ]

        # Call service with poi_types parameter
        result = self.service.fetch_data(
            self.property,
            poi_types=['school'],
            radius=1600
        )

        # Verify result structure
        self.assertIn('poi_types', result)
        self.assertIn('school', result['poi_types'])
        self.assertEqual(len(result['poi_types']['school']), 1)
        self.assertEqual(result['total_pois_found'], 1)
        self.assertEqual(result['types_searched'], ['school'])
        self.assertEqual(result['search_radius_meters'], 1600)

    def test_fetch_data_no_poi_types(self):
        """Test fetch_data with no POI types returns empty result"""
        result = self.service.fetch_data(
            self.property,
            poi_types=[],
            radius=1600
        )

        self.assertEqual(result['poi_types'], {})
        self.assertEqual(result['total_pois_found'], 0)
        self.assertEqual(result['types_searched'], [])

    @patch.object(POIService, '_search_poi_type')
    def test_fetch_data_multiple_types(self, mock_search):
        """Test fetch_data with multiple POI types"""
        # Return different results for different types
        def search_side_effect(property_obj, place_type, radius):
            if place_type == 'school':
                return [{'place_id': 'school1', 'name': 'School 1', 'straight_distance_km': 0.3}]
            elif place_type == 'hospital':
                return [{'place_id': 'hosp1', 'name': 'Hospital 1', 'straight_distance_km': 0.8}]
            return []

        mock_search.side_effect = search_side_effect

        result = self.service.fetch_data(
            self.property,
            poi_types=['school', 'hospital'],
            radius=1600
        )

        self.assertEqual(len(result['poi_types']), 2)
        self.assertIn('school', result['poi_types'])
        self.assertIn('hospital', result['poi_types'])
        self.assertEqual(result['total_pois_found'], 2)

    @patch.object(POIService, '_search_poi_type')
    def test_fetch_data_partial_success(self, mock_search):
        """Test fetch_data handles partial failures gracefully"""
        call_count = [0]

        def search_side_effect(property_obj, place_type, radius):
            call_count[0] += 1
            if place_type == 'school':
                return [{'place_id': 'school1', 'name': 'School', 'straight_distance_km': 0.5}]
            elif place_type == 'hospital':
                raise Exception('API Error')
            return []

        mock_search.side_effect = search_side_effect

        result = self.service.fetch_data(
            self.property,
            poi_types=['school', 'hospital'],
            radius=1600
        )

        # Should return school results even though hospital failed
        self.assertEqual(len(result['poi_types']), 1)
        self.assertIn('school', result['poi_types'])
        self.assertNotIn('hospital', result['poi_types'])

    @patch.object(POIService, 'geo_service')
    def test_search_poi_type_cache_hit(self, mock_geo_service):
        """Test _search_poi_type returns cached data"""
        # Set up cache
        cache_key = 'poi:school:51.507:-0.128'
        cached_data = [
            {
                'place_id': 'cached_school',
                'name': 'Cached School',
                'straight_distance_km': 0.4
            }
        ]
        cache.set(cache_key, cached_data, 3600)

        # Call search
        result = self.service._search_poi_type(
            self.property,
            'school',
            1600
        )

        # Should return cached data without calling API
        self.assertEqual(result, cached_data)
        mock_geo_service.search_nearby_places.assert_not_called()

    @patch.object(POIService, 'geo_service')
    @patch.object(POIService, '_store_poi_data')
    def test_search_poi_type_cache_miss(self, mock_store, mock_geo_service):
        """Test _search_poi_type fetches from API on cache miss"""
        # Mock API response
        mock_geo_service.search_nearby_places.return_value = [
            {
                'place_id': 'ChIJ_new',
                'name': 'New School',
                'vicinity': '456 New St',
                'geometry': {'location': {'lat': 51.508, 'lng': -0.129}},
                'straight_dist': 0.35,
                'website': 'https://newschool.com',
                'phone_number': '+44 20 1111 2222',
                'driving_dist': 0.45,
                'driving_time': 2.0,
                'walking_dist': 0.40,
                'walking_time': 5.0,
                'gmaps_url': 'https://maps.google.com/?cid=new'
            }
        ]

        # Call search
        result = self.service._search_poi_type(
            self.property,
            'school',
            1600
        )

        # Should call API
        mock_geo_service.search_nearby_places.assert_called_once()
        # Should store in DB
        mock_store.assert_called_once()
        # Should return formatted results
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['place_id'], 'ChIJ_new')

        # Check cache was updated
        cache_key = 'poi:school:51.507:-0.128'
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached[0]['place_id'], 'ChIJ_new')

    @patch.object(POIService, 'geo_service')
    def test_search_poi_type_no_results(self, mock_geo_service):
        """Test _search_poi_type handles empty results"""
        mock_geo_service.search_nearby_places.return_value = []

        result = self.service._search_poi_type(
            self.property,
            'airport',
            1600
        )

        self.assertEqual(result, [])

    def test_store_poi_data(self):
        """Test _store_poi_data creates PlaceOfInterest records"""
        places = [
            {
                'place_id': 'ChIJ_store1',
                'name': 'Store Test School',
                'vicinity': '789 Store St',
                'geometry': {'location': {'lat': 51.509, 'lng': -0.130}},
                'straight_dist': 0.60,
                'website': 'https://store.com',
                'phone_number': '+44 20 3333 4444',
                'driving_dist': 0.70,
                'driving_time': 3.0,
                'walking_dist': 0.65,
                'walking_time': 8.0,
                'gmaps_url': 'https://maps.google.com/?cid=store'
            }
        ]

        self.service._store_poi_data(self.property, 'school', places)

        # Check POI was created
        poi = PlaceOfInterest.objects.get(
            property=self.property,
            place_id='ChIJ_store1'
        )

        self.assertEqual(poi.name, 'Store Test School')
        self.assertEqual(poi.place_type, 'school')
        self.assertEqual(poi.straight_distance_km, Decimal('0.60'))
        self.assertEqual(poi.website_url, 'https://store.com')

    def test_store_poi_data_duplicate(self):
        """Test _store_poi_data doesn't create duplicates"""
        places = [
            {
                'place_id': 'ChIJ_dup',
                'name': 'Duplicate School',
                'vicinity': '999 Dup St',
                'geometry': {'location': {'lat': 51.510, 'lng': -0.131}},
                'straight_dist': 0.70,
                'gmaps_url': 'https://maps.google.com/?cid=dup'
            }
        ]

        # Store twice
        self.service._store_poi_data(self.property, 'school', places)
        self.service._store_poi_data(self.property, 'school', places)

        # Should only have one record
        count = PlaceOfInterest.objects.filter(
            property=self.property,
            place_id='ChIJ_dup'
        ).count()

        self.assertEqual(count, 1)

    def test_format_place(self):
        """Test _format_place formats data correctly"""
        place = {
            'place_id': 'ChIJ_format',
            'name': 'Format Test',
            'vicinity': 'Format St',
            'geometry': {'location': {'lat': 51.511, 'lng': -0.132}},
            'straight_dist': 0.8543,  # Should round to 0.85
            'website': 'https://format.com',
            'phone_number': '+44 20 5555 6666',
            'driving_dist': 0.9876,   # Should round to 0.99
            'driving_time': 4.567,    # Should round to 4.6
            'walking_dist': 0.8765,   # Should round to 0.88
            'walking_time': 10.234,   # Should round to 10.2
            'gmaps_url': 'https://maps.google.com/?cid=format'
        }

        formatted = self.service._format_place(place)

        self.assertEqual(formatted['straight_distance_km'], 0.85)
        self.assertEqual(formatted['driving_distance_km'], 0.99)
        self.assertEqual(formatted['driving_time_min'], 4.6)
        self.assertEqual(formatted['walking_distance_km'], 0.88)
        self.assertEqual(formatted['walking_time_min'], 10.2)

    def test_format_place_missing_optional_data(self):
        """Test _format_place handles missing optional data"""
        place = {
            'place_id': 'ChIJ_minimal',
            'name': 'Minimal Place',
            'vicinity': 'Minimal St',
            'geometry': {'location': {'lat': 51.512, 'lng': -0.133}},
            'straight_dist': 1.0,
            'gmaps_url': 'https://maps.google.com/?cid=minimal'
        }

        formatted = self.service._format_place(place)

        self.assertIsNone(formatted['driving_distance_km'])
        self.assertIsNone(formatted['driving_time_min'])
        self.assertIsNone(formatted['walking_distance_km'])
        self.assertIsNone(formatted['walking_time_min'])
        self.assertIsNone(formatted['website_url'])
        self.assertIsNone(formatted['phone_number'])

    def test_format_response(self):
        """Test _format_response creates correct structure"""
        all_pois = {
            'school': [{'place_id': 's1'}, {'place_id': 's2'}],
            'hospital': [{'place_id': 'h1'}]
        }
        types_searched = ['school', 'hospital', 'park']
        radius = 2000

        result = self.service._format_response(
            all_pois,
            types_searched,
            radius
        )

        self.assertEqual(result['poi_types'], all_pois)
        self.assertEqual(result['total_pois_found'], 3)
        self.assertEqual(result['types_searched'], types_searched)
        self.assertEqual(result['search_radius_meters'], 2000)
