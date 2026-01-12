from django.test import TestCase
from django.contrib.auth.models import User
from django_fsm import TransitionNotAllowed
from .models import PropertyList, Property, StateTransitionLog


class PropertyStateMachineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com')
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            property_list=self.property_list,
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=100000,
            bedrooms=2,
            bathrooms=1
        )

    def test_property_initial_state(self):
        """Property should start in NEW state"""
        self.assertEqual(self.property.state, 'NEW')

    def test_valid_transition_new_to_stage2(self):
        """Test valid transition: NEW → STAGE2_IN_PROGRESS"""
        self.property.run_stage2()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_IN_PROGRESS')

    def test_invalid_transition_new_to_stage3(self):
        """Test that skipping Stage 2 is not allowed"""
        with self.assertRaises(TransitionNotAllowed):
            self.property.run_stage3()

    def test_stage2_complete_transition(self):
        """Test transition: STAGE2_IN_PROGRESS → STAGE2_COMPLETE"""
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_COMPLETE')

    def test_stage3_transitions(self):
        """Test Stage 3 transitions"""
        # Setup: advance to STAGE2_COMPLETE
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()

        # Run Stage 3
        self.property.run_stage3()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE3_IN_PROGRESS')

        # Complete Stage 3
        self.property.complete_stage3()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE3_COMPLETE')

    def test_rerun_services_from_stage3(self):
        """Test service rerun: STAGE3_COMPLETE → STAGE2_IN_PROGRESS"""
        # Setup: advance to STAGE3_COMPLETE
        self.property.run_stage2()
        self.property.save()
        self.property.complete_stage2()
        self.property.save()
        self.property.run_stage3()
        self.property.save()
        self.property.complete_stage3()
        self.property.save()

        # Trigger rerun
        self.property.rerun_services()
        self.property.save()
        self.assertEqual(self.property.state, 'STAGE2_IN_PROGRESS')

    def test_state_transition_logging(self):
        """Test that state transitions are logged"""
        initial_count = StateTransitionLog.objects.count()

        self.property.run_stage2()
        self.property.save()

        # Verify log entry created
        self.assertEqual(StateTransitionLog.objects.count(), initial_count + 1)

        # Verify log details
        log = StateTransitionLog.objects.latest('timestamp')
        self.assertEqual(log.from_state, 'NEW')
        self.assertEqual(log.to_state, 'STAGE2_IN_PROGRESS')
        self.assertEqual(log.transition_name, 'run_stage2')
        self.assertTrue(log.triggered_by_system)


class PropertyListStateMachineTestCase(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='testuser', email='test@test.com')
        self.property_list = PropertyList.objects.create(
            owner=self.user,
            title='Test List'
        )

    def test_property_list_initial_state(self):
        """PropertyList should start in DRAFT state"""
        self.assertEqual(self.property_list.state, 'DRAFT')

    def test_activate_property_list(self):
        """Test transition: DRAFT → ACTIVE"""
        self.property_list.activate()
        self.property_list.save()
        self.assertEqual(self.property_list.state, 'ACTIVE')
