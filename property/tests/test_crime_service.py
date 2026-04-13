"""
Tests for CrimeService
"""
from unittest.mock import Mock, patch
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User
import requests

from property.models import Property, PropertyList, Project
from property.services.context_retrieval import CrimeService


class CrimeServiceTest(TestCase):
    """Test CrimeService implementation"""

    def setUp(self):
        """Set up test fixtures"""
        # Create user and property list
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
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

        # Create test property with valid UK postcode and coordinates
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

        self.service = CrimeService()

    def test_service_name(self):
        """Test service name returns 'crime'"""
        self.assertEqual(self.service.get_service_name(), 'crime')

    def test_cache_key_format(self):
        """Test cache key uses postcode sector (first 4 chars)"""
        cache_key = self.service.get_cache_key(self.property)
        self.assertEqual(cache_key, 'crime:SW1A')

    def test_cache_ttl(self):
        """Test cache TTL is 30 days"""
        expected_ttl = 86400 * 30  # 30 days in seconds
        self.assertEqual(self.service.get_cache_ttl(), expected_ttl)

    def test_validate_property_data_success(self):
        """Test validation passes with valid property"""
        result = self.service.validate_property_data(self.property)
        self.assertTrue(result)

    def test_validate_property_data_missing_postcode(self):
        """Test validation fails without postcode"""
        property_no_postcode = Property.objects.create(
            title='No Postcode Property',
            address_line_1='456 Test Ave',
            city='London',
            postcode='',
            latitude=Decimal('51.5074'),
            longitude=Decimal('-0.1278'),
            price=Decimal('400000.00')
        )

        with self.assertRaises(ValueError) as context:
            self.service.validate_property_data(property_no_postcode)

        self.assertIn('postcode', str(context.exception))

    def test_validate_property_data_missing_coordinates(self):
        """Test validation fails without coordinates"""
        property_no_coords = Property.objects.create(
            title='No Coords Property',
            address_line_1='789 Test Rd',
            city='London',
            postcode='SW1A 2BB',
            latitude=None,
            longitude=None,
            price=Decimal('350000.00')
        )

        with self.assertRaises(ValueError) as context:
            self.service.validate_property_data(property_no_coords)

        self.assertIn('latitude', str(context.exception).lower())

    @patch('property.services.context_retrieval.crime_service.requests.get')
    def test_fetch_data_with_mock(self, mock_get):
        """Test fetch_data with mocked API responses"""
        # Mock locate-neighbourhood response
        mock_locate = Mock()
        mock_locate.status_code = 200
        mock_locate.json.return_value = {
            'force': 'metropolitan',
            'neighbourhood': 'E01000001'
        }

        # Mock boundary response
        mock_boundary = Mock()
        mock_boundary.status_code = 200
        mock_boundary.json.return_value = [
            {'latitude': '51.507', 'longitude': '-0.127'},
            {'latitude': '51.508', 'longitude': '-0.128'},
        ]

        # Mock crimes response
        mock_crimes = Mock()
        mock_crimes.status_code = 200
        mock_crimes.json.return_value = [
            {'category': 'anti-social-behaviour'},
            {'category': 'burglary'},
            {'category': 'anti-social-behaviour'},
        ]

        # Set up mock to return different responses
        mock_get.side_effect = [mock_locate, mock_boundary] + [mock_crimes] * 12

        # Fetch data
        result = self.service.fetch_data(self.property)

        # Verify result structure
        self.assertIn('total_crimes', result)
        self.assertIn('crime_rating', result)
        self.assertIn('categories', result)
        self.assertIn('months_analyzed', result)

        # With 3 crimes per month for 12 months = 36 crimes
        # Average per month = 3
        self.assertEqual(result['months_analyzed'], 12)

    def test_format_category_name(self):
        """Test category name formatting"""
        formatted = self.service._format_category_name('anti-social-behaviour')
        self.assertEqual(formatted, 'Anti-social behaviour')

        formatted = self.service._format_category_name('violent-crime')
        self.assertEqual(formatted, 'Violence and sexual offences')

    def test_get_top_categories(self):
        """Test getting top categories by count"""
        categories = {
            'Burglary': 10,
            'Anti-social behaviour': 25,
            'Vehicle crime': 5,
            'Theft': 15,
            'Violence': 20
        }

        top_3 = self.service._get_top_categories(categories, 3)

        self.assertEqual(len(top_3), 3)
        self.assertEqual(top_3[0]['category'], 'Anti-social behaviour')
        self.assertEqual(top_3[0]['count'], 25)
        self.assertEqual(top_3[1]['category'], 'Violence')
        self.assertEqual(top_3[1]['count'], 20)

    def test_analyze_crime_data_empty(self):
        """Test crime analysis with no data"""
        monthly_breakdown = [{'month': '2026-03', 'crime_count': 0, 'status': 'success'}]
        result = self.service._analyze_crime_data([], monthly_breakdown)

        self.assertEqual(result['total_crimes'], 0)
        self.assertEqual(result['crime_rating'], 'Very Low')
        self.assertEqual(result['categories'], {})

    def test_analyze_crime_data_rating_thresholds(self):
        """Test crime rating thresholds"""
        # Create mock monthly breakdown for 12 successful months
        monthly_breakdown = [
            {'month': f'2026-{i:02d}', 'crime_count': 10, 'status': 'success'}
            for i in range(1, 13)
        ]

        # Very Low: < 5 per month
        crimes_very_low = [{'category': 'burglary'}] * 40  # 40/12 = 3.3 per month
        result = self.service._analyze_crime_data(crimes_very_low, monthly_breakdown)
        self.assertEqual(result['crime_rating'], 'Very Low')

        # Low: 5-15 per month
        crimes_low = [{'category': 'burglary'}] * 120  # 120/12 = 10 per month
        result = self.service._analyze_crime_data(crimes_low, monthly_breakdown)
        self.assertEqual(result['crime_rating'], 'Low')

        # Moderate: 15-30 per month
        crimes_moderate = [{'category': 'burglary'}] * 240  # 240/12 = 20 per month
        result = self.service._analyze_crime_data(crimes_moderate, monthly_breakdown)
        self.assertEqual(result['crime_rating'], 'Moderate')

        # High: 30-50 per month
        crimes_high = [{'category': 'burglary'}] * 480  # 480/12 = 40 per month
        result = self.service._analyze_crime_data(crimes_high, monthly_breakdown)
        self.assertEqual(result['crime_rating'], 'High')

        # Very High: >= 50 per month
        crimes_very_high = [{'category': 'burglary'}] * 720  # 720/12 = 60 per month
        result = self.service._analyze_crime_data(crimes_very_high, monthly_breakdown)
        self.assertEqual(result['crime_rating'], 'Very High')

    @patch('property.services.context_retrieval.crime_service.requests.get')
    def test_fetch_crimes_partial_failure(self, mock_get):
        """Test _fetch_crimes_by_location handles partial month failures"""
        # Mock responses: 10 successful, 2 failures
        successful_response = Mock()
        successful_response.status_code = 200
        successful_response.raise_for_status = Mock()
        successful_response.json.return_value = [
            {'category': 'burglary'},
            {'category': 'anti-social-behaviour'}
        ]

        # Create HTTPError for 404 response
        failed_response = Mock()
        failed_response.status_code = 404
        http_error = requests.exceptions.HTTPError()
        http_error.response = failed_response
        failed_response.raise_for_status = Mock(side_effect=http_error)
        failed_response.json.return_value = []

        # Create side effect: 10 success, 2 failures
        mock_get.side_effect = [successful_response] * 10 + [failed_response] * 2

        result = self.service._fetch_crimes_by_location('51.5,-0.1', months_range=13)

        # Verify structure
        self.assertIn('crimes', result)
        self.assertIn('monthly_breakdown', result)
        self.assertIn('successful_months', result)
        self.assertIn('failed_months', result)

        # Verify counts
        self.assertEqual(result['successful_months'], 10)
        self.assertEqual(result['failed_months'], 2)
        self.assertEqual(len(result['monthly_breakdown']), 12)

        # Verify we got crimes from successful months (10 months * 2 crimes each)
        self.assertEqual(len(result['crimes']), 20)

        # Verify monthly breakdown has correct statuses
        successful_count = sum(1 for m in result['monthly_breakdown'] if m['status'] == 'success')
        failed_count = sum(1 for m in result['monthly_breakdown'] if m['status'] == 'failed')
        self.assertEqual(successful_count, 10)
        self.assertEqual(failed_count, 2)

    @patch('property.services.context_retrieval.crime_service.requests.get')
    def test_fetch_crimes_all_months_fail(self, mock_get):
        """Test _fetch_crimes_by_location raises error when all months fail"""
        # Create HTTPError for 500 response
        failed_response = Mock()
        failed_response.status_code = 500
        http_error = requests.exceptions.HTTPError("Server error")
        http_error.response = failed_response
        failed_response.raise_for_status = Mock(side_effect=http_error)

        mock_get.return_value = failed_response

        with self.assertRaises(Exception) as context:
            self.service._fetch_crimes_by_location('51.5,-0.1', months_range=13)

        self.assertIn('all months', str(context.exception))

    def test_analyze_crime_data_includes_monthly_breakdown(self):
        """Test _analyze_crime_data includes monthly_breakdown in response"""
        monthly_breakdown = [
            {'month': '2026-03', 'crime_count': 10, 'status': 'success'},
            {'month': '2026-02', 'crime_count': None, 'status': 'failed', 'error': 'No data'}
        ]
        crimes = [{'category': 'burglary'}] * 10

        result = self.service._analyze_crime_data(crimes, monthly_breakdown)

        self.assertIn('monthly_breakdown', result)
        self.assertEqual(len(result['monthly_breakdown']), 2)
        self.assertEqual(result['months_analyzed'], 1)  # Only 1 successful month
