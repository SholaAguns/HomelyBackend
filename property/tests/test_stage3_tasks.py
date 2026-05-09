"""
Tests for Stage 3 Rating Celery Tasks
"""
from decimal import Decimal
from unittest.mock import patch, MagicMock
from django.test import TestCase
from django.contrib.auth.models import User
from property.models import (
    Project, PropertyList, Property, RatingCriteria, Criterion
)
from property.tasks import (
    calculate_property_rating,
    bulk_calculate_ratings,
    bulk_calculate_project_ratings
)


class CalculatePropertyRatingTaskTest(TestCase):
    """Tests for calculate_property_rating task"""

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

        # Create rating criteria
        self.rating_criteria = RatingCriteria.objects.create(
            owner=self.user,
            name='Test Criteria'
        )
        self.project.rating_criteria = self.rating_criteria
        self.project.save()

        # Create criterion
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        # Create property in Stage3InProgress
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=Decimal('300000'),
            bedrooms=2,
            bathrooms=1,
            state='STAGE2_COMPLETE'
        )
        self.property.property_lists.add(self.property_list)

    @patch('property.tasks._send_rating_complete')
    @patch('property.tasks._send_property_event')
    def test_calculate_rating_success(self, mock_websocket, mock_rating_complete):
        """Test successful rating calculation"""
        # Transition to Stage3InProgress
        self.property.run_stage3()
        self.property.save()

        # Run task
        result = calculate_property_rating(self.property.id)

        # Verify result
        self.assertIn('Rating calculation complete', result)

        # Verify property updated
        self.property.refresh_from_db()
        self.assertEqual(self.property.state, 'STAGE3_COMPLETE')
        self.assertIsNotNone(self.property.overall_rating)

        # Verify WebSocket calls
        mock_websocket.assert_called_once()
        mock_rating_complete.assert_called_once()

    def test_calculate_rating_wrong_state(self):
        """Test error when property in wrong state"""
        # Property is in STAGE2_COMPLETE, not STAGE3_IN_PROGRESS
        with self.assertRaises(ValueError) as context:
            calculate_property_rating(self.property.id)

        self.assertIn('Cannot calculate rating', str(context.exception))

    def test_calculate_rating_no_criteria(self):
        """Test error when no rating criteria configured"""
        # Remove rating criteria
        self.project.rating_criteria = None
        self.project.save()

        # Transition to Stage3InProgress
        self.property.run_stage3()
        self.property.save()

        # Run task
        with self.assertRaises(ValueError) as context:
            calculate_property_rating(self.property.id)

        self.assertIn('No rating criteria', str(context.exception))

    def test_calculate_rating_property_not_found(self):
        """Test error when property doesn't exist"""
        with self.assertRaises(Exception):
            calculate_property_rating(99999)


class BulkCalculateRatingsTaskTest(TestCase):
    """Tests for bulk_calculate_ratings task"""

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

        # Create rating criteria
        self.rating_criteria = RatingCriteria.objects.create(
            owner=self.user,
            name='Test Criteria'
        )
        self.project.rating_criteria = self.rating_criteria
        self.project.save()

        # Create criterion
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        # Create properties
        self.property1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=Decimal('300000'),
            bedrooms=2,
            state='STAGE2_COMPLETE'
        )
        self.property1.property_lists.add(self.property_list)

        self.property2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 2BB',
            price=Decimal('400000'),
            bedrooms=3,
            state='STAGE2_COMPLETE'
        )
        self.property2.property_lists.add(self.property_list)

        self.property3 = Property.objects.create(
            title='Property 3',
            address_line_1='789 Test Rd',
            postcode='SW1A 3CC',
            price=Decimal('500000'),
            bedrooms=4,
            state='NEW'  # Wrong state
        )
        self.property3.property_lists.add(self.property_list)

    @patch('property.tasks.calculate_property_rating.delay')
    def test_bulk_calculate_valid_properties(self, mock_task):
        """Test bulk calculation only queues valid properties"""
        property_ids = [self.property1.id, self.property2.id, self.property3.id]

        # Run task
        result = bulk_calculate_ratings(property_ids)

        # Verify only 2 properties queued (property3 in wrong state)
        self.assertEqual(mock_task.call_count, 2)
        self.assertIn('2 properties', result)

        # Verify properties transitioned to Stage3InProgress
        self.property1.refresh_from_db()
        self.property2.refresh_from_db()
        self.property3.refresh_from_db()

        self.assertEqual(self.property1.state, 'STAGE3_IN_PROGRESS')
        self.assertEqual(self.property2.state, 'STAGE3_IN_PROGRESS')
        self.assertEqual(self.property3.state, 'NEW')  # Unchanged

    @patch('property.tasks.calculate_property_rating.delay')
    def test_bulk_calculate_empty_list(self, mock_task):
        """Test bulk calculation with empty list"""
        result = bulk_calculate_ratings([])

        # No tasks queued
        mock_task.assert_not_called()
        self.assertIn('0 properties', result)

    @patch('property.tasks.calculate_property_rating.delay')
    def test_bulk_calculate_with_already_rated(self, mock_task):
        """Test bulk calculation includes already rated properties"""
        # Set property1 to STAGE3_COMPLETE
        self.property1.state = 'STAGE3_COMPLETE'
        self.property1.save()

        property_ids = [self.property1.id, self.property2.id]

        # Run task
        result = bulk_calculate_ratings(property_ids)

        # Both should be queued (STAGE3_COMPLETE is valid source state)
        self.assertEqual(mock_task.call_count, 2)
        self.assertIn('2 properties', result)


class BulkCalculateProjectRatingsTaskTest(TestCase):
    """Tests for bulk_calculate_project_ratings task"""

    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create project with multiple property lists
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )

        self.list1 = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='List 1'
        )

        self.list2 = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='List 2'
        )

        # Create rating criteria
        self.rating_criteria = RatingCriteria.objects.create(
            owner=self.user,
            name='Test Criteria'
        )
        self.project.rating_criteria = self.rating_criteria
        self.project.save()

        # Create criterion
        Criterion.objects.create(
            rating_criteria=self.rating_criteria,
            name='Price',
            source='property',
            field_name='price',
            weight=Decimal('1.0')
        )

        # Create properties in different lists
        self.prop1 = Property.objects.create(
            title='Property 1',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=Decimal('300000'),
            state='STAGE2_COMPLETE'
        )
        self.prop1.property_lists.add(self.list1)

        self.prop2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test Ave',
            postcode='SW1A 2BB',
            price=Decimal('400000'),
            state='STAGE2_COMPLETE'
        )
        self.prop2.property_lists.add(self.list2)

        # Property in both lists (should only be rated once)
        self.prop3 = Property.objects.create(
            title='Property 3',
            address_line_1='789 Test Rd',
            postcode='SW1A 3CC',
            price=Decimal('500000'),
            state='STAGE2_COMPLETE'
        )
        self.prop3.property_lists.add(self.list1)
        self.prop3.property_lists.add(self.list2)

    @patch('property.tasks.bulk_calculate_ratings.delay')
    def test_project_bulk_calculate(self, mock_bulk_task):
        """Test project-level bulk calculation"""
        result = bulk_calculate_project_ratings(self.project.id)

        # Verify bulk task called
        mock_bulk_task.assert_called_once()

        # Verify property_ids passed (3 unique properties)
        call_args = mock_bulk_task.call_args
        property_ids = call_args[0][0]
        self.assertEqual(len(property_ids), 3)
        self.assertIn(self.prop1.id, property_ids)
        self.assertIn(self.prop2.id, property_ids)
        self.assertIn(self.prop3.id, property_ids)

        # Verify result message
        self.assertIn('3 properties', result)

    def test_project_bulk_calculate_not_found(self):
        """Test error when project doesn't exist"""
        with self.assertRaises(ValueError) as context:
            bulk_calculate_project_ratings(99999)

        self.assertIn('Project', str(context.exception))


class RatingTaskIntegrationTest(TestCase):
    """Integration tests for rating task workflow"""

    def setUp(self):
        """Create test data"""
        self.user = User.objects.create_user(username='testuser', password='testpass')

        # Create project
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )

        # Create rating criteria
        self.rating_criteria = RatingCriteria.objects.create(
            owner=self.user,
            name='Test Criteria'
        )
        self.project.rating_criteria = self.rating_criteria
        self.project.save()

        # Create multiple criteria
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

        # Create properties
        for i in range(3):
            prop = Property.objects.create(
                title=f'Property {i+1}',
                address_line_1=f'{100+i} Test St',
                postcode='SW1A 1AA',
                price=Decimal(300000 + i*100000),
                bedrooms=2 + i,
                state='STAGE2_COMPLETE'
            )
            prop.property_lists.add(self.property_list)

    @patch('property.tasks._send_rating_complete')
    @patch('property.tasks._send_property_event')
    def test_end_to_end_rating_workflow(self, mock_websocket, mock_rating_complete):
        """Test complete rating workflow from trigger to completion"""
        properties = Property.objects.filter(property_lists=self.property_list)

        for prop in properties:
            # Transition to Stage3InProgress
            prop.run_stage3()
            prop.save()

            # Run calculation task
            calculate_property_rating(prop.id)

            # Verify property rated
            prop.refresh_from_db()
            self.assertEqual(prop.state, 'STAGE3_COMPLETE')
            self.assertIsNotNone(prop.overall_rating)
            self.assertGreater(prop.overall_rating, 0)

        # Verify all properties have different ratings (due to different prices/bedrooms)
        ratings = [p.overall_rating for p in Property.objects.filter(property_lists=self.property_list)]
        self.assertEqual(len(set(ratings)), 3, "All ratings should be unique")
