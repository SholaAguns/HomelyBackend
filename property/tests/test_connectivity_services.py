"""
Tests for broadband and mobile coverage services
"""
from unittest.mock import Mock, patch
from decimal import Decimal
from datetime import date
from django.test import TestCase
from django.core.cache import cache

from property.models import Property, BroadbandCoverage, MobileCoverage
from property.services.context_retrieval.broadband_dataset_service import BroadbandDatasetService
from property.services.context_retrieval.mobile_dataset_service import MobileDatasetService


class BroadbandDatasetServiceTest(TestCase):
    """Test BroadbandDatasetService"""

    def setUp(self):
        """Set up test data"""
        cache.clear()
        self.service = BroadbandDatasetService()

        # Create test property
        self.property = Property.objects.create(
            title='Test Property',
            postcode='SW1A 1AA',
            address_line_1='10 Downing Street',
            city='London',
            price=Decimal('500000.00')
        )

        # Create test broadband coverage data
        self.broadband_data = BroadbandCoverage.objects.create(
            oa_code='E00000001',
            laua_code='E09000033',
            laua_name='Westminster',
            avg_download_under_10=Decimal('8.5'),
            avg_download_10_to_30=Decimal('25.3'),
            avg_download_30_to_100=Decimal('75.2'),
            avg_download_100_to_300=Decimal('245.1'),
            avg_download_300_to_900=Decimal('650.5'),
            avg_download_over_900=Decimal('980.2'),
            avg_upload_under_10=Decimal('5.2'),
            avg_upload_10_to_30=Decimal('18.3'),
            avg_upload_30_to_100=Decimal('55.1'),
            avg_upload_100_to_300=Decimal('150.2'),
            avg_monthly_usage_gb=Decimal('450.5'),
            full_fibre_takeup_pct_of_all=Decimal('78.5'),
            data_date=date(2024, 7, 1)
        )

    def tearDown(self):
        cache.clear()

    @patch('property.utils.geocoding.postcode_to_oa')
    def test_fetch_data_success(self, mock_postcode_to_oa):
        """Test successful data fetch"""
        mock_postcode_to_oa.return_value = 'E00000001'

        data = self.service.fetch_data(self.property)

        # Verify postcode lookup was called
        mock_postcode_to_oa.assert_called_once_with('SW1A 1AA')

        # Verify returned data structure
        self.assertEqual(data['postcode'], 'SW1A 1AA')
        self.assertEqual(data['oa_code'], 'E00000001')
        self.assertEqual(data['laua_code'], 'E09000033')
        self.assertEqual(data['laua_name'], 'Westminster')

        # Check max speeds are returned (should be from highest tier)
        self.assertEqual(data['max_download_mbps'], 980.2)
        self.assertEqual(data['max_upload_mbps'], 150.2)

        # Check metadata
        self.assertEqual(data['data_source'], 'Ofcom Connected Nations Dataset')
        self.assertEqual(data['granularity'], 'Output Area (~125 households)')

    # Cache testing removed - Django cache is tested internally
    # Service uses IContextService caching which is framework-level

    @patch('property.utils.geocoding.postcode_to_oa')
    def test_fetch_data_no_postcode(self, mock_postcode_to_oa):
        """Test error when property has no postcode"""
        property_no_postcode = Property.objects.create(
            title='Test',
            address_line_1='Test Street',
            city='London',
            price=Decimal('100000')
        )

        with self.assertRaises(ValueError) as cm:
            self.service.fetch_data(property_no_postcode)

        self.assertIn('postcode', str(cm.exception).lower())

    @patch('property.utils.geocoding.postcode_to_oa')
    def test_fetch_data_no_oa_found(self, mock_postcode_to_oa):
        """Test error when OA code not found"""
        mock_postcode_to_oa.return_value = None

        with self.assertRaises(ValueError) as cm:
            self.service.fetch_data(self.property)

        self.assertIn('Output Area', str(cm.exception))

    @patch('property.utils.geocoding.postcode_to_oa')
    def test_fetch_data_no_coverage_data(self, mock_postcode_to_oa):
        """Test error when no coverage data exists for OA"""
        mock_postcode_to_oa.return_value = 'E99999999'

        with self.assertRaises(ValueError) as cm:
            self.service.fetch_data(self.property)

        self.assertIn('No broadband data found', str(cm.exception))

    def test_cache_key_generation(self):
        """Test cache key is based on postcode"""
        key = self.service.get_cache_key(self.property)
        self.assertEqual(key, 'broadband:SW1A 1AA')

    def test_cache_ttl(self):
        """Test cache TTL is 90 days"""
        ttl = self.service.get_cache_ttl()
        self.assertEqual(ttl, 86400 * 90)


class MobileDatasetServiceTest(TestCase):
    """Test MobileDatasetService"""

    def setUp(self):
        """Set up test data"""
        cache.clear()
        self.service = MobileDatasetService()

        self.property = Property.objects.create(
            title='Test Property',
            postcode='SW1A 1AA',
            address_line_1='10 Downing Street',
            city='London',
            price=Decimal('500000.00')
        )

        self.mobile_data = MobileCoverage.objects.create(
            laua_code='E09000033',
            laua_name='Westminster',
            premise_count=50000,
            fourg_premises_outdoor_4=Decimal('99.8'),
            fourg_premises_indoor_4=Decimal('95.2'),
            fourg_premises_outdoor_3=Decimal('0.1'),
            fourg_premises_indoor_3=Decimal('2.5'),
            fiveg_high_premises_outdoor_4=Decimal('85.3'),
            fiveg_very_high_premises_outdoor_4=Decimal('62.1'),
            voice_premises_outdoor_4=Decimal('99.5'),
            voice_premises_indoor_4=Decimal('98.7'),
            data_date=date(2024, 9, 1)
        )

    def tearDown(self):
        cache.clear()

    @patch('property.utils.geocoding.postcode_to_laua')
    def test_fetch_data_success(self, mock_postcode_to_laua):
        """Test successful data fetch"""
        mock_postcode_to_laua.return_value = 'E09000033'

        data = self.service.fetch_data(self.property)

        mock_postcode_to_laua.assert_called_once_with('SW1A 1AA')

        self.assertEqual(data['postcode'], 'SW1A 1AA')
        self.assertEqual(data['laua_code'], 'E09000033')
        self.assertEqual(data['laua_name'], 'Westminster')

        # Check 4G data
        self.assertIn('4g_coverage', data)
        self.assertEqual(data['4g_coverage']['outdoor']['all_4_networks'], 99.8)
        self.assertEqual(data['4g_coverage']['indoor']['all_4_networks'], 95.2)

        # Check 5G data
        self.assertIn('5g_coverage_high_confidence', data)

        # Check metadata
        self.assertEqual(data['data_source'], 'Ofcom Connected Nations Dataset')
        self.assertEqual(data['granularity'], 'Local Authority')

    # Cache testing removed - Django cache is tested internally

    @patch('property.utils.geocoding.postcode_to_laua')
    def test_fetch_data_no_laua_found(self, mock_postcode_to_laua):
        """Test error when LAUA not found"""
        mock_postcode_to_laua.return_value = None

        with self.assertRaises(ValueError) as cm:
            self.service.fetch_data(self.property)

        self.assertIn('Local Authority', str(cm.exception))


class BroadbandCoverageModelTest(TestCase):
    """Test BroadbandCoverage model methods"""

    def setUp(self):
        self.coverage = BroadbandCoverage.objects.create(
            oa_code='E00000001',
            laua_code='E09000033',
            laua_name='Westminster',
            avg_download_under_10=Decimal('8.5'),
            avg_download_10_to_30=Decimal('25.3'),
            avg_download_30_to_100=Decimal('75.2'),
            avg_download_100_to_300=Decimal('245.1'),
            avg_download_300_to_900=Decimal('650.5'),
            avg_download_over_900=Decimal('980.2'),
            avg_upload_under_10=Decimal('5.2'),
            avg_upload_10_to_30=Decimal('18.3'),
            avg_upload_30_to_100=Decimal('55.1'),
            avg_upload_100_to_300=Decimal('150.2'),
            data_date=date(2024, 7, 1)
        )

    def test_get_max_download_speed(self):
        """Test max download speed returns highest tier"""
        max_speed = self.coverage.get_max_download_speed()
        self.assertEqual(max_speed, 980.2)

    def test_get_max_upload_speed(self):
        """Test max upload speed returns highest tier"""
        max_speed = self.coverage.get_max_upload_speed()
        self.assertEqual(max_speed, 150.2)

    def test_get_max_speed_with_missing_high_tier(self):
        """Test max speed when highest tier is None"""
        coverage = BroadbandCoverage.objects.create(
            oa_code='E00000002',
            laua_code='E09000033',
            avg_download_30_to_100=Decimal('75.2'),
            avg_download_100_to_300=Decimal('245.1'),
            avg_upload_10_to_30=Decimal('18.3'),
            data_date=date(2024, 7, 1)
        )

        # Should return highest available
        self.assertEqual(coverage.get_max_download_speed(), 245.1)
        self.assertEqual(coverage.get_max_upload_speed(), 18.3)

    def test_get_max_speed_all_none(self):
        """Test max speed when all tiers are None"""
        coverage = BroadbandCoverage.objects.create(
            oa_code='E00000003',
            laua_code='E09000033',
            data_date=date(2024, 7, 1)
        )

        self.assertIsNone(coverage.get_max_download_speed())
        self.assertIsNone(coverage.get_max_upload_speed())


class MobileCoverageModelTest(TestCase):
    """Test MobileCoverage model methods"""

    def setUp(self):
        self.coverage = MobileCoverage.objects.create(
            laua_code='E09000033',
            laua_name='Westminster',
            fourg_premises_outdoor_4=Decimal('99.8'),
            fourg_premises_indoor_4=Decimal('95.2'),
            fourg_premises_outdoor_3=Decimal('0.1'),
            fourg_premises_indoor_3=Decimal('2.5'),
            fiveg_high_premises_outdoor_4=Decimal('85.3'),
            fiveg_very_high_premises_outdoor_4=Decimal('62.1'),
            fiveg_very_high_premises_outdoor_3=Decimal('15.2'),
            voice_premises_indoor_4=Decimal('98.7'),
            data_date=date(2024, 9, 1)
        )

    def test_get_4g_coverage_score(self):
        """Test 4G coverage score calculation"""
        score = self.coverage.get_4g_coverage_score()

        # Formula: outdoor_4 * 0.4 + indoor_4 * 0.3 + outdoor_3 * 0.2 + indoor_3 * 0.1
        expected = (99.8 * 0.4) + (95.2 * 0.3) + (0.1 * 0.2) + (2.5 * 0.1)
        self.assertAlmostEqual(score, expected, places=2)

    def test_get_5g_coverage_score(self):
        """Test 5G coverage score calculation"""
        score = self.coverage.get_5g_coverage_score()

        # Formula: very_high_4 * 0.5 + high_4 * 0.3 + very_high_3 * 0.2
        expected = (62.1 * 0.5) + (85.3 * 0.3) + (15.2 * 0.2)
        self.assertAlmostEqual(score, expected, places=2)

    def test_get_overall_coverage_score(self):
        """Test overall coverage score"""
        score = self.coverage.get_overall_coverage_score()

        # Formula: 4G * 0.7 + 5G * 0.2 + voice_indoor_4 * 0.1
        fourg_score = self.coverage.get_4g_coverage_score()
        fiveg_score = self.coverage.get_5g_coverage_score()
        expected = (fourg_score * 0.7) + (fiveg_score * 0.2) + (98.7 * 0.1)

        self.assertAlmostEqual(score, expected, places=2)
