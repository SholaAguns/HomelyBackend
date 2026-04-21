from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from property.models import Project, PropertyList, Property, PropertyFavorite
from property.serializers import PropertySerializer, PropertyFavoriteSerializer


class PropertyFavoriteModelTest(TestCase):
    """Test PropertyFavorite model"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(
            owner=self.user,
            title='Test Project'
        )
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=250000
        )
        self.property.property_lists.add(self.property_list)

    def test_create_favorite(self):
        """Can create a favorite"""
        favorite = PropertyFavorite.objects.create(
            user=self.user,
            property=self.property
        )
        self.assertEqual(favorite.user, self.user)
        self.assertEqual(favorite.property, self.property)
        self.assertIsNotNone(favorite.uuid)
        self.assertIsNotNone(favorite.created_at)

    def test_unique_together_constraint(self):
        """User cannot favorite same property twice"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        with self.assertRaises(Exception):
            PropertyFavorite.objects.create(user=self.user, property=self.property)

    def test_favorite_str_representation(self):
        """Favorite has correct string representation"""
        favorite = PropertyFavorite.objects.create(
            user=self.user,
            property=self.property
        )
        self.assertEqual(str(favorite), f"{self.user.username} → {self.property.title}")

    def test_favorite_ordering(self):
        """Favorites ordered by created_at descending"""
        fav1 = PropertyFavorite.objects.create(user=self.user, property=self.property)

        property2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test St',
            postcode='SW1A 2BB',
            price=300000
        )
        property2.property_lists.add(self.property_list)
        fav2 = PropertyFavorite.objects.create(user=self.user, property=property2)

        favorites = PropertyFavorite.objects.all()
        self.assertEqual(favorites[0], fav2)
        self.assertEqual(favorites[1], fav1)


class PropertyFavoriteSerializerTest(TestCase):
    """Test PropertyFavoriteSerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(owner=self.user, title='Test Project')
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=250000
        )
        self.property.property_lists.add(self.property_list)

    def test_favorite_serializer_fields(self):
        """PropertyFavoriteSerializer includes correct fields"""
        favorite = PropertyFavorite.objects.create(
            user=self.user,
            property=self.property
        )
        serializer = PropertyFavoriteSerializer(favorite)

        data = serializer.data
        self.assertIn('uuid', data)
        self.assertIn('user', data)
        self.assertIn('property_uuid', data)
        self.assertIn('created_at', data)
        self.assertEqual(data['user'], 'testuser')
        self.assertEqual(str(data['property_uuid']), str(self.property.uuid))


class PropertySerializerIsFavoritedTest(APITestCase):
    """Test is_favorited field in PropertySerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.project = Project.objects.create(owner=self.user, title='Test Project')
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=250000
        )
        self.property.property_lists.add(self.property_list)

    def test_is_favorited_true_when_favorited(self):
        """is_favorited is True when user has favorited property"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        from rest_framework.request import Request
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        serializer = PropertySerializer(self.property, context={'request': request})
        self.assertTrue(serializer.data['is_favorited'])

    def test_is_favorited_false_when_not_favorited(self):
        """is_favorited is False when user has not favorited property"""
        from rest_framework.request import Request
        from django.test import RequestFactory

        factory = RequestFactory()
        request = factory.get('/')
        request.user = self.user

        serializer = PropertySerializer(self.property, context={'request': request})
        self.assertFalse(serializer.data['is_favorited'])


class PropertyFavoriteAPITest(APITestCase):
    """Test PropertyFavorite API endpoints"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            email='test@test.com',
            password='testpass123'
        )
        self.user2 = User.objects.create_user(
            username='user2',
            email='user2@test.com',
            password='testpass123'
        )
        self.token = RefreshToken.for_user(self.user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token}')

        self.project = Project.objects.create(owner=self.user, title='Test Project')
        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.user,
            title='Test List'
        )
        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=250000
        )
        self.property.property_lists.add(self.property_list)

    def test_add_favorite(self):
        """POST /api/property/favorites/ adds favorite"""
        data = {'property_uuid': str(self.property.uuid)}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['status'], 'added')
        self.assertTrue(
            PropertyFavorite.objects.filter(
                user=self.user,
                property=self.property
            ).exists()
        )

    def test_add_favorite_already_favorited(self):
        """POST /api/property/favorites/ returns 200 if already favorited"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        data = {'property_uuid': str(self.property.uuid)}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['status'], 'already_favorited')

    def test_add_favorite_missing_property_uuid(self):
        """POST /api/property/favorites/ requires property_uuid"""
        response = self.client.post('/api/property/favorites/', {})

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('error', response.data)

    def test_add_favorite_property_not_found(self):
        """POST /api/property/favorites/ returns 404 for invalid property"""
        data = {'property_uuid': '00000000-0000-0000-0000-000000000000'}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_add_favorite_no_access_to_property(self):
        """Cannot favorite property user doesn't have access to"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        other_project = Project.objects.create(owner=other_user, title='Other Project')
        other_list = PropertyList.objects.create(
            project=other_project,
            owner=other_user,
            title='Other List'
        )
        other_property = Property.objects.create(
            title='Other Property',
            address_line_1='456 Other St',
            postcode='SW1A 2BB',
            price=300000
        )
        other_property.property_lists.add(other_list)

        data = {'property_uuid': str(other_property.uuid)}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_favorite(self):
        """DELETE /api/property/favorites/{uuid}/ removes favorite"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        response = self.client.delete(
            f'/api/property/favorites/{self.property.uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(
            PropertyFavorite.objects.filter(
                user=self.user,
                property=self.property
            ).exists()
        )

    def test_remove_favorite_not_found(self):
        """DELETE /api/property/favorites/{uuid}/ returns 404 if not favorited"""
        response = self.client.delete(
            f'/api/property/favorites/{self.property.uuid}/'
        )

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_list_all_favorites(self):
        """GET /api/property/favorites/ returns user's favorites"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        property2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test St',
            postcode='SW1A 2BB',
            price=300000
        )
        property2.property_lists.add(self.property_list)
        PropertyFavorite.objects.create(user=self.user, property=property2)

        response = self.client.get('/api/property/favorites/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_list_favorites_only_accessible_projects(self):
        """GET /api/property/favorites/ only returns properties from accessible projects"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        other_project = Project.objects.create(owner=other_user, title='Other Project')
        other_list = PropertyList.objects.create(
            project=other_project,
            owner=other_user,
            title='Other List'
        )
        other_property = Property.objects.create(
            title='Other Property',
            address_line_1='456 Other St',
            postcode='SW1A 2BB',
            price=300000
        )
        other_property.property_lists.add(other_list)
        PropertyFavorite.objects.create(user=self.user, property=other_property)

        response = self.client.get('/api/property/favorites/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]['uuid'], str(self.property.uuid))

    def test_list_project_favorites(self):
        """GET /api/property/projects/{uuid}/favorites/ returns project favorites"""
        PropertyFavorite.objects.create(user=self.user, property=self.property)

        property2 = Property.objects.create(
            title='Property 2',
            address_line_1='456 Test St',
            postcode='SW1A 2BB',
            price=300000
        )
        property2.property_lists.add(self.property_list)
        PropertyFavorite.objects.create(user=self.user, property=property2)

        response = self.client.get(
            f'/api/property/projects/{self.project.uuid}/favorites/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['project_id'], str(self.project.uuid))
        self.assertEqual(response.data['project_name'], 'Test Project')
        self.assertEqual(response.data['total_favorites'], 2)
        self.assertEqual(len(response.data['properties']), 2)

    def test_list_project_favorites_empty(self):
        """GET /api/property/projects/{uuid}/favorites/ returns empty list when no favorites"""
        response = self.client.get(
            f'/api/property/projects/{self.project.uuid}/favorites/'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_favorites'], 0)
        self.assertEqual(len(response.data['properties']), 0)

    def test_favorite_as_viewer(self):
        """Viewer can favorite properties in shared project"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        shared_project = Project.objects.create(owner=other_user, title='Shared')
        shared_project.viewers.add(self.user)
        shared_list = PropertyList.objects.create(
            project=shared_project,
            owner=other_user,
            title='Shared List'
        )
        shared_property = Property.objects.create(
            title='Shared Property',
            address_line_1='789 Shared St',
            postcode='SW1A 3CC',
            price=350000
        )
        shared_property.property_lists.add(shared_list)

        data = {'property_uuid': str(shared_property.uuid)}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_favorite_as_contributor(self):
        """Contributor can favorite properties in shared project"""
        other_user = User.objects.create_user(
            username='otheruser',
            email='other@test.com',
            password='testpass'
        )
        shared_project = Project.objects.create(owner=other_user, title='Shared')
        shared_project.contributors.add(self.user)
        shared_list = PropertyList.objects.create(
            project=shared_project,
            owner=other_user,
            title='Shared List'
        )
        shared_property = Property.objects.create(
            title='Shared Property',
            address_line_1='789 Shared St',
            postcode='SW1A 3CC',
            price=350000
        )
        shared_property.property_lists.add(shared_list)

        data = {'property_uuid': str(shared_property.uuid)}
        response = self.client.post('/api/property/favorites/', data)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_unauthenticated_cannot_access_favorites(self):
        """Unauthenticated user cannot access favorites endpoints"""
        self.client.credentials()

        response = self.client.get('/api/property/favorites/')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

        response = self.client.post('/api/property/favorites/', {})
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
