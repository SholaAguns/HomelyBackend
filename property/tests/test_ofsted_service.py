"""
Tests for OfstedService
"""
from unittest.mock import Mock, patch
from django.test import TestCase
from django.core.cache import cache

from property.services.ofsted_service import OfstedService


class OfstedServiceTest(TestCase):
    """Test OfstedService scraping and caching"""

    def setUp(self):
        """Clear cache before each test"""
        cache.clear()

    def tearDown(self):
        """Clear cache after each test"""
        cache.clear()

    @patch('property.services.ofsted_service.requests.get')
    def test_get_ofsted_report_success(self, mock_get):
        """Test successful Ofsted report retrieval"""
        # Mock HTML response
        html_content = """
        <html>
            <title>The Aldgate School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>The overall outcome of the inspection on 12 June 2024 was:</p>
                <strong>Outstanding</strong>
            </div>
            <div class="subjudgements__rates">
                <div class="subjudgements__rates__item">
                    <p>Quality of education:</p>
                    <strong>Outstanding</strong>
                </div>
                <div class="subjudgements__rates__item">
                    <p>Behaviour and attitudes:</p>
                    <strong>Outstanding</strong>
                </div>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('100000')

        # Verify
        self.assertNotIn('error', result)
        self.assertEqual(result['urn'], '100000')
        self.assertEqual(result['school_name'], 'The Aldgate School')
        self.assertEqual(result['overall_rating'], 'Outstanding')
        self.assertEqual(result['inspection_date'], '2024-06-12')
        self.assertEqual(result['sub_judgements']['quality_of_education'], 'Outstanding')
        self.assertEqual(result['sub_judgements']['behaviour_and_attitudes'], 'Outstanding')
        self.assertIn('report_url', result)
        self.assertFalse(result['cached'])

    @patch('property.services.ofsted_service.requests.get')
    def test_get_ofsted_report_not_found(self, mock_get):
        """Test 404 response for non-existent school"""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('999999')

        # Verify
        self.assertEqual(result['error'], 'School not found')
        self.assertEqual(result['urn'], '999999')

    @patch('property.services.ofsted_service.requests.get')
    def test_get_ofsted_report_network_error(self, mock_get):
        """Test network error handling"""
        mock_get.side_effect = Exception('Connection timeout')

        # Test
        result = OfstedService.get_ofsted_report('100000')

        # Verify
        self.assertEqual(result['error'], 'Parse error')
        self.assertEqual(result['urn'], '100000')

    @patch('property.services.ofsted_service.requests.get')
    def test_get_ofsted_report_caching(self, mock_get):
        """Test that results are cached"""
        html_content = """
        <html>
            <title>Test School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>The overall outcome of the inspection on 1 January 2024 was:</p>
                <strong>Good</strong>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # First call
        result1 = OfstedService.get_ofsted_report('100001')
        self.assertFalse(result1['cached'])

        # Second call (should be cached)
        result2 = OfstedService.get_ofsted_report('100001')
        self.assertTrue(result2['cached'])

        # Should only call requests.get once
        self.assertEqual(mock_get.call_count, 1)

    @patch('property.services.ofsted_service.requests.get')
    def test_parse_missing_overall_rating(self, mock_get):
        """Test parsing when overall rating is missing"""
        html_content = """
        <html>
            <title>Test School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>No rating available</p>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('100002')

        # Verify
        self.assertEqual(result['error'], 'Could not parse Ofsted rating')

    @patch('property.services.ofsted_service.requests.get')
    def test_parse_sub_judgements(self, mock_get):
        """Test parsing all sub-judgements"""
        html_content = """
        <html>
            <title>Test School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>The overall outcome of the inspection on 15 March 2024 was:</p>
                <strong>Good</strong>
            </div>
            <div class="subjudgements__rates">
                <div class="subjudgements__rates__item">
                    <p>Quality of education:</p>
                    <strong>Good</strong>
                </div>
                <div class="subjudgements__rates__item">
                    <p>Behaviour and attitudes:</p>
                    <strong>Good</strong>
                </div>
                <div class="subjudgements__rates__item">
                    <p>Personal development:</p>
                    <strong>Outstanding</strong>
                </div>
                <div class="subjudgements__rates__item">
                    <p>Leadership and management:</p>
                    <strong>Good</strong>
                </div>
                <div class="subjudgements__rates__item">
                    <p>Early years provision:</p>
                    <strong>Good</strong>
                </div>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('100003')

        # Verify all sub-judgements parsed
        self.assertEqual(len(result['sub_judgements']), 5)
        self.assertEqual(result['sub_judgements']['quality_of_education'], 'Good')
        self.assertEqual(result['sub_judgements']['behaviour_and_attitudes'], 'Good')
        self.assertEqual(result['sub_judgements']['personal_development'], 'Outstanding')
        self.assertEqual(result['sub_judgements']['leadership_and_management'], 'Good')
        self.assertEqual(result['sub_judgements']['early_years_provision'], 'Good')

    @patch('property.services.ofsted_service.requests.get')
    def test_parse_requires_improvement(self, mock_get):
        """Test parsing 'Requires improvement' rating"""
        html_content = """
        <html>
            <title>Test School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>The overall outcome of the inspection on 1 May 2024 was:</p>
                <strong>Requires improvement</strong>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('100004')

        # Verify
        self.assertEqual(result['overall_rating'], 'Requires improvement')

    @patch('property.services.ofsted_service.requests.get')
    def test_clear_cache(self, mock_get):
        """Test cache clearing"""
        html_content = """
        <html>
            <title>Test School - Open - Find an Inspection Report - Ofsted</title>
            <div class="subjudgements__overall">
                <p>The overall outcome of the inspection on 1 January 2024 was:</p>
                <strong>Good</strong>
            </div>
        </html>
        """

        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = html_content
        mock_get.return_value = mock_response

        # Cache data
        OfstedService.get_ofsted_report('100005')

        # Clear cache
        OfstedService.clear_cache('100005')

        # Fetch again (should hit API)
        result = OfstedService.get_ofsted_report('100005')
        self.assertFalse(result['cached'])

        # Should call requests.get twice (once before clear, once after)
        self.assertEqual(mock_get.call_count, 2)

    @patch('property.services.ofsted_service.requests.get')
    def test_http_500_error(self, mock_get):
        """Test handling of HTTP 500 error"""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response

        # Test
        result = OfstedService.get_ofsted_report('100006')

        # Verify
        self.assertEqual(result['error'], 'HTTP 500')

    def test_cache_key_format(self):
        """Test cache key format is consistent"""
        # This is tested implicitly in caching tests
        # Cache key should be "ofsted:{urn}"
        urn = '100007'
        cache_key = f"ofsted:{urn}"

        # Set and get
        test_data = {'test': 'data'}
        cache.set(cache_key, test_data, timeout=60)
        cached = cache.get(cache_key)

        self.assertEqual(cached, test_data)
