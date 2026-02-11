from django.test import TestCase
from django.contrib.auth.models import User
from django_fsm import TransitionNotAllowed
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch, MagicMock
import uuid

from property.models import PropertyList, Property, SavedLocation, StateTransitionLog
from property.serializers import PropertyListSerializer, PropertySerializer, SavedLocationSerializer


# ==========================
# Model Tests
# ==========================

class PropertyListModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    def test_property_list_creation(self):
        """PropertyList created with correct defaults"""
        prop_list = PropertyList.objects.create(
            owner=self.user,
            title='My Properties'
        )
        self.assertEqual(prop_list.owner, self.user)
        self.assertEqual(prop_list.title, 'My Properties')
        self.assertEqual(prop_list.state, 'DRAFT')
        self.assertIsNotNone(prop_list.uuid)
        self.assertIsNotNone(prop_list.created_at)

    def test_property_list_uuid_unique(self):
        """PropertyList UUIDs are unique"""
        list1 = PropertyList.objects.create(owner=self.user, title='List 1')
        list2 = PropertyList.objects.create(owner=self.user, title='List 2')
        self.assertNotEqual(list1.uuid, list2.uuid)

    def test_property_list_unique_together(self):
        """PropertyList enforces unique owner+title"""
        PropertyList.objects.create(owner=self.user, title='Same Title')

        with self.assertRaises(Exception):
            PropertyList.objects.create(owner=self.user, title='Same Title')

    def test_property_list_str(self):
        """PropertyList string representation"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')
        self.assertEqual(str(prop_list), 'Test List (testuser)')

    def test_property_list_status_summary(self):
        """PropertyList returns correct status summary"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')

        prop1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1,
            state='NEW'
        )
        prop1.property_lists.add(prop_list)

        prop2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 1AB',
            price=200000,
            bedrooms=3,
            bathrooms=2,
            state='STAGE2_COMPLETE'
        )
        prop2.property_lists.add(prop_list)

        summary = prop_list.get_status_summary()
        self.assertEqual(summary['total'], 2)
        self.assertEqual(summary['new'], 1)
        self.assertEqual(summary['stage2_complete'], 1)


class PropertyModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

    def test_property_creation(self):
        """Property created with correct fields"""
        prop = Property.objects.create(
            title='Modern Flat',
            address_line_1='123 Test St',
            address_line_2='Apt 4B',
            city='London',
            postcode='SW1A 1AA',
            price=450000,
            bedrooms=2,
            bathrooms=1,
            garden=True,
            parking=False
        )
        prop.property_lists.add(self.property_list)

        self.assertEqual(prop.title, 'Modern Flat')
        self.assertEqual(prop.state, 'NEW')
        self.assertIsNotNone(prop.uuid)
        self.assertEqual(prop.bedrooms, 2)
        self.assertTrue(prop.garden)
        self.assertFalse(prop.parking)

    def test_property_uuid_unique(self):
        """Property UUIDs are unique"""
        prop1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop1.property_lists.add(self.property_list)

        prop2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 1AB',
            price=200000,
            bedrooms=3,
            bathrooms=2
        )
        prop2.property_lists.add(self.property_list)
        self.assertNotEqual(prop1.uuid, prop2.uuid)

    def test_property_str(self):
        """Property string representation"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)
        self.assertEqual(str(prop), 'Test Property - SW1A 1AA')


class SavedLocationModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    def test_saved_location_creation(self):
        """SavedLocation created with correct fields"""
        location = SavedLocation.objects.create(
            user=self.user,
            name='Work Office',
            address='10 Downing Street, London',
            latitude=51.5034,
            longitude=-0.1276
        )

        self.assertEqual(location.name, 'Work Office')
        self.assertIsNotNone(location.uuid)
        self.assertEqual(float(location.latitude), 51.5034)

    def test_saved_location_str(self):
        """SavedLocation string representation"""
        location = SavedLocation.objects.create(
            user=self.user,
            name='Work',
            address='London',
            latitude=51.5,
            longitude=-0.1
        )
        self.assertEqual(str(location), 'Work (testuser)')


# ==========================
# FSM State Machine Tests
# ==========================

class PropertyStateMachineTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com')
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        self.property.property_lists.add(self.property_list)

    def test_property_initial_state(self):
        """Property starts in NEW state"""
        self.assertEqual(self.property.state, 'NEW')

    def test_transition_new_to_stage2(self):
        """Valid transition: NEW → STAGE2_IN_PROGRESS"""
        self.property.run_stage2()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_IN_PROGRESS')

    def test_invalid_transition_new_to_stage3(self):
        """Invalid: Cannot skip Stage 2"""
        with self.assertRaises(TransitionNotAllowed):
            self.property.run_stage3()

    def test_transition_stage2_complete(self):
        """Valid transition: STAGE2_IN_PROGRESS → STAGE2_COMPLETE"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_COMPLETE')

    def test_transition_run_stage3(self):
        """Valid transition: STAGE2_COMPLETE → STAGE3_IN_PROGRESS"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.run_stage3()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE3_IN_PROGRESS')

    def test_transition_complete_stage3(self):
        """Valid transition: STAGE3_IN_PROGRESS → STAGE3_COMPLETE"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.run_stage3()
        self.property.save()
        self.property.complete_stage3()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE3_COMPLETE')

    def test_rerun_services_from_stage2_complete(self):
        """Valid rerun: STAGE2_COMPLETE → STAGE2_IN_PROGRESS"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.rerun_services()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_IN_PROGRESS')

    def test_rerun_services_from_stage3_complete(self):
        """Valid rerun: STAGE3_COMPLETE → STAGE2_IN_PROGRESS"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.run_stage3()
        self.property.save()
        self.property.complete_stage3()
        self.property.save()
        self.property.rerun_services()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_IN_PROGRESS')

    def test_stage3_from_stage3_complete(self):
        """Valid transition: STAGE3_COMPLETE → STAGE3_IN_PROGRESS"""
        # Advance to STAGE3_COMPLETE
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.run_stage3()
        self.property.save()
        self.property.complete_stage3()
        self.property.save()

        # Can rerun stage3
        self.property.run_stage3()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE3_IN_PROGRESS')


class PropertyListStateMachineTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com')
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

    def test_property_list_initial_state(self):
        """PropertyList starts in DRAFT state"""
        self.assertEqual(self.property_list.state, 'DRAFT')

    def test_activate_property_list(self):
        """Valid transition: DRAFT → ACTIVE"""
        self.property_list.activate()
        self.property_list.save()
        self.assertEqual(self.property_list.state, 'ACTIVE')


# ==========================
# Serializer Tests
# ==========================

class PropertyListSerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )

    def test_property_list_serializer_fields(self):
        """PropertyListSerializer includes correct fields"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')
        serializer = PropertyListSerializer(prop_list)

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('owner', data)
        self.assertIn('title', data)
        self.assertIn('state', data)
        self.assertIn('properties_count', data)
        self.assertIn('status_summary', data)

    def test_property_list_serializer_read_only_fields(self):
        """PropertyListSerializer marks correct fields as read-only"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')
        serializer = PropertyListSerializer(prop_list)

        # UUID should be read-only
        self.assertIn('uuid', serializer.data)


class PropertySerializerTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

    def test_property_serializer_fields(self):
        """PropertySerializer includes correct fields"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)

        from rest_framework.request import Request
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        request = factory.get('/')
        request.user = self.user

        serializer = PropertySerializer(prop, context={'request': request})

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('property_lists', data)
        self.assertIn('state', data)
        self.assertIn('state_display', data)
        self.assertIn('title', data)
        self.assertIn('postcode', data)


# ==========================
# API Endpoint Tests
# ==========================

class PropertyListAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_create_property_list(self):
        """POST /api/property/property-lists/ creates new list"""
        data = {'title': 'My Properties'}
        response = self.client.post('/api/property/property-lists/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'My Properties')
        self.assertEqual(response.data['owner'], 'testuser')
        self.assertEqual(response.data['state'], 'DRAFT')
        self.assertIn('uuid', response.data)

    def test_list_property_lists(self):
        """GET /api/property/property-lists/ returns user's lists"""
        PropertyList.objects.create(owner=self.user, title='List 1')
        PropertyList.objects.create(owner=self.user, title='List 2')

        response = self.client.get('/api/property/property-lists/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_property_list_by_uuid(self):
        """GET /api/property/property-lists/{uuid}/ returns list"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')

        response = self.client.get(f'/api/property/property-lists/{prop_list.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test List')
        self.assertIn('properties', response.data)  # Detail serializer

    def test_update_property_list(self):
        """PATCH /api/property/property-lists/{uuid}/ updates list"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Old Title')

        data = {'title': 'New Title'}
        response = self.client.patch(f'/api/property/property-lists/{prop_list.uuid}/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'New Title')

    def test_delete_property_list(self):
        """DELETE /api/property/property-lists/{uuid}/ deletes list"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')

        response = self.client.delete(f'/api/property/property-lists/{prop_list.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(PropertyList.objects.filter(uuid=prop_list.uuid).exists())

    def test_activate_property_list(self):
        """POST /api/property/property-lists/{uuid}/activate/ transitions state"""
        prop_list = PropertyList.objects.create(owner=self.user, title='Test List')

        response = self.client.post(f'/api/property/property-lists/{prop_list.uuid}/activate/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['state'], 'ACTIVE')

        prop_list.refresh_from_db()
        self.assertEqual(prop_list.state, 'ACTIVE')

    def test_cannot_access_other_user_list(self):
        """User cannot access another user's property lists"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        other_list = PropertyList.objects.create(owner=other_user, title='Other List')

        response = self.client.get(f'/api/property/property-lists/{other_list.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class PropertyAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

    def test_create_property(self):
        """POST /api/property/properties/ creates new property"""
        data = {
            'property_lists_input': [str(self.property_list.uuid)],
            'title': 'Modern Flat',
            'address_line_1': '123 Test St',
            'postcode': 'SW1A 1AA',
            'price': '450000.00',
            'bedrooms': 2,
            'bathrooms': 1,
            'garden': True
        }
        response = self.client.post('/api/property/properties/', data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['title'], 'Modern Flat')
        self.assertEqual(response.data['state'], 'NEW')
        self.assertIn('uuid', response.data)

    def test_list_properties(self):
        """GET /api/property/properties/ returns user's properties"""
        prop1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop1.property_lists.add(self.property_list)

        prop2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 1AB',
            price=200000,
            bedrooms=3,
            bathrooms=2
        )
        prop2.property_lists.add(self.property_list)

        response = self.client.get('/api/property/properties/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_filter_properties_by_list_uuid(self):
        """GET /api/property/properties/?property_list={uuid} filters"""
        list2 = PropertyList.objects.create(owner=self.user, title='List 2')

        prop1 = Property.objects.create(
            title='Property in List 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop1.property_lists.add(self.property_list)

        prop2 = Property.objects.create(
            title='Property in List 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 1AB',
            price=200000,
            bedrooms=3,
            bathrooms=2
        )
        prop2.property_lists.add(list2)

        response = self.client.get(f'/api/property/properties/?property_list={self.property_list.uuid}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['title'], 'Property in List 1')

    def test_retrieve_property_by_uuid(self):
        """GET /api/property/properties/{uuid}/ returns property"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)

        response = self.client.get(f'/api/property/properties/{prop.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['title'], 'Test Property')
        self.assertIn('context_data', response.data)  # Detail serializer
        self.assertIn('available_transitions', response.data)

    @patch('property.tasks.retrieve_context_data.delay')
    def test_run_stage2(self, mock_task):
        """POST /api/property/properties/{uuid}/run_stage2/ triggers Stage 2"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)

        response = self.client.post(f'/api/property/properties/{prop.uuid}/run_stage2/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['state'], 'STAGE2_IN_PROGRESS')

        prop.refresh_from_db()
        self.assertEqual(prop.state, 'STAGE2_IN_PROGRESS')

        # Verify Celery task queued
        mock_task.assert_called_once_with(prop.id)

    @patch('property.tasks.calculate_property_rating.delay')
    def test_run_stage3(self, mock_task):
        """POST /api/property/properties/{uuid}/run_stage3/ triggers Stage 3"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)
        # Advance to STAGE2_COMPLETE
        prop.run_stage2()
        prop.save()
        prop.complete_stage2()
        prop.save()

        response = self.client.post(f'/api/property/properties/{prop.uuid}/run_stage3/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['state'], 'STAGE3_IN_PROGRESS')

        # Verify Celery task queued
        mock_task.assert_called_once_with(prop.id)

    @patch('property.tasks.retrieve_context_data.delay')
    def test_rerun_services(self, mock_task):
        """POST /api/property/properties/{uuid}/rerun_services/ reruns Stage 2"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)
        # Advance to STAGE2_COMPLETE
        prop.run_stage2()
        prop.save()
        prop.complete_stage2()
        prop.save()

        response = self.client.post(f'/api/property/properties/{prop.uuid}/rerun_services/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['state'], 'STAGE2_IN_PROGRESS')

        # Verify Celery task queued
        mock_task.assert_called_once_with(prop.id)

    def test_cannot_run_stage3_from_new(self):
        """Cannot skip Stage 2 via API"""
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )
        prop.property_lists.add(self.property_list)

        response = self.client.post(f'/api/property/properties/{prop.uuid}/run_stage3/')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class SavedLocationAPITest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

    def test_create_saved_location(self):
        """POST /api/property/saved-locations/ creates location"""
        data = {
            'name': 'Work Office',
            'address': '10 Downing Street, London',
            'latitude': '51.5034',
            'longitude': '-0.1276'
        }
        response = self.client.post('/api/property/saved-locations/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'Work Office')
        self.assertIn('uuid', response.data)

    def test_list_saved_locations(self):
        """GET /api/property/saved-locations/ returns user's locations"""
        SavedLocation.objects.create(
            user=self.user,
            name='Location 1',
            address='Address 1',
            latitude=51.5,
            longitude=-0.1
        )
        SavedLocation.objects.create(
            user=self.user,
            name='Location 2',
            address='Address 2',
            latitude=51.6,
            longitude=-0.2
        )

        response = self.client.get('/api/property/saved-locations/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)


# ==========================
# Permission Tests
# ==========================

class PermissionTest(APITestCase):
    def test_unauthenticated_cannot_access_property_lists(self):
        """Unauthenticated users cannot access API"""
        response = self.client.get('/api/property/property-lists/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unauthenticated_cannot_create_property(self):
        """Unauthenticated users cannot create properties"""
        data = {'title': 'Test'}
        response = self.client.post('/api/property/properties/', data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
