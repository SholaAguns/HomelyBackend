"""
Tests for Rightmove integration API endpoints.
Tests phase 3 & 4 implementation (bulk creation, progress tracking, enhanced create-from-input).
"""
from django.test import TestCase, TransactionTestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch, MagicMock
from decimal import Decimal

from property.models import Property, PropertyList, SearchCriteria, PropertyListTask
from property.tests.mocks.rightmove_mock import MockRightmoveService


class CreateFromSearchEndpointTest(TransactionTestCase):
    """Test POST /api/property-lists/{uuid}/create-from-search/ endpoint"""

    def setUp(self):
        from rest_framework.test import APIClient
        self.client = APIClient()

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

    @patch('property.tasks.scrape_rightmove_properties.delay')
    def test_create_from_search_creates_task(self, mock_task):
        """Endpoint creates PropertyListTask and queues Celery task"""
        data = {
            'search_criteria': {
                'area': 'Manchester',
                'bedrooms_min': 2,
                'bedrooms_max': 4,
                'price_min': 800,
                'price_max': 2000,
                'radius': 10
            },
            'max_properties': 50
        }

        response = self.client.post(
            f'/api/property/property-lists/{self.property_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('uuid', response.data)
        self.assertEqual(response.data['task_type'], 'SCRAPE_SEARCH')
        self.assertEqual(response.data['status'], 'QUEUED')
        self.assertIn('websocket_url', response.data)

        # Check PropertyListTask created
        tasks = PropertyListTask.objects.filter(property_list=self.property_list)
        self.assertEqual(tasks.count(), 1)

        task = tasks.first()
        self.assertEqual(task.task_type, 'SCRAPE_SEARCH')
        self.assertEqual(task.status, 'QUEUED')

        # Check SearchCriteria created and linked
        self.property_list.refresh_from_db()
        self.assertIsNotNone(self.property_list.search_criteria)
        self.assertEqual(self.property_list.search_criteria.area, 'Manchester')
        self.assertEqual(self.property_list.search_criteria.bedrooms_min, 2)
        self.assertEqual(self.property_list.search_criteria.price_max, 2000)

        # Check Celery task queued
        mock_task.assert_called_once()
        call_args = mock_task.call_args
        self.assertEqual(call_args[0][0], str(task.uuid))
        self.assertEqual(call_args[1]['max_properties'], 50)

    @patch('property.tasks.scrape_rightmove_properties.delay')
    def test_create_from_search_updates_existing_criteria(self, mock_task):
        """Endpoint updates existing SearchCriteria if already exists"""
        # Create existing search criteria
        existing_criteria = SearchCriteria.objects.create(
            area='London',
            bedrooms_min=1
        )
        self.property_list.search_criteria = existing_criteria
        self.property_list.save()

        # Update with new criteria
        data = {
            'search_criteria': {
                'area': 'Manchester',  # Changed
                'bedrooms_min': 2,
                'price_max': 1500
            }
        }

        response = self.client.post(
            f'/api/property/property-lists/{self.property_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)

        # Check criteria updated (not new one created)
        existing_criteria.refresh_from_db()
        self.assertEqual(existing_criteria.area, 'Manchester')
        self.assertEqual(existing_criteria.bedrooms_min, 2)
        self.assertEqual(existing_criteria.price_max, 1500)

        # Should still be only one SearchCriteria
        self.assertEqual(SearchCriteria.objects.count(), 1)

    def test_create_from_search_validates_criteria(self):
        """Endpoint validates search criteria"""
        # Missing required 'area' field
        data = {
            'search_criteria': {
                'bedrooms_min': 2
            }
        }

        response = self.client.post(
            f'/api/property/property-lists/{self.property_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_from_search_validates_min_max(self):
        """Endpoint validates min/max ranges"""
        data = {
            'search_criteria': {
                'area': 'Manchester',
                'bedrooms_min': 5,
                'bedrooms_max': 2  # Invalid: min > max
            }
        }

        response = self.client.post(
            f'/api/property/property-lists/{self.property_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('bedrooms_min', str(response.data))

    def test_create_from_search_requires_authentication(self):
        """Endpoint requires authentication"""
        self.client.credentials()  # Remove auth

        data = {
            'search_criteria': {
                'area': 'Manchester'
            }
        }

        response = self.client.post(
            f'/api/property/property-lists/{self.property_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_from_search_cant_access_other_user_list(self):
        """User cannot create search for another user's list"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        other_list = PropertyList.objects.create(
            owner=other_user,
            title='Other List'
        )

        data = {
            'search_criteria': {
                'area': 'Manchester'
            }
        }

        response = self.client.post(
            f'/api/property/property-lists/{other_list.uuid}/create-from-search/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class ScrapeStatusEndpointTest(APITestCase):
    """Test GET /api/property-lists/{uuid}/scrape-status/{task_uuid}/ endpoint"""

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

        self.task = PropertyListTask.objects.create(
            property_list=self.property_list,
            task_type='SCRAPE_SEARCH',
            status='IN_PROGRESS',
            total_items=50,
            completed_items=25,
            failed_items=2
        )

    def test_get_scrape_status(self):
        """Endpoint returns current task status"""
        response = self.client.get(
            f'/api/property/property-lists/{self.property_list.uuid}/scrape-status/{self.task.uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['uuid'], str(self.task.uuid))
        self.assertEqual(response.data['status'], 'IN_PROGRESS')
        self.assertEqual(response.data['total_items'], 50)
        self.assertEqual(response.data['completed_items'], 25)
        self.assertEqual(response.data['failed_items'], 2)
        self.assertEqual(response.data['progress_percentage'], 50)
        self.assertIn('websocket_url', response.data)

    def test_get_scrape_status_task_not_found(self):
        """Endpoint returns 404 for non-existent task"""
        invalid_uuid = '00000000-0000-0000-0000-000000000000'

        response = self.client.get(
            f'/api/property/property-lists/{self.property_list.uuid}/scrape-status/{invalid_uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_get_scrape_status_requires_authentication(self):
        """Endpoint requires authentication"""
        self.client.credentials()  # Remove auth

        response = self.client.get(
            f'/api/property/property-lists/{self.property_list.uuid}/scrape-status/{self.task.uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_scrape_status_cant_access_other_user_task(self):
        """User cannot access another user's task status"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        other_list = PropertyList.objects.create(
            owner=other_user,
            title='Other List'
        )
        other_task = PropertyListTask.objects.create(
            property_list=other_list,
            task_type='SCRAPE_SEARCH',
            status='COMPLETED'
        )

        response = self.client.get(
            f'/api/property/property-lists/{other_list.uuid}/scrape-status/{other_task.uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)


class EnhancedCreateFromInputEndpointTest(APITestCase):
    """Test enhanced POST /api/property/properties/create-from-input/ endpoint"""

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

    @patch('requests.get')
    def test_create_from_input_extract_only_mode(self, mock_get):
        """Endpoint extracts data without creating Property (original behavior)"""
        # Setup mock
        mock_html = MockRightmoveService.get_mock_next_data_html('123456')
        mock_get.return_value = MagicMock(
            content=mock_html.encode('cp1252'),
            status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        # No property_list_uuid provided
        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url'
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        # Check response
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertIn('property_data', response.data)
        self.assertNotIn('property', response.data)
        self.assertEqual(response.data['source'], 'RightmoveService')

        # Check no Property created
        self.assertEqual(Property.objects.count(), 0)

    @patch('requests.get')
    def test_create_from_input_auto_create_mode(self, mock_get):
        """Endpoint creates Property when property_list_uuid provided"""
        # Setup mock
        mock_html = MockRightmoveService.get_mock_next_data_html('123456')
        mock_get.return_value = MagicMock(
            content=mock_html.encode('cp1252'),
            status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        # With property_list_uuid
        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url',
            'property_list_uuid': str(self.property_list.uuid)
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        # Check response
        if response.status_code != status.HTTP_201_CREATED:
            print(f"Error response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(response.data['success'])
        self.assertTrue(response.data['created'])
        self.assertIn('property', response.data)
        self.assertEqual(response.data['property']['external_id'], '123456')
        self.assertEqual(response.data['property']['state'], 'NEW')

        # Check Property created
        self.assertEqual(Property.objects.count(), 1)
        prop = Property.objects.first()
        self.assertEqual(prop.external_id, '123456')
        self.assertIn(self.property_list, prop.property_lists.all())
        self.assertIn('Manchester', prop.title)

    @patch('requests.get')
    def test_create_from_input_updates_duplicate(self, mock_get):
        """Endpoint updates existing property with same external_id"""
        # Create existing property
        existing = Property.objects.create(
            external_id='123456',
            title='Old Title',
            address_line_1='Old Address',
            postcode='M1 1AA',
            price=Decimal('1000'),
            bedrooms=2,
            bathrooms=1
        )
        existing.property_lists.add(self.property_list)

        # Setup mock with updated data
        mock_html = MockRightmoveService.get_mock_next_data_html('123456')
        mock_get.return_value = MagicMock(
            content=mock_html.encode('cp1252'),
            status_code=200
        )
        mock_get.return_value.raise_for_status = MagicMock()

        # Try to create same property
        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url',
            'property_list_uuid': str(self.property_list.uuid)
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        # Check response indicates update
        if response.status_code != status.HTTP_200_OK:
            print(f"Error response: {response.data}")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['success'])
        self.assertFalse(response.data['created'])
        self.assertTrue(response.data['updated'])
        self.assertIn('already exists', response.data['message'])

        # Check property was updated (not duplicated)
        self.assertEqual(Property.objects.count(), 1)
        existing.refresh_from_db()
        self.assertIn('Manchester', existing.title)  # Updated from mock data

    def test_create_from_input_invalid_property_list(self):
        """Endpoint returns 404 for invalid property_list_uuid"""
        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url',
            'property_list_uuid': '00000000-0000-0000-0000-000000000000'
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_create_from_input_cannot_use_other_user_list(self):
        """User cannot create property in another user's list"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass123'
        )
        other_list = PropertyList.objects.create(
            owner=other_user,
            title='Other List'
        )

        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url',
            'property_list_uuid': str(other_list.uuid)
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertIn('not found or access denied', response.data['error'])

    @patch('requests.get')
    def test_create_from_input_handles_extraction_errors(self, mock_get):
        """Endpoint handles extraction errors gracefully"""
        # Setup mock to raise exception
        mock_get.side_effect = Exception('Network error')

        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url'
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_create_from_input_validates_input(self):
        """Endpoint validates required fields"""
        # Missing input_data
        data = {
            'input_type': 'url'
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_from_input_requires_authentication(self):
        """Endpoint requires authentication"""
        self.client.credentials()  # Remove auth

        data = {
            'input_data': 'https://www.rightmove.co.uk/properties/123456',
            'input_type': 'url'
        }

        response = self.client.post(
            '/api/property/properties/create-from-input/',
            data,
            format='json'
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class PropertyListTaskModelTest(TestCase):
    """Test PropertyListTask model"""

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

    def test_task_creation(self):
        """PropertyListTask created with correct defaults"""
        task = PropertyListTask.objects.create(
            property_list=self.property_list,
            task_type='SCRAPE_SEARCH'
        )

        self.assertEqual(task.status, 'QUEUED')
        self.assertEqual(task.total_items, 0)
        self.assertEqual(task.completed_items, 0)
        self.assertEqual(task.failed_items, 0)
        self.assertIsNotNone(task.uuid)
        self.assertIsInstance(task.errors, list)
        self.assertIsInstance(task.metadata, dict)

    def test_task_progress_percentage(self):
        """Task calculates progress percentage correctly"""
        task = PropertyListTask.objects.create(
            property_list=self.property_list,
            task_type='SCRAPE_SEARCH',
            total_items=100,
            completed_items=25
        )

        self.assertEqual(task.progress_percentage, 25)

        task.completed_items = 50
        self.assertEqual(task.progress_percentage, 50)

        # Edge case: total_items = 0
        task.total_items = 0
        self.assertEqual(task.progress_percentage, 0)

    def test_task_add_error(self):
        """Task can add errors to errors list"""
        task = PropertyListTask.objects.create(
            property_list=self.property_list,
            task_type='SCRAPE_SEARCH'
        )

        task.add_error('First error', {'context': 'test'})
        task.add_error('Second error')

        self.assertEqual(len(task.errors), 2)
        self.assertIn('First error', task.errors[0]['message'])
        self.assertIn('context', task.errors[0])
        self.assertIn('Second error', task.errors[1]['message'])

    def test_task_str_representation(self):
        """Task has readable string representation"""
        task = PropertyListTask.objects.create(
            property_list=self.property_list,
            task_type='SCRAPE_SEARCH',
            status='IN_PROGRESS'
        )

        str_repr = str(task)
        self.assertIn('Scrape from Search', str_repr)
        self.assertIn('In Progress', str_repr)
        self.assertIn('Test List', str_repr)
