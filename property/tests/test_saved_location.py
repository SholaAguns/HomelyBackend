from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch
from decimal import Decimal
from property.models import SavedLocation
from property.serializers import SavedLocationSerializer


class SavedLocationModelTest(TestCase):
    """Test SavedLocation model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    def test_create_saved_location_minimal(self):
        """Test creating a saved location with minimal required fields"""
        location = SavedLocation.objects.create(
            user=self.user,
            name='Work',
            postcode='EC1A 1BB',
            address_line_1='1 Example Street'
        )

        self.assertEqual(location.name, 'Work')
        self.assertEqual(location.postcode, 'EC1A 1BB')
        self.assertEqual(location.address_line_1, '1 Example Street')
        self.assertEqual(location.user, self.user)
        self.assertIsNotNone(location.uuid)

    def test_create_saved_location_full(self):
        """Test creating a saved location with all fields"""
        location = SavedLocation.objects.create(
            user=self.user,
            name='Parents',
            postcode='M1 1AA',
            address_line_1='123 Main Road',
            address_line_2='Flat 4',
            city='Manchester',
            latitude=Decimal('53.483959'),
            longitude=Decimal('-2.244644')
        )

        self.assertEqual(location.name, 'Parents')
        self.assertEqual(location.postcode, 'M1 1AA')
        self.assertEqual(location.address_line_1, '123 Main Road')
        self.assertEqual(location.address_line_2, 'Flat 4')
        self.assertEqual(location.city, 'Manchester')
        self.assertEqual(location.latitude, Decimal('53.483959'))
        self.assertEqual(location.longitude, Decimal('-2.244644'))

    def test_saved_location_str(self):
        """Test string representation"""
        location = SavedLocation.objects.create(
            user=self.user,
            name='Home',
            postcode='SW1A 1AA',
            address_line_1='10 Downing Street'
        )
        self.assertEqual(str(location), 'Home (testuser)')

    def test_saved_location_ordering(self):
        """Test locations are ordered by name"""
        SavedLocation.objects.create(user=self.user, name='Zebra', postcode='AA1 1AA', address_line_1='Street')
        SavedLocation.objects.create(user=self.user, name='Apple', postcode='BB2 2BB', address_line_1='Street')

        locations = list(SavedLocation.objects.all())
        self.assertEqual(locations[0].name, 'Apple')
        self.assertEqual(locations[1].name, 'Zebra')


class SavedLocationSerializerTest(TestCase):
    """Test SavedLocation serializer and geocoding"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    @patch('property.serializers.geocode_postcode')
    def test_create_with_auto_geocoding(self, mock_geocode):
        """Test creating location auto-geocodes from postcode"""
        mock_geocode.return_value = (Decimal('51.503396'), Decimal('-0.127764'))

        data = {
            'name': 'Test Location',
            'postcode': 'SW1A 1AA',
            'address_line_1': '10 Downing Street',
            'city': 'London'
        }

        serializer = SavedLocationSerializer(
            data=data,
            context={'request': type('obj', (object,), {'user': self.user})}
        )
        self.assertTrue(serializer.is_valid())
        location = serializer.save()

        mock_geocode.assert_called_once_with('SW1A 1AA')
        self.assertEqual(location.latitude, Decimal('51.503396'))
        self.assertEqual(location.longitude, Decimal('-0.127764'))

    def test_postcode_uppercase_validation(self):
        """Test postcode is converted to uppercase"""
        data = {
            'name': 'Test',
            'postcode': 'sw1a 1aa',
            'address_line_1': 'Street'
        }

        serializer = SavedLocationSerializer(
            data=data,
            context={'request': type('obj', (object,), {'user': self.user})}
        )
        self.assertTrue(serializer.is_valid())
        self.assertEqual(serializer.validated_data['postcode'], 'SW1A 1AA')

    def test_missing_required_fields(self):
        """Test validation for missing required fields"""
        # Missing postcode
        serializer = SavedLocationSerializer(data={
            'name': 'Test',
            'address_line_1': 'Street'
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('postcode', serializer.errors)

        # Missing address_line_1
        serializer = SavedLocationSerializer(data={
            'name': 'Test',
            'postcode': 'SW1A 1AA'
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('address_line_1', serializer.errors)

        # Missing name
        serializer = SavedLocationSerializer(data={
            'postcode': 'SW1A 1AA',
            'address_line_1': 'Street'
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('name', serializer.errors)

    @patch('property.serializers.geocode_postcode')
    def test_update_postcode_regeocode(self, mock_geocode):
        """Test updating postcode triggers re-geocoding"""
        mock_geocode.return_value = (Decimal('53.483959'), Decimal('-2.244644'))

        location = SavedLocation.objects.create(
            user=self.user,
            name='Home',
            postcode='SW1A 1AA',
            address_line_1='10 Downing Street'
        )

        data = {
            'postcode': 'M1 1AA',
            'address_line_1': 'New Street'
        }

        serializer = SavedLocationSerializer(location, data=data, partial=True)
        self.assertTrue(serializer.is_valid())
        updated_location = serializer.save()

        mock_geocode.assert_called_once_with('M1 1AA')
        self.assertEqual(updated_location.postcode, 'M1 1AA')
        self.assertEqual(updated_location.latitude, Decimal('53.483959'))
        self.assertEqual(updated_location.longitude, Decimal('-2.244644'))


class SavedLocationAPITest(APITestCase):
    """Test SavedLocation API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

        self.location = SavedLocation.objects.create(
            user=self.user,
            name='Home',
            postcode='SW1A 1AA',
            address_line_1='10 Downing Street',
            city='London',
            latitude=Decimal('51.503396'),
            longitude=Decimal('-0.127764')
        )

    def test_list_saved_locations(self):
        """Test listing saved locations"""
        response = self.client.get('/api/property/saved-locations/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['name'], 'Home')
        self.assertEqual(response.data[0]['postcode'], 'SW1A 1AA')

    def test_list_only_user_locations(self):
        """Test users only see their own locations"""
        # Create another user with location
        other_user = User.objects.create_user(username='other', password='pass')
        SavedLocation.objects.create(
            user=other_user,
            name='Other Location',
            postcode='AA1 1AA',
            address_line_1='Street'
        )

        response = self.client.get('/api/property/saved-locations/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['user'], 'testuser')

    def test_retrieve_saved_location(self):
        """Test retrieving a single saved location"""
        response = self.client.get(f'/api/property/saved-locations/{self.location.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Home')
        self.assertEqual(response.data['postcode'], 'SW1A 1AA')
        self.assertEqual(response.data['address_line_1'], '10 Downing Street')
        self.assertEqual(response.data['city'], 'London')

    @patch('property.serializers.geocode_postcode')
    def test_create_saved_location(self, mock_geocode):
        """Test creating a new saved location"""
        mock_geocode.return_value = (Decimal('51.514'), Decimal('-0.093'))

        data = {
            'name': 'Office',
            'postcode': 'EC1A 1BB',
            'address_line_1': '1 Example Street',
            'city': 'London'
        }

        response = self.client.post('/api/property/saved-locations/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Office')
        self.assertEqual(response.data['user'], 'testuser')
        self.assertIn('uuid', response.data)

        # Verify in DB
        location = SavedLocation.objects.get(uuid=response.data['uuid'])
        self.assertEqual(location.name, 'Office')
        self.assertEqual(location.user.username, 'testuser')

    def test_update_saved_location(self):
        """Test updating a saved location"""
        data = {
            'name': 'Updated Home',
            'city': 'Westminster'
        }

        response = self.client.patch(
            f'/api/property/saved-locations/{self.location.uuid}/',
            data
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Updated Home')
        self.assertEqual(response.data['city'], 'Westminster')

        self.location.refresh_from_db()
        self.assertEqual(self.location.name, 'Updated Home')
        self.assertEqual(self.location.city, 'Westminster')

    def test_delete_saved_location(self):
        """Test deleting a saved location"""
        uuid = self.location.uuid

        response = self.client.delete(f'/api/property/saved-locations/{uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(SavedLocation.objects.filter(uuid=uuid).exists())

    def test_unauthenticated_access(self):
        """Test unauthenticated users cannot access endpoints"""
        self.client.force_authenticate(user=None)
        response = self.client.get('/api/property/saved-locations/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_cannot_access_other_user_location(self):
        """Test users cannot access other users' locations"""
        # Create another user with location
        other_user = User.objects.create_user(username='other', password='pass')
        other_location = SavedLocation.objects.create(
            user=other_user,
            name='Other Location',
            postcode='AA1 1AA',
            address_line_1='Street'
        )

        # Try to retrieve
        response = self.client.get(f'/api/property/saved-locations/{other_location.uuid}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Try to update
        response = self.client.patch(
            f'/api/property/saved-locations/{other_location.uuid}/',
            {'name': 'Hacked'}
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

        # Try to delete
        response = self.client.delete(f'/api/property/saved-locations/{other_location.uuid}/')
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
