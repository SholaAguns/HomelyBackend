"""
Tests for SchoolRatingService
"""
from unittest.mock import Mock, patch
from decimal import Decimal
from django.test import TestCase
from django.contrib.auth.models import User

from property.models import Property, PropertyList, Project, School
from property.services.context_retrieval import SchoolRatingService


class SchoolRatingServiceTest(TestCase):
    """Test SchoolRatingService implementation"""

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

        # Create test property in London
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

        # Create test schools
        self.school_primary_close = School.objects.create(
            urn='100001',
            name='Close Primary School',
            establishment_status='Open',
            postcode='SW1A 2BB',
            latitude=Decimal('51.5084'),  # ~1km away
            longitude=Decimal('-0.1268'),
            phase='Primary',
            type_of_establishment='Community school',
            pupil_count=200,
            school_capacity=210,
            gender='Mixed'
        )

        self.school_secondary_close = School.objects.create(
            urn='100002',
            name='Close Secondary School',
            establishment_status='Open',
            postcode='SW1A 3CC',
            latitude=Decimal('51.5064'),  # ~1.5km away
            longitude=Decimal('-0.1288'),
            phase='Secondary',
            type_of_establishment='Academy',
            pupil_count=800,
            school_capacity=900,
            gender='Mixed'
        )

        self.school_primary_far = School.objects.create(
            urn='100003',
            name='Far Primary School',
            establishment_status='Open',
            postcode='SW2A 1AA',
            latitude=Decimal('51.5274'),  # ~2.5km away
            longitude=Decimal('-0.1478'),
            phase='Primary',
            type_of_establishment='Voluntary aided school',
            pupil_count=150
        )

        self.school_closed = School.objects.create(
            urn='100004',
            name='Closed School',
            establishment_status='Closed',
            postcode='SW1A 4DD',
            latitude=Decimal('51.5074'),
            longitude=Decimal('-0.1278'),
            phase='Primary'
        )

        self.service = SchoolRatingService()

    def test_service_name(self):
        """Test service name returns 'schools'"""
        self.assertEqual(self.service.get_service_name(), 'schools')

    def test_cache_key_format(self):
        """Test cache key uses postcode"""
        cache_key = self.service.get_cache_key(self.property)
        self.assertEqual(cache_key, 'schools:SW1A 1AA')

    def test_cache_ttl(self):
        """Test cache TTL is 90 days"""
        expected_ttl = 86400 * 90  # 90 days in seconds
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

    def test_fetch_data_returns_nearby_schools(self):
        """Test fetch_data returns schools within radius"""
        result = self.service.fetch_data(self.property)

        # Check structure
        self.assertIn('primary_schools', result)
        self.assertIn('secondary_schools', result)
        self.assertIn('statistics', result)

        # Should find primary and secondary schools
        self.assertGreater(len(result['primary_schools']), 0)
        self.assertGreater(len(result['secondary_schools']), 0)

        # Check primary school data structure
        primary = result['primary_schools'][0]
        self.assertIn('urn', primary)
        self.assertIn('name', primary)
        self.assertIn('distance_km', primary)
        self.assertIn('distance_miles', primary)
        self.assertIn('phase', primary)
        self.assertIn('pupil_count', primary)

    def test_fetch_data_excludes_closed_schools(self):
        """Test that closed schools are not included"""
        result = self.service.fetch_data(self.property)

        all_schools = (result['primary_schools'] +
                      result['secondary_schools'] +
                      result['all_through_schools'])

        # No closed schools should be in results
        for school in all_schools:
            self.assertNotEqual(school['urn'], '100004')

    def test_fetch_data_separates_by_phase(self):
        """Test schools are correctly separated by phase"""
        result = self.service.fetch_data(self.property)

        # Primary schools should only be primary phase
        for school in result['primary_schools']:
            self.assertIn('Primary', school['phase'])

        # Secondary schools should only be secondary phase
        for school in result['secondary_schools']:
            self.assertIn('Secondary', school['phase'])

    def test_fetch_data_sorts_by_distance(self):
        """Test schools are sorted by distance (closest first)"""
        result = self.service.fetch_data(self.property)

        # Check primary schools are sorted
        if len(result['primary_schools']) > 1:
            for i in range(len(result['primary_schools']) - 1):
                self.assertLessEqual(
                    result['primary_schools'][i]['distance_km'],
                    result['primary_schools'][i + 1]['distance_km']
                )

    def test_fetch_data_includes_statistics(self):
        """Test statistics are calculated correctly"""
        result = self.service.fetch_data(self.property)

        stats = result['statistics']

        # Check required statistics fields
        self.assertIn('total_schools_found', stats)
        self.assertIn('primary_count', stats)
        self.assertIn('secondary_count', stats)
        self.assertIn('search_radius_km', stats)
        self.assertIn('closest_primary_km', stats)
        self.assertIn('closest_secondary_km', stats)

        # Verify counts match
        self.assertEqual(
            stats['primary_count'],
            len(result['primary_schools'])
        )
        self.assertEqual(
            stats['secondary_count'],
            len(result['secondary_schools'])
        )

    def test_fetch_data_respects_max_schools_limit(self):
        """Test maximum schools per phase limit is enforced"""
        # Create 15 primary schools within radius
        for i in range(15):
            School.objects.create(
                urn=f'20000{i}',
                name=f'Primary School {i}',
                establishment_status='Open',
                postcode='SW1A 1AA',
                latitude=Decimal('51.5074') + Decimal(i * 0.001),
                longitude=Decimal('-0.1278') + Decimal(i * 0.001),
                phase='Primary',
                type_of_establishment='Community school'
            )

        result = self.service.fetch_data(self.property)

        # Should not exceed MAX_SCHOOLS_PER_PHASE
        self.assertLessEqual(
            len(result['primary_schools']),
            SchoolRatingService.MAX_SCHOOLS_PER_PHASE
        )

    def test_fetch_data_calculates_distances_correctly(self):
        """Test distance calculations are in expected range"""
        result = self.service.fetch_data(self.property)

        for school in result['primary_schools']:
            # Distance should be positive
            self.assertGreater(school['distance_km'], 0)

            # Miles should be less than km
            self.assertLess(school['distance_miles'], school['distance_km'])

            # Conversion factor check (roughly 0.621)
            ratio = school['distance_miles'] / school['distance_km']
            self.assertAlmostEqual(ratio, 0.621371, delta=0.01)

    def test_fetch_data_includes_ofsted_url(self):
        """Test Ofsted URL is included in response"""
        result = self.service.fetch_data(self.property)

        if result['primary_schools']:
            school = result['primary_schools'][0]
            self.assertIn('ofsted_url', school)
            self.assertIn('reports.ofsted.gov.uk', school['ofsted_url'])
            self.assertIn(school['urn'], school['ofsted_url'])

    def test_fetch_data_no_schools_nearby(self):
        """Test behavior when no schools are within radius"""
        # Create property in remote location
        remote_property = Property.objects.create(
            title='Remote Property',
            address_line_1='Remote Location',
            city='Remote',
            postcode='ZZ99 9ZZ',
            latitude=Decimal('60.0'),
            longitude=Decimal('-5.0'),
            price=Decimal('200000.00')
        )
        remote_property.property_lists.add(self.property_list)

        result = self.service.fetch_data(remote_property)

        # Should return empty lists
        self.assertEqual(len(result['primary_schools']), 0)
        self.assertEqual(len(result['secondary_schools']), 0)

        # Statistics should reflect no schools
        self.assertEqual(result['statistics']['total_schools_found'], 0)
        self.assertIsNone(result['statistics']['closest_primary_km'])

    def test_fetch_data_note_about_ofsted(self):
        """Test response includes note about Ofsted"""
        with patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report') as mock_ofsted:
            # Mock Ofsted responses
            mock_ofsted.return_value = {
                'overall_rating': 'Good',
                'inspection_date': '2024-01-01',
                'sub_judgements': {},
                'cached': False
            }

            result = self.service.fetch_data(self.property)

            self.assertIn('note', result)
            self.assertIn('Ofsted', result['note'])

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_fetch_data_includes_ofsted_ratings(self, mock_ofsted):
        """Test Ofsted ratings are fetched and included for each school"""
        # Mock Ofsted response
        mock_ofsted.return_value = {
            'overall_rating': 'Outstanding',
            'inspection_date': '2024-06-12',
            'sub_judgements': {
                'quality_of_education': 'Outstanding',
                'behaviour_and_attitudes': 'Outstanding'
            },
            'cached': False
        }

        result = self.service.fetch_data(self.property)

        # Check that schools have Ofsted data
        if result['primary_schools']:
            school = result['primary_schools'][0]
            self.assertIn('ofsted', school)
            self.assertIsNotNone(school['ofsted'])
            self.assertEqual(school['ofsted']['overall_rating'], 'Outstanding')
            self.assertEqual(school['ofsted']['inspection_date'], '2024-06-12')
            self.assertIn('sub_judgements', school['ofsted'])

        # Verify Ofsted service was called for each school
        self.assertGreater(mock_ofsted.call_count, 0)

    @patch('property.services.context_retrieval.ofsted_service.OfstedService.get_ofsted_report')
    def test_fetch_data_handles_ofsted_errors_gracefully(self, mock_ofsted):
        """Test that Ofsted errors don't break school service"""
        # Mock Ofsted error
        mock_ofsted.return_value = {
            'error': 'School not found',
            'urn': '100001'
        }

        result = self.service.fetch_data(self.property)

        # Should still return schools even if Ofsted fails
        if result['primary_schools']:
            school = result['primary_schools'][0]
            self.assertIn('ofsted', school)
            # Should have error field
            self.assertIn('error', school['ofsted'])
            self.assertEqual(school['ofsted']['overall_rating'], None)
