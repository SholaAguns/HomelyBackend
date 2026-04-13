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


class MinMaxScoringTests(RatingServiceTestCase):
    """Tests for min-max normalization (higher is better)"""

    def test_min_max_scoring_bedrooms(self):
        """Test min-max scoring where higher is better"""
        # Create criterion for bedrooms
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        # Test scoring for property2 (3 bedrooms)
        # Range: 2-4 bedrooms
        # Score = (3 - 2) / (4 - 2) * 100 = 50
        service = RatingService(self.property2, self.rating_criteria)
        score = service._score_min_max(3, criterion)
        self.assertEqual(score, Decimal('50.00'))

        # Test min value
        score_min = service._score_min_max(2, criterion)
        self.assertEqual(score_min, Decimal('0.00'))

        # Test max value
        score_max = service._score_min_max(4, criterion)
        self.assertEqual(score_max, Decimal('100.00'))

    def test_min_max_all_equal(self):
        """Test min-max when all properties have same value"""
        # Set all properties to same bedroom count
        Property.objects.filter(property_lists=self.property_list).update(bedrooms=3)

        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Bedrooms',
            source='property',
            field_name='bedrooms',
            weight=Decimal('1.0')
        )

        service = RatingService(self.property1, self.rating_criteria)
        score = service._score_min_max(3, criterion)
        self.assertEqual(score, Decimal('100.00'))


class InvertedMinMaxScoringTests(RatingServiceTestCase):
    """Tests for inverted min-max normalization (lower is better)"""

    def test_inverted_min_max_price(self):
        """Test inverted min-max scoring where lower is better"""
        criterion = Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.5')
        )

        # Test scoring for property2 (£400k)
        # Range: £300k-£500k
        # Score = (500k - 400k) / (500k - 300k) * 100 = 50
        service = RatingService(self.property2, self.rating_criteria)
        score = service._score_inverted_min_max(Decimal('400000'), criterion)
        self.assertEqual(score, Decimal('50.00'))

        # Test min value (gets highest score)
        score_min = service._score_inverted_min_max(Decimal('300000'), criterion)
        self.assertEqual(score_min, Decimal('100.00'))

        # Test max value (gets lowest score)
        score_max = service._score_inverted_min_max(Decimal('500000'), criterion)
        self.assertEqual(score_max, Decimal('0.00'))


class OrdinalScoringTests(RatingServiceTestCase):
    """Tests for ordinal mapping scoring"""

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
