"""
Tests for PlaceOfInterest model
"""
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
from django.db import IntegrityError

from property.models import Property, PropertyList, PlaceOfInterest


class PlaceOfInterestModelTest(TestCase):
    """Test PlaceOfInterest model"""

    def setUp(self):
        """Set up test fixtures"""
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

    def test_create_poi(self):
        """Test creating a PlaceOfInterest"""
        poi = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJdd4hrwug2EcRmSrV3Vo6llI',
            place_type='school',
            name='Test School',
            address='456 School Lane, London',
            latitude=Decimal('51.5080'),
            longitude=Decimal('-0.1290'),
            website_url='https://testschool.com',
            phone_number='+44 20 1234 5678',
            google_maps_url='https://maps.google.com/?cid=123',
            straight_distance_km=Decimal('0.15'),
            driving_distance_km=Decimal('0.25'),
            driving_time_min=Decimal('2.5'),
            walking_distance_km=Decimal('0.20'),
            walking_time_min=Decimal('3.0')
        )

        self.assertIsNotNone(poi.uuid)
        self.assertEqual(poi.name, 'Test School')
        self.assertEqual(poi.place_type, 'school')
        self.assertEqual(poi.property, self.property)

    def test_unique_together_constraint(self):
        """Test unique_together constraint (property, place_id, place_type)"""
        # Create first POI
        PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ123',
            place_type='hospital',
            name='Test Hospital',
            address='789 Hospital Rd',
            latitude=Decimal('51.5100'),
            longitude=Decimal('-0.1300'),
            google_maps_url='https://maps.google.com/?cid=456',
            straight_distance_km=Decimal('0.50')
        )

        # Try to create duplicate (same property, place_id, place_type)
        with self.assertRaises(IntegrityError):
            PlaceOfInterest.objects.create(
                property=self.property,
                place_id='ChIJ123',
                place_type='hospital',
                name='Duplicate Hospital',
                address='Different Address',
                latitude=Decimal('51.5100'),
                longitude=Decimal('-0.1300'),
                google_maps_url='https://maps.google.com/?cid=789',
                straight_distance_km=Decimal('0.60')
            )

    def test_same_place_different_types(self):
        """Test same place_id can exist with different place_types"""
        # This could happen if a place is both a restaurant and a cafe
        place_id = 'ChIJ_multi_type'

        poi1 = PlaceOfInterest.objects.create(
            property=self.property,
            place_id=place_id,
            place_type='restaurant',
            name='Test Cafe',
            address='100 Food St',
            latitude=Decimal('51.5110'),
            longitude=Decimal('-0.1310'),
            google_maps_url='https://maps.google.com/?cid=111',
            straight_distance_km=Decimal('0.30')
        )

        poi2 = PlaceOfInterest.objects.create(
            property=self.property,
            place_id=place_id,
            place_type='grocery',
            name='Test Cafe',
            address='100 Food St',
            latitude=Decimal('51.5110'),
            longitude=Decimal('-0.1310'),
            google_maps_url='https://maps.google.com/?cid=111',
            straight_distance_km=Decimal('0.30')
        )

        self.assertEqual(poi1.place_id, poi2.place_id)
        self.assertNotEqual(poi1.place_type, poi2.place_type)

    def test_has_driving_info(self):
        """Test has_driving_info() helper method"""
        # POI with driving info
        poi_with = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_driving',
            place_type='park',
            name='Test Park',
            address='200 Park Ave',
            latitude=Decimal('51.5120'),
            longitude=Decimal('-0.1320'),
            google_maps_url='https://maps.google.com/?cid=222',
            straight_distance_km=Decimal('0.40'),
            driving_distance_km=Decimal('0.50'),
            driving_time_min=Decimal('3.0')
        )

        # POI without driving info
        poi_without = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_no_driving',
            place_type='library',
            name='Test Library',
            address='300 Book St',
            latitude=Decimal('51.5130'),
            longitude=Decimal('-0.1330'),
            google_maps_url='https://maps.google.com/?cid=333',
            straight_distance_km=Decimal('0.45')
        )

        self.assertTrue(poi_with.has_driving_info())
        self.assertFalse(poi_without.has_driving_info())

    def test_has_walking_info(self):
        """Test has_walking_info() helper method"""
        # POI with walking info
        poi_with = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_walking',
            place_type='gym',
            name='Test Gym',
            address='400 Fitness Rd',
            latitude=Decimal('51.5140'),
            longitude=Decimal('-0.1340'),
            google_maps_url='https://maps.google.com/?cid=444',
            straight_distance_km=Decimal('0.35'),
            walking_distance_km=Decimal('0.40'),
            walking_time_min=Decimal('5.0')
        )

        # POI without walking info
        poi_without = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_no_walking',
            place_type='airport',
            name='Test Airport',
            address='500 Flight Way',
            latitude=Decimal('51.5150'),
            longitude=Decimal('-0.1350'),
            google_maps_url='https://maps.google.com/?cid=555',
            straight_distance_km=Decimal('5.00')
        )

        self.assertTrue(poi_with.has_walking_info())
        self.assertFalse(poi_without.has_walking_info())

    def test_ordering(self):
        """Test default ordering (place_type, straight_distance_km)"""
        # Create POIs with different types and distances
        PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_hospital_far',
            place_type='hospital',
            name='Far Hospital',
            address='Far Street',
            latitude=Decimal('51.5200'),
            longitude=Decimal('-0.1400'),
            google_maps_url='https://maps.google.com/?cid=h2',
            straight_distance_km=Decimal('2.00')
        )

        PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_school_near',
            place_type='school',
            name='Near School',
            address='Near Street',
            latitude=Decimal('51.5075'),
            longitude=Decimal('-0.1280'),
            google_maps_url='https://maps.google.com/?cid=s1',
            straight_distance_km=Decimal('0.10')
        )

        PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_hospital_near',
            place_type='hospital',
            name='Near Hospital',
            address='Close Street',
            latitude=Decimal('51.5076'),
            longitude=Decimal('-0.1281'),
            google_maps_url='https://maps.google.com/?cid=h1',
            straight_distance_km=Decimal('0.20')
        )

        # Get all POIs (should be ordered by place_type, then distance)
        pois = list(PlaceOfInterest.objects.all())

        # First two should be hospitals (alphabetically before school)
        self.assertEqual(pois[0].place_type, 'hospital')
        self.assertEqual(pois[1].place_type, 'hospital')
        # Within hospitals, near should come before far
        self.assertLess(pois[0].straight_distance_km, pois[1].straight_distance_km)
        # Last should be school
        self.assertEqual(pois[2].place_type, 'school')

    def test_str_representation(self):
        """Test string representation"""
        poi = PlaceOfInterest.objects.create(
            property=self.property,
            place_id='ChIJ_str_test',
            place_type='pharmacy',
            name='Test Pharmacy',
            address='600 Medicine Ave',
            latitude=Decimal('51.5160'),
            longitude=Decimal('-0.1360'),
            google_maps_url='https://maps.google.com/?cid=666',
            straight_distance_km=Decimal('0.25')
        )

        expected = 'Test Pharmacy (pharmacy) - 0.25km'
        self.assertEqual(str(poi), expected)

    def test_relationship_with_property(self):
        """Test relationship with Property model"""
        # Create multiple POIs for the property
        for i in range(3):
            PlaceOfInterest.objects.create(
                property=self.property,
                place_id=f'ChIJ_rel_{i}',
                place_type='supermarket',
                name=f'Supermarket {i}',
                address=f'{i*100} Market St',
                latitude=Decimal('51.5070') + Decimal(i) * Decimal('0.001'),
                longitude=Decimal('-0.1270'),
                google_maps_url=f'https://maps.google.com/?cid={i}',
                straight_distance_km=Decimal('0.10') * (i + 1)
            )

        # Check relationship
        pois = self.property.places_of_interest.all()
        self.assertEqual(pois.count(), 3)
        self.assertEqual(pois[0].name, 'Supermarket 0')
