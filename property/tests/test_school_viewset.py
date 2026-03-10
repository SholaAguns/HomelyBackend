"""
Tests for SchoolViewSet (Ofsted endpoint)
"""
from unittest.mock import patch
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status

User = get_user_model()


class SchoolViewSetTest(TestCase):
    """Test SchoolViewSet endpoints"""

    def setUp(self):
        """Set up test client and user"""
        self.client = APIClient()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.client.force_authenticate(user=self.user)

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_get_ofsted_report_success(self, mock_get_report):
        """Test successful Ofsted report retrieval"""
        # Mock service response
        mock_get_report.return_value = {
            'urn': '100000',
            'school_name': 'The Aldgate School',
            'overall_rating': 'Outstanding',
            'inspection_date': '2024-06-12',
            'sub_judgements': {
                'quality_of_education': 'Outstanding',
                'behaviour_and_attitudes': 'Outstanding',
            },
            'report_url': 'https://reports.ofsted.gov.uk/provider/21/100000',
            'fetched_at': '2024-01-01T12:00:00',
            'cached': False
        }

        # Test
        response = self.client.get('/api/schools/ofsted/100000/')

        # Verify
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['urn'], '100000')
        self.assertEqual(response.data['overall_rating'], 'Outstanding')
        mock_get_report.assert_called_once_with('100000')

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_get_ofsted_report_not_found(self, mock_get_report):
        """Test 404 response for non-existent school"""
        # Mock service response
        mock_get_report.return_value = {
            'error': 'School not found',
            'urn': '999999',
            'url': 'https://reports.ofsted.gov.uk/provider/21/999999',
            'cached': False
        }

        # Test
        response = self.client.get('/api/schools/ofsted/999999/')

        # Verify
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(response.data['error'], 'School not found')

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_get_ofsted_report_server_error(self, mock_get_report):
        """Test 500 response for server errors"""
        # Mock service response
        mock_get_report.return_value = {
            'error': 'Network error',
            'urn': '100000',
            'cached': False
        }

        # Test
        response = self.client.get('/api/schools/ofsted/100000/')

        # Verify
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(response.data['error'], 'Network error')

    def test_ofsted_report_requires_authentication(self):
        """Test endpoint requires authentication"""
        # Unauthenticated client
        client = APIClient()

        # Test
        response = client.get('/api/schools/ofsted/100000/')

        # Verify
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_get_ofsted_report_cached_response(self, mock_get_report):
        """Test cached Ofsted report includes cached flag"""
        # Mock cached response
        mock_get_report.return_value = {
            'urn': '100001',
            'school_name': 'Test School',
            'overall_rating': 'Good',
            'inspection_date': '2024-01-01',
            'sub_judgements': {},
            'report_url': 'https://reports.ofsted.gov.uk/provider/21/100001',
            'fetched_at': '2024-01-01T12:00:00',
            'cached': True
        }

        # Test
        response = self.client.get('/api/schools/ofsted/100001/')

        # Verify
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['cached'])
