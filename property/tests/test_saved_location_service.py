from django.test import TestCase
from django.contrib.auth.models import User
from decimal import Decimal
from property.models import Property, PropertyList, Project, SavedLocation
from property.services.context_retrieval.saved_location_service import SavedLocationService


class SavedLocationServiceTest(TestCase):
    """Test SavedLocation context service"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

        self.property_list = PropertyList.objects.create(
            owner=self.user,
            project=self.project,
            title='Test List'
        )

        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='1 Test Street',
            postcode='SW1A 1AA',
            price=Decimal('1500.00'),
            bedrooms=2,
            bathrooms=1,
            latitude=Decimal('51.503396'),
            longitude=Decimal('-0.127764')
        )
        self.property.property_lists.add(self.property_list)

        # Create saved locations
        self.location1 = SavedLocation.objects.create(
            user=self.user,
            name='Home',
            postcode='SW1A 2AA',
            address_line_1='10 Downing Street',
            city='London',
            latitude=Decimal('51.503000'),
            longitude=Decimal('-0.127000')
        )

        self.location2 = SavedLocation.objects.create(
            user=self.user,
            name='Work',
            postcode='EC1A 1BB',
            address_line_1='1 Example Street',
            city='London',
            latitude=Decimal('51.517037'),
            longitude=Decimal('-0.092890')
        )

        self.service = SavedLocationService()

    def test_service_name(self):
        """Test service name"""
        self.assertEqual(self.service.get_service_name(), 'saved_locations')

    def test_validate_property_data_success(self):
        """Test property validation with coordinates"""
        self.assertTrue(self.service.validate_property_data(self.property))

    def test_validate_property_data_missing_coordinates(self):
        """Test property validation fails without coordinates"""
        prop = Property.objects.create(
            title='No Coords',
            address_line_1='Test',
            postcode='AA1 1AA',
            price=1000
        )

        with self.assertRaises(ValueError):
            self.service.validate_property_data(prop)

    def test_fetch_data_with_uuids(self):
        """Test fetching data with UUID list"""
        result = self.service.fetch_data(
            self.property,
            saved_location_uuids=[str(self.location1.uuid), str(self.location2.uuid)]
        )

        self.assertEqual(result['total_locations'], 2)
        self.assertEqual(len(result['distances']), 2)
        self.assertIsNotNone(result['closest_location'])

        # Check distance structure
        distance = result['distances'][0]
        self.assertIn('location_id', distance)
        self.assertIn('location_uuid', distance)
        self.assertIn('location_name', distance)
        self.assertIn('address', distance)
        self.assertIn('postcode', distance)
        self.assertIn('distance_km', distance)
        self.assertIn('distance_miles', distance)

    def test_fetch_data_sorted_by_distance(self):
        """Test distances are sorted closest first"""
        result = self.service.fetch_data(
            self.property,
            saved_location_uuids=[str(self.location1.uuid), str(self.location2.uuid)]
        )

        distances = result['distances']
        for i in range(len(distances) - 1):
            self.assertLessEqual(distances[i]['distance_km'], distances[i + 1]['distance_km'])

    def test_fetch_data_no_locations(self):
        """Test with no saved location IDs"""
        result = self.service.fetch_data(self.property, saved_location_uuids=[])

        self.assertEqual(result['total_locations'], 0)
        self.assertEqual(len(result['distances']), 0)

    def test_fetch_data_invalid_uuids(self):
        """Test with non-existent UUIDs"""
        result = self.service.fetch_data(
            self.property,
            saved_location_uuids=['00000000-0000-0000-0000-000000000000']
        )

        self.assertEqual(result['total_locations'], 0)
        self.assertEqual(len(result['distances']), 0)
        self.assertIn('error', result)

    def test_fetch_data_single_location(self):
        """Test with single location"""
        result = self.service.fetch_data(
            self.property,
            saved_location_uuids=[str(self.location1.uuid)]
        )

        self.assertEqual(result['total_locations'], 1)
        self.assertEqual(len(result['distances']), 1)
        self.assertEqual(result['closest_location']['location_uuid'], str(self.location1.uuid))

    def test_distance_calculation(self):
        """Test distance is calculated correctly"""
        result = self.service.fetch_data(
            self.property,
            saved_location_uuids=[str(self.location1.uuid)]
        )

        distance = result['distances'][0]
        # Distance should be very small (less than 1km) as locations are very close
        self.assertLess(distance['distance_km'], 1.0)
        self.assertGreater(distance['distance_km'], 0)

        # Miles should be km * 0.621371
        expected_miles = distance['distance_km'] * 0.621371
        self.assertAlmostEqual(distance['distance_miles'], expected_miles, places=2)

    def test_cache_key_generation(self):
        """Test cache key format"""
        cache_key = self.service.get_cache_key(self.property)

        self.assertIn('saved_locations:', cache_key)
        self.assertIn('51.5034', cache_key)
        self.assertIn('-0.1278', cache_key)
