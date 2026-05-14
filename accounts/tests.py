from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from .models import UserProfile


class UserProfileModelTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )

    def test_profile_created_on_user_creation(self):
        """Profile auto-created when user created"""
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertIsInstance(self.user.profile, UserProfile)

    def test_profile_str(self):
        """Profile string representation"""
        self.assertEqual(str(self.user.profile), "test@test.com's profile")

    def test_profile_fields(self):
        """Profile has correct fields"""
        profile = self.user.profile
        profile.bio = "Test bio"
        profile.phone_number = "1234567890"
        profile.avatar = "https://example.com/avatar.jpg"
        profile.save()

        profile.refresh_from_db()
        self.assertEqual(profile.bio, "Test bio")
        self.assertEqual(profile.phone_number, "1234567890")
        self.assertEqual(profile.avatar, "https://example.com/avatar.jpg")

    def test_profile_uuid_auto_generated(self):
        """Profile UUID auto-generated and unique"""
        profile = self.user.profile
        self.assertIsNotNone(profile.uuid)

        # Create another user and verify different UUID
        user2 = User.objects.create_user(
            username='test2@test.com',
            email='test2@test.com',
            password='testpass123'
        )
        self.assertIsNotNone(user2.profile.uuid)
        self.assertNotEqual(profile.uuid, user2.profile.uuid)


class RegisterViewTest(APITestCase):
    def test_register_success(self):
        """User registration with valid data"""
        data = {
            'email': 'newuser@test.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post('/api/accounts/register/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertEqual(response.data['user']['email'], 'newuser@test.com')
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

        # Verify user created
        user = User.objects.get(email='newuser@test.com')
        self.assertEqual(user.first_name, 'Test')
        self.assertEqual(user.last_name, 'User')

    def test_register_password_mismatch(self):
        """Registration fails when passwords don't match"""
        data = {
            'email': 'newuser@test.com',
            'password': 'TestPass123!',
            'password2': 'DifferentPass123!',
            'first_name': 'Test',
            'last_name': 'User'
        }
        response = self.client.post('/api/accounts/register/', data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data.get('field_errors', response.data))

    def test_register_duplicate_email(self):
        """Registration fails with duplicate email"""
        User.objects.create_user(
            username='existing@test.com',
            email='existing@test.com',
            password='testpass123'
        )

        data = {
            'email': 'existing@test.com',
            'password': 'TestPass123!',
            'password2': 'TestPass123!',
        }
        response = self.client.post('/api/accounts/register/', data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data.get('field_errors', response.data))


class LoginViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )

    def test_login_success(self):
        """Login with valid credentials"""
        data = {
            'email': 'test@test.com',
            'password': 'testpass123'
        }
        response = self.client.post('/api/accounts/login/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('user', response.data)
        self.assertIn('access_token', response.cookies)
        self.assertIn('refresh_token', response.cookies)

    def test_login_invalid_credentials(self):
        """Login fails with wrong password"""
        data = {
            'email': 'test@test.com',
            'password': 'wrongpassword'
        }
        response = self.client.post('/api/accounts/login/', data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn('error', response.data)

    def test_login_missing_fields(self):
        """Login fails with missing fields"""
        response = self.client.post('/api/accounts/login/', {'email': 'test@test.com'})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LogoutViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_logout_success(self):
        """Logout with valid cookies clears auth cookies"""
        self.client.cookies['access_token'] = self.access
        self.client.cookies['refresh_token'] = str(self.refresh)
        response = self.client.post('/api/accounts/logout/', {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_logout_without_auth(self):
        """Logout requires authentication"""
        response = self.client.post('/api/accounts/logout/', {})

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserProfileViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123',
            first_name='Test',
            last_name='User'
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_get_profile(self):
        """Get user profile"""
        self.client.cookies['access_token'] = self.access
        response = self.client.get('/api/accounts/users/profile/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'test@test.com')
        self.assertEqual(response.data['first_name'], 'Test')

    def test_update_profile(self):
        """Update user profile"""
        self.client.cookies['access_token'] = self.access
        data = {
            'first_name': 'Updated',
            'last_name': 'Name',
            'bio': 'New bio',
            'phone_number': '9876543210'
        }
        response = self.client.patch('/api/accounts/users/profile/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['first_name'], 'Updated')
        self.assertEqual(response.data['bio'], 'New bio')

        # Verify database updated
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Updated')
        self.assertEqual(self.user.profile.bio, 'New bio')


class ChangePasswordViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='oldpass123'
        )
        self.refresh = RefreshToken.for_user(self.user)
        self.access = str(self.refresh.access_token)

    def test_change_password_success(self):
        """Change password with correct old password"""
        self.client.cookies['access_token'] = self.access
        data = {
            'old_password': 'oldpass123',
            'new_password': 'NewPass123!'
        }
        response = self.client.post('/api/accounts/users/change_password/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify new password works
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPass123!'))

    def test_change_password_wrong_old(self):
        """Change password fails with wrong old password"""
        self.client.cookies['access_token'] = self.access
        data = {
            'old_password': 'wrongpass',
            'new_password': 'NewPass123!'
        }
        response = self.client.post('/api/accounts/users/change_password/', data)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('old_password', response.data)


class PasswordResetTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )

    def test_password_reset_request(self):
        """Request password reset"""
        data = {'email': 'test@test.com'}
        response = self.client.post('/api/accounts/password-reset/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)

    def test_password_reset_nonexistent_email(self):
        """Reset request with nonexistent email still returns success (security)"""
        data = {'email': 'nonexistent@test.com'}
        response = self.client.post('/api/accounts/password-reset/', data)

        # Should return success to prevent email enumeration
        self.assertEqual(response.status_code, status.HTTP_200_OK)


class TokenRefreshTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='test@test.com',
            email='test@test.com',
            password='testpass123'
        )
        self.refresh = RefreshToken.for_user(self.user)

    def test_token_refresh(self):
        """Refresh access token via cookie"""
        self.client.cookies['refresh_token'] = str(self.refresh)
        response = self.client.post('/api/accounts/token/refresh/', {})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access_token', response.cookies)

    def test_token_refresh_invalid(self):
        """Refresh with invalid token fails"""
        data = {'refresh': 'invalid_token'}
        response = self.client.post('/api/accounts/token/refresh/', data)

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)


class UserViewSetTest(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            username='user1@test.com',
            email='user1@test.com',
            password='testpass123',
            first_name='User',
            last_name='One'
        )
        self.user2 = User.objects.create_user(
            username='user2@test.com',
            email='user2@test.com',
            password='testpass123',
            first_name='User',
            last_name='Two'
        )
        self.refresh = RefreshToken.for_user(self.user1)
        self.access = str(self.refresh.access_token)

    def test_list_users(self):
        """List all users"""
        self.client.cookies['access_token'] = self.access
        response = self.client.get('/api/accounts/users/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_retrieve_user_by_uuid(self):
        """Get user by UUID"""
        self.client.cookies['access_token'] = self.access
        uuid = self.user2.profile.uuid
        response = self.client.get(f'/api/accounts/users/{uuid}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], 'user2@test.com')
        self.assertEqual(response.data['first_name'], 'User')
        self.assertIn('profile', response.data)
        self.assertEqual(str(response.data['profile']['uuid']), str(uuid))

    def test_list_users_unauthorized(self):
        """List users requires authentication"""
        response = self.client.get('/api/accounts/users/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_retrieve_user_unauthorized(self):
        """Retrieve user by UUID requires authentication"""
        uuid = self.user1.profile.uuid
        response = self.client.get(f'/api/accounts/users/{uuid}/')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
