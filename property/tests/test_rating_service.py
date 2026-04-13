"""
Tests for Stage 3 Rating Service
Tests all 5 scoring strategies, dealbreaker evaluation, and rating aggregation
"""
from decimal import Decimal
from unittest import skip
from django.test import TestCase
from django.contrib.auth.models import User
from property.models import (
    Project, PropertyList, Property, RatingCriteria, Criterion,
    CriterionScore, ContextData, SavedLocation
)
from property.services.rating_service import RatingService, calculate_and_persist_rating


class RatingServiceTestCase(TestCase):
    """Base test case with common setup"""

    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create project and property list
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )

        # Create test properties
        self.property1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=Decimal('300000'),
            bedrooms=2,
            bathrooms=1,
            square_area=Decimal('500'),
            garden=True,
            parking=False,
            council_tax_band='B',
            epc_rating='C',
            state='STAGE2_COMPLETE'
        )
        self.property1.property_lists.add(self.property_list)

        self.property2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 2BB',
            price=Decimal('400000'),
            bedrooms=3,
            bathrooms=2,
            square_area=Decimal('750'),
            garden=False,
            parking=True,
            council_tax_band='D',
            epc_rating='B',
            state='STAGE2_COMPLETE'
        )
        self.property2.property_lists.add(self.property_list)

        self.property3 = Property.objects.create(
            title='Property 3',
            address_line_1='789 Test Rd',
            postcode='SW1A 3CC',
            price=Decimal('500000'),
            bedrooms=4,
            bathrooms=3,
            square_area=Decimal('1000'),
            garden=True,
            parking=True,
            council_tax_band='E',
            epc_rating='A',
            state='STAGE2_COMPLETE'
        )
        self.property3.property_lists.add(self.property_list)

        # Create rating criteria
        self.rating_criteria = RatingCriteria.objects.create(
            owner=self.user,
            name='Test Criteria'
        )
        self.project.rating_criteria = self.rating_criteria
        self.project.save()


class BedroomScoringTests(RatingServiceTestCase):
    """Tests for _score_bedrooms() - threshold-based scoring"""

    def test_bedroom_scoring_thresholds(self):
        """Test bedroom scoring uses correct thresholds (4=100, 3=75, 2=50, 1=25, 0=0)"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        # Test property1 (2 bedrooms) - should score 50
        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_bedrooms(criterion)
        self.assertEqual(raw_value, 2)
        self.assertEqual(score, Decimal('50.0'))

        # Test property2 (3 bedrooms) - should score 75
        service = RatingService(self.property2, self.rating_criteria)
        raw_value, score = service._score_bedrooms(criterion)
        self.assertEqual(raw_value, 3)
        self.assertEqual(score, Decimal('75.0'))

        # Test property3 (4 bedrooms) - should score 100
        service = RatingService(self.property3, self.rating_criteria)
        raw_value, score = service._score_bedrooms(criterion)
        self.assertEqual(raw_value, 4)
        self.assertEqual(score, Decimal('100.0'))


class BathroomScoringTests(RatingServiceTestCase):
    """Tests for _score_bathrooms() - threshold-based scoring"""

    def test_bathroom_scoring(self):
        """Test bathroom scoring uses threshold-based scoring"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bathrooms',
            source='property',
            field_name='bathrooms',
            weight=Decimal('1.0')
        )

        # Test property1 (1 bathroom)
        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_bathrooms(criterion)
        self.assertEqual(raw_value, 1)
        self.assertGreater(score, Decimal('0'))
        self.assertLessEqual(score, Decimal('100'))

        # Test property3 (3 bathrooms) should score higher than property1
        service = RatingService(self.property3, self.rating_criteria)
        raw_value3, score3 = service._score_bathrooms(criterion)
        self.assertEqual(raw_value3, 3)
        self.assertGreater(score3, score)  # More bathrooms = higher score


class PriceScoringTests(RatingServiceTestCase):
    """Tests for _score_price() - inverted min-max (lower is better)"""

    def test_price_scoring_without_search_criteria(self):
        """Test price scoring calculates from properties when no search criteria"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        # Properties: £300k, £400k, £500k
        # property1 = £300k (lowest, should score 100 since lower is better)
        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_price(criterion)
        self.assertEqual(raw_value, Decimal('300000'))
        self.assertEqual(score, Decimal('100.00'))  # Lowest price = best score

        # property3 = £500k (highest, should score 0)
        service = RatingService(self.property3, self.rating_criteria)
        raw_value, score = service._score_price(criterion)
        self.assertEqual(raw_value, Decimal('500000'))
        self.assertEqual(score, Decimal('0.00'))  # Highest price = worst score


class CouncilTaxScoringTests(RatingServiceTestCase):
    """Tests for _score_council_tax() - ordinal band scoring from context data"""

    def test_council_tax_scoring(self):
        """Test council tax scoring extracts band from context and scores correctly"""
        from property.models import ContextData

        # Create context data for property1
        ContextData.objects.create(
            property=self.property1,
            service_name='council_tax',
            status='COMPLETE',
            data={'band': 'B', 'annual_amount': 1500}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Council Tax',
            source='context_report',
            field_name='council_tax',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_council_tax(criterion)

        self.assertEqual(raw_value, 'B')
        self.assertEqual(score, Decimal('85'))  # Band B = 85

    def test_council_tax_different_bands(self):
        """Test different council tax bands score correctly"""
        from property.models import ContextData

        # Test Band A (best)
        ContextData.objects.create(
            property=self.property1,
            service_name='council_tax',
            status='COMPLETE',
            data={'band': 'A'}
        )

        # Test Band H (worst)
        ContextData.objects.create(
            property=self.property2,
            service_name='council_tax',
            status='COMPLETE',
            data={'band': 'H'}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Council Tax',
            source='context_report',
            field_name='council_tax',
            weight=Decimal('1.0')
        )

        # Band A should score 100
        service = RatingService(self.property1, self.rating_criteria)
        _, score_a = service._score_council_tax(criterion)
        self.assertEqual(score_a, Decimal('100'))

        # Band H should score 0
        service = RatingService(self.property2, self.rating_criteria)
        _, score_h = service._score_council_tax(criterion)
        self.assertEqual(score_h, Decimal('0'))


class CrimeScoringTests(RatingServiceTestCase):
    """Tests for _score_crime() - ordinal crime rating scoring from context data"""

    def test_crime_scoring(self):
        """Test crime scoring extracts rating from context and scores correctly"""
        from property.models import ContextData

        ContextData.objects.create(
            property=self.property1,
            service_name='crime',
            status='COMPLETE',
            data={'crime_rating': 'Low', 'total_crimes': 50}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Crime Rating',
            source='context_report',
            field_name='crime',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_crime(criterion)

        self.assertEqual(raw_value, 'Low')
        self.assertEqual(score, Decimal('75'))  # Low = 75

    def test_crime_rating_levels(self):
        """Test different crime rating levels score correctly"""
        from property.models import ContextData

        # Very Low (best)
        ContextData.objects.create(
            property=self.property1,
            service_name='crime',
            status='COMPLETE',
            data={'crime_rating': 'Very Low'}
        )

        # Very High (worst)
        ContextData.objects.create(
            property=self.property2,
            service_name='crime',
            status='COMPLETE',
            data={'crime_rating': 'Very High'}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Crime',
            source='context_report',
            field_name='crime',
            weight=Decimal('1.0')
        )

        # Very Low should score 100
        service = RatingService(self.property1, self.rating_criteria)
        _, score_low = service._score_crime(criterion)
        self.assertEqual(score_low, Decimal('100'))

        # Very High should score 0
        service = RatingService(self.property2, self.rating_criteria)
        _, score_high = service._score_crime(criterion)
        self.assertEqual(score_high, Decimal('0'))


class MobileScoringTests(RatingServiceTestCase):
    """Tests for _score_mobile() - mobile coverage scoring from context data"""

    def test_mobile_coverage_scoring(self):
        """Test mobile coverage scoring extracts overall_coverage from context"""
        from property.models import ContextData

        ContextData.objects.create(
            property=self.property1,
            service_name='mobile',
            status='COMPLETE',
            data={'scores': {'overall_coverage': 85.5}}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Mobile Coverage',
            source='context_report',
            field_name='mobile',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_mobile(criterion)

        self.assertEqual(raw_value, 85.5)
        self.assertEqual(score, Decimal('85.50'))  # Score is the coverage value itself


class BroadbandScoringTests(RatingServiceTestCase):
    """Tests for _score_broadband() - threshold-based broadband speed scoring"""

    def test_broadband_speed_scoring(self):
        """Test broadband speed scoring uses thresholds correctly"""
        from property.models import ContextData

        # Test with 150 Mbps (should score 75)
        ContextData.objects.create(
            property=self.property1,
            service_name='broadband',
            status='COMPLETE',
            data={'max_download_mbps': 150}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Broadband Speed',
            source='context_report',
            field_name='broadband',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_broadband(criterion)

        self.assertEqual(raw_value, 150)
        self.assertEqual(score, Decimal('75.0'))  # 100-300 Mbps = 75

    def test_broadband_speed_thresholds(self):
        """Test broadband scoring threshold ranges"""
        from property.models import ContextData

        # Test 350 Mbps (>300, should score 100)
        ContextData.objects.create(
            property=self.property1,
            service_name='broadband',
            status='COMPLETE',
            data={'max_download_mbps': 350}
        )

        # Test 50 Mbps (30-100 range, should score 50)
        ContextData.objects.create(
            property=self.property2,
            service_name='broadband',
            status='COMPLETE',
            data={'max_download_mbps': 50}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Broadband',
            source='context_report',
            field_name='broadband',
            weight=Decimal('1.0')
        )

        # 350 Mbps should score 100
        service = RatingService(self.property1, self.rating_criteria)
        _, score_high = service._score_broadband(criterion)
        self.assertEqual(score_high, Decimal('100.0'))

        # 50 Mbps should score 50
        service = RatingService(self.property2, self.rating_criteria)
        _, score_mid = service._score_broadband(criterion)
        self.assertEqual(score_mid, Decimal('50.0'))


class SavedLocationDistanceScoringTests(RatingServiceTestCase):
    """Tests for _score_saved_location_distance() - distance-based scoring"""

    def test_saved_location_distance_scoring(self):
        """Test distance to saved location scoring"""
        from property.models import ContextData, SavedLocation

        # Create saved location
        saved_loc = SavedLocation.objects.create(
            user=self.user,
            name='Work',
            postcode='SW1A 1AA',
            address_line_1='10 Downing St',
            city='London',
            latitude=51.5034,
            longitude=-0.1276
        )

        # Create context data with distance to saved location
        # Expected structure: distances array with location_uuid, location_name, distance_km
        ContextData.objects.create(
            property=self.property1,
            service_name='saved_locations',
            status='COMPLETE',
            data={
                'distances': [
                    {
                        'location_uuid': str(saved_loc.uuid),
                        'location_name': 'Work',
                        'distance_km': 2.5,
                        'distance_miles': 1.55
                    }
                ]
            }
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Distance to Work',
            source='context_report',
            field_name='saved_locations',
            saved_location_uuid=saved_loc.uuid,
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_saved_location_distance(criterion)

        self.assertEqual(raw_value, 2.5)
        # 2.5km is in 1-3km range, should score 80
        self.assertEqual(score, Decimal('80.0'))


class POIDistanceScoringTests(RatingServiceTestCase):
    """Tests for _score_poi_distance() - POI distance scoring"""

    def test_poi_distance_scoring(self):
        """Test distance to POI scoring"""
        from property.models import ContextData

        # Create context data with POI distances
        # Expected structure: poi_types object with category keys, places need 'straight_distance_km'
        ContextData.objects.create(
            property=self.property1,
            service_name='poi',
            status='COMPLETE',
            data={
                'poi_types': {
                    'supermarket': [
                        {
                            'name': 'Tesco',
                            'straight_distance_km': 0.8,
                            'distance_miles': 0.5
                        }
                    ]
                }
            }
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Distance to Supermarket',
            source='context_report',
            field_name='poi',
            poi_category='supermarket',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        raw_value, score = service._score_poi_distance(criterion)

        self.assertEqual(raw_value, 0.8)
        # 0.8km is in 0-1km range, should score 100
        self.assertEqual(score, Decimal('100.00'))


class OrdinalScoringTests(RatingServiceTestCase):
    """Tests for ordinal mapping scoring"""

    @skip("ordinal_mapping field removed from Criterion model - scoring uses hardcoded logic. Re-enable when configurable mappings are supported.")
    def test_ordinal_council_tax(self):
        """Test ordinal mapping for council tax bands"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Council Tax Band',
            source='property',
            field_name='council_tax_band',
            ordinal_mapping={
                'A': 100, 'B': 90, 'C': 80, 'D': 70,
                'E': 60, 'F': 50, 'G': 40, 'H': 30
            },
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)

        # Property1 has band B
        score_b = service._score_ordinal('B', criterion)
        self.assertEqual(score_b, Decimal('90'))

        # Property2 has band D
        score_d = service._score_ordinal('D', criterion)
        self.assertEqual(score_d, Decimal('70'))

        # Property3 has band E
        score_e = service._score_ordinal('E', criterion)
        self.assertEqual(score_e, Decimal('60'))

    @skip("ordinal_mapping field removed from Criterion model - scoring uses hardcoded logic. Re-enable when configurable mappings are supported.")
    def test_ordinal_crime_rating(self):
        """Test ordinal mapping for crime ratings"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Crime Rating',
            source='context',
            field_name='crime',
            data_path='rating',
            ordinal_mapping={'Low': 100, 'Medium': 50, 'High': 0},
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)

        score_low = service._score_ordinal('Low', criterion)
        self.assertEqual(score_low, Decimal('100'))

        score_medium = service._score_ordinal('Medium', criterion)
        self.assertEqual(score_medium, Decimal('50'))

        score_high = service._score_ordinal('High', criterion)
        self.assertEqual(score_high, Decimal('0'))

    @skip("ordinal_mapping field removed from Criterion model - scoring uses hardcoded logic. Re-enable when configurable mappings are supported.")
    def test_ordinal_missing_value(self):
        """Test ordinal mapping with unknown value returns 0"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Test Ordinal',
            source='property',
            field_name='council_tax_band',
            ordinal_mapping={'A': 100, 'B': 90},
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        score = service._score_ordinal('Z', criterion)
        self.assertEqual(score, Decimal('0'))


class BooleanScoringTests(RatingServiceTestCase):
    """Tests for boolean scoring"""

    @skip("Boolean scoring with boolean_true_is_better field removed from Criterion model")
    def test_boolean_true_is_better(self):
        """Test boolean scoring where True is better"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Garden',
            source='property',
            field_name='garden',
            weight=Decimal('0.5')
        )

        service = RatingService(self.property1, self.rating_criteria)

        score_true = service._score_boolean(True, criterion)
        self.assertEqual(score_true, Decimal('100.00'))

        score_false = service._score_boolean(False, criterion)
        self.assertEqual(score_false, Decimal('0.00'))

    @skip("Boolean scoring with boolean_true_is_better field removed from Criterion model")
    def test_boolean_false_is_better(self):
        """Test boolean scoring where False is better"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Test Inverse Boolean',
            source='property',
            field_name='parking',
            weight=Decimal('0.5')
        )

        service = RatingService(self.property1, self.rating_criteria)

        score_true = service._score_boolean(True, criterion)
        self.assertEqual(score_true, Decimal('0.00'))

        score_false = service._score_boolean(False, criterion)
        self.assertEqual(score_false, Decimal('100.00'))


class ThresholdScoringTests(RatingServiceTestCase):
    """Tests for threshold-based scoring"""

    @skip("Threshold scoring not yet implemented - thresholds field removed from Criterion model. Re-enable when threshold scoring is supported.")
    def test_threshold_scoring(self):
        """Test threshold-based scoring with distance ranges"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Distance to Station',
            source='calculated',
            thresholds=[
                [0, 100],
                [500, 75],
                [1000, 50],
                [2000, 25]
            ],
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)

        # Test various distances
        score_0 = service._score_threshold(0, criterion)
        self.assertEqual(score_0, Decimal('100'))

        score_300 = service._score_threshold(300, criterion)
        self.assertEqual(score_300, Decimal('100'))

        score_750 = service._score_threshold(750, criterion)
        self.assertEqual(score_750, Decimal('75'))

        score_1500 = service._score_threshold(1500, criterion)
        self.assertEqual(score_1500, Decimal('50'))

        score_2500 = service._score_threshold(2500, criterion)
        self.assertEqual(score_2500, Decimal('25'))

        score_3000 = service._score_threshold(3000, criterion)
        self.assertEqual(score_3000, Decimal('25'))  # Still matches 2000 threshold


class DealbrekerTests(RatingServiceTestCase):
    """Tests for dealbreaker evaluation"""

    def test_dealbreaker_pass(self):
        """Test property passing dealbreaker"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Min Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '>=', 'value': 2}
        )

        service = RatingService(self.property2, self.rating_criteria)
        passed, reason = service.evaluate_dealbreakers()

        self.assertTrue(passed)
        self.assertIsNone(reason)

    def test_dealbreaker_fail(self):
        """Test property failing dealbreaker"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Max Price',
            source='property',
            field_name='price',
            weight=Decimal('1.5'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '<=', 'value': 350000}
        )

        # property2 has price of £400k, should fail
        service = RatingService(self.property2, self.rating_criteria)
        passed, reason = service.evaluate_dealbreakers()

        self.assertFalse(passed)
        self.assertIn('Max Price', reason)

    @skip("Test uses 'parking' field which is not yet supported by RatingService. Re-enable when boolean field scoring (garden, parking) is implemented.")
    def test_multiple_dealbreakers(self):
        """Test multiple dealbreakers"""
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Min Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '>=', 'value': 2}
        )

        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Must Have Parking',
            source='property',
            field_name='parking',
            weight=Decimal('0.5'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '==', 'value': True}
        )

        # property1 has 2 bedrooms but no parking - should fail
        service = RatingService(self.property1, self.rating_criteria)
        passed, reason = service.evaluate_dealbreakers()

        self.assertFalse(passed)
        self.assertIn('Parking', reason)

    def test_dealbreaker_operators(self):
        """Test various dealbreaker operators"""
        service = RatingService(self.property1, self.rating_criteria)

        # Test >= operator
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Test >=',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0'),
            dealbreaker_threshold={'operator': '>=', 'value': 2}
        )
        self.assertTrue(service._meets_dealbreaker_threshold(2, criterion))
        self.assertFalse(service._meets_dealbreaker_threshold(1, criterion))

        # Test > operator
        criterion.dealbreaker_threshold = {'operator': '>', 'value': 2}
        self.assertFalse(service._meets_dealbreaker_threshold(2, criterion))
        self.assertTrue(service._meets_dealbreaker_threshold(3, criterion))

        # Test <= operator
        criterion.dealbreaker_threshold = {'operator': '<=', 'value': 3}
        self.assertTrue(service._meets_dealbreaker_threshold(3, criterion))
        self.assertFalse(service._meets_dealbreaker_threshold(4, criterion))

        # Test < operator
        criterion.dealbreaker_threshold = {'operator': '<', 'value': 3}
        self.assertTrue(service._meets_dealbreaker_threshold(2, criterion))
        self.assertFalse(service._meets_dealbreaker_threshold(3, criterion))

        # Test == operator
        criterion.dealbreaker_threshold = {'operator': '==', 'value': 2}
        self.assertTrue(service._meets_dealbreaker_threshold(2, criterion))
        self.assertFalse(service._meets_dealbreaker_threshold(3, criterion))

        # Test != operator
        criterion.dealbreaker_threshold = {'operator': '!=', 'value': 2}
        self.assertFalse(service._meets_dealbreaker_threshold(2, criterion))
        self.assertTrue(service._meets_dealbreaker_threshold(3, criterion))


class RawValueExtractionTests(RatingServiceTestCase):
    """Tests for raw value extraction"""

    def test_extract_from_property(self):
        """Test extracting value from property field"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        value = service.extract_raw_value(criterion)

        self.assertEqual(value, Decimal('300000'))

    @skip("ContextData uses 'service_name' not 'field_name', and Criterion no longer has 'data_path' field. Re-enable when configurable data paths are supported.")
    def test_extract_from_context(self):
        """Test extracting value from context data"""
        # Create context data
        ContextData.objects.create(
            property=self.property1,
            field_name='crime',
            status='COMPLETE',
            data={'rating': 'Low', 'score': 25}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Crime Rating',
            source='context',
            field_name='crime',
            data_path='rating',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        value = service.extract_raw_value(criterion)

        self.assertEqual(value, 'Low')

    @skip("ContextData uses 'service_name' not 'field_name', and Criterion no longer has 'data_path' field. Re-enable when configurable data paths are supported.")
    def test_extract_from_context_nested_path(self):
        """Test extracting nested value from context data"""
        ContextData.objects.create(
            property=self.property1,
            field_name='broadband',
            status='COMPLETE',
            data={'speeds': {'max': 100, 'avg': 75}}
        )

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Broadband Speed',
            source='context',
            field_name='broadband',
            data_path='speeds.max',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        value = service.extract_raw_value(criterion)

        self.assertEqual(value, 100)

    @skip("data_path field removed from Criterion model - scoring methods use hardcoded paths. Re-enable when configurable paths are supported.")
    def test_extract_context_not_available(self):
        """Test error when context data not available"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Crime Rating',
            source='context',
            field_name='crime',
            data_path='rating',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)

        with self.assertRaises(ValueError):
            service.extract_raw_value(criterion)


class OverallRatingTests(RatingServiceTestCase):
    """Tests for overall rating calculation"""

    @skip("Test uses 'garden' field which is not yet supported by RatingService. Re-enable when boolean field scoring (garden, parking) is implemented.")
    def test_calculate_overall_rating(self):
        """Test full rating calculation with multiple criteria"""
        # Create criteria
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.5')
        )

        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Garden',
            source='property',
            field_name='garden',
            weight=Decimal('0.5')
        )

        # Calculate rating for property2
        service = RatingService(self.property2, self.rating_criteria)
        overall, breakdown, disqualified, reason = service.calculate_rating()

        # Verify result structure
        self.assertFalse(disqualified)
        self.assertIsNone(reason)
        self.assertIn('Price', breakdown)
        self.assertIn('Bedrooms', breakdown)
        self.assertIn('Garden', breakdown)

        # Verify overall rating is calculated correctly
        self.assertGreater(overall, Decimal('0'))
        self.assertLessEqual(overall, Decimal('100'))

    def test_rating_with_dealbreaker_fail(self):
        """Test rating calculation when dealbreaker fails"""
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Max Price',
            source='property',
            field_name='price',
            weight=Decimal('1.5'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '<=', 'value': 350000}
        )

        # property3 has price £500k, should be disqualified
        service = RatingService(self.property3, self.rating_criteria)
        overall, breakdown, disqualified, reason = service.calculate_rating()

        self.assertTrue(disqualified)
        self.assertIsNotNone(reason)
        self.assertEqual(overall, Decimal('0.00'))

    def test_rating_with_zero_weight_criterion(self):
        """Test that zero-weight criteria are included in breakdown but not in overall calculation"""
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('0.0')  # Zero weight
        )

        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        overall, breakdown, disqualified, reason = service.calculate_rating()

        # Price should be in breakdown (for debugging) but with weight=0
        self.assertIn('Price', breakdown)
        self.assertEqual(breakdown['Price']['weight'], 0.0)
        self.assertEqual(breakdown['Price']['weighted_score'], 0.0)
        self.assertIn('Bedrooms', breakdown)

        # Overall rating should only be based on Bedrooms (non-zero weight)
        self.assertGreater(overall, Decimal('0'))


class CalculateAndPersistTests(RatingServiceTestCase):
    """Tests for calculate_and_persist_rating function"""

    def test_calculate_and_persist_rating(self):
        """Test full calculation and persistence"""
        # Create criterion
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        # Calculate and persist
        result = calculate_and_persist_rating(self.property1.id)

        # Check return value
        self.assertIn('overall_rating', result)
        self.assertIn('breakdown', result)
        self.assertFalse(result['disqualified'])

        # Check property was updated
        self.property1.refresh_from_db()
        self.assertIsNotNone(self.property1.overall_rating)
        self.assertIsNotNone(self.property1.rating_breakdown)
        self.assertFalse(self.property1.disqualified)

        # Check criterion scores were created
        scores = CriterionScore.objects.filter(property=self.property1)
        self.assertEqual(scores.count(), 2)

    def test_persist_rating_with_disqualification(self):
        """Test persistence when property is disqualified"""
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Max Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0'),
            is_dealbreaker=True,
            dealbreaker_threshold={'operator': '<=', 'value': 250000}
        )

        result = calculate_and_persist_rating(self.property1.id)

        # Check disqualification
        self.assertTrue(result['disqualified'])
        self.assertIsNotNone(result['disqualification_reason'])

        # Check property
        self.property1.refresh_from_db()
        self.assertEqual(self.property1.overall_rating, Decimal('0.00'))
        self.assertTrue(self.property1.disqualified)
        self.assertIn('Max Price', self.property1.disqualification_reason)

    def test_no_rating_criteria_configured(self):
        """Test error when no rating criteria configured"""
        # Clear rating criteria
        self.project.rating_criteria = None
        self.project.save()

        with self.assertRaises(ValueError) as context:
            calculate_and_persist_rating(self.property1.id)

        self.assertIn('No rating criteria', str(context.exception))
