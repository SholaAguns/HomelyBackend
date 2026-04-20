from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from property.models import Project, PropertyList, Property, SearchCriteria
from property.models.stage2_models import ContextOptions
from property.models.stage3_models import RatingCriteria
from property.permissions import (
    get_project_from_object,
    check_project_owner,
    check_project_contributor
)


def make_user(username, email, password='testpass123'):
    return User.objects.create_user(username=username, email=email, password=password)


def auth_client(client, user):
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class PermissionUtilsTest(APITestCase):
    """Test permission utility functions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')
        self.stranger = make_user('stranger', 'stranger@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

    def test_check_project_owner_returns_true_for_owner(self):
        self.assertTrue(check_project_owner(self.owner, self.project))

    def test_check_project_owner_returns_false_for_contributor(self):
        self.assertFalse(check_project_owner(self.contributor, self.project))

    def test_check_project_owner_returns_false_for_viewer(self):
        self.assertFalse(check_project_owner(self.viewer, self.project))

    def test_check_project_contributor_returns_true_for_owner(self):
        self.assertTrue(check_project_contributor(self.owner, self.project))

    def test_check_project_contributor_returns_true_for_contributor(self):
        self.assertTrue(check_project_contributor(self.contributor, self.project))

    def test_check_project_contributor_returns_false_for_viewer(self):
        self.assertFalse(check_project_contributor(self.viewer, self.project))

    def test_check_project_contributor_returns_false_for_stranger(self):
        self.assertFalse(check_project_contributor(self.stranger, self.project))

    def test_get_project_from_object_returns_project(self):
        result = get_project_from_object(self.project)
        self.assertEqual(result, self.project)

    def test_get_project_from_object_returns_project_from_property_list(self):
        prop_list = PropertyList.objects.create(
            project=self.project,
            owner=self.owner,
            title='Test List'
        )
        result = get_project_from_object(prop_list)
        self.assertEqual(result, self.project)

    def test_get_project_from_object_returns_project_from_property(self):
        prop_list = PropertyList.objects.create(
            project=self.project,
            owner=self.owner,
            title='Test List'
        )
        prop = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=500000
        )
        prop.property_lists.add(prop_list)

        result = get_project_from_object(prop)
        self.assertEqual(result, self.project)


class ProjectPermissionsTest(APITestCase):
    """Test Project CRUD permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')
        self.stranger = make_user('stranger', 'stranger@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

    def test_owner_can_read_project(self):
        auth_client(self.client, self.owner)
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_contributor_can_read_project(self):
        auth_client(self.client, self.contributor)
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_can_read_project(self):
        auth_client(self.client, self.viewer)
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_stranger_cannot_read_project(self):
        auth_client(self.client, self.stranger)
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)

    def test_owner_can_update_project(self):
        auth_client(self.client, self.owner)
        res = self.client.patch(
            f'/api/property/projects/{self.project.uuid}/',
            {'title': 'Updated Title'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'Updated Title')

    def test_contributor_can_update_project(self):
        auth_client(self.client, self.contributor)
        res = self.client.patch(
            f'/api/property/projects/{self.project.uuid}/',
            {'title': 'Updated by Contributor'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.title, 'Updated by Contributor')

    def test_viewer_cannot_update_project(self):
        auth_client(self.client, self.viewer)
        res = self.client.patch(
            f'/api/property/projects/{self.project.uuid}/',
            {'title': 'Unauthorized Update'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_owner_can_delete_project(self):
        auth_client(self.client, self.owner)
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Project.objects.filter(uuid=self.project.uuid).exists())

    def test_contributor_cannot_delete_project(self):
        auth_client(self.client, self.contributor)
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(Project.objects.filter(uuid=self.project.uuid).exists())

    def test_viewer_cannot_delete_project(self):
        auth_client(self.client, self.viewer)
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class ContextOptionsPermissionsTest(APITestCase):
    """Test ContextOptions permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

    def test_owner_can_update_context_options(self):
        auth_client(self.client, self.owner)
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/context-options/',
            {'enable_crime': True, 'enable_schools': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(res.data['enable_crime'])

    def test_contributor_can_update_context_options(self):
        auth_client(self.client, self.contributor)
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/context-options/',
            {'enable_crime': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_update_context_options(self):
        auth_client(self.client, self.viewer)
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/context-options/',
            {'enable_crime': True},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_viewer_can_read_context_options(self):
        auth_client(self.client, self.viewer)
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/context-options/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)


class RatingCriteriaPermissionsTest(APITestCase):
    """Test RatingCriteria permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

        self.criteria = RatingCriteria.objects.create(owner=self.owner, name='Test Criteria')

    def test_owner_can_update_rating_criteria(self):
        auth_client(self.client, self.owner)
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/rating-criteria/',
            {'rating_criteria_uuid': str(self.criteria.uuid)},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.project.refresh_from_db()
        self.assertEqual(self.project.rating_criteria, self.criteria)

    def test_contributor_can_update_rating_criteria(self):
        auth_client(self.client, self.contributor)
        criteria2 = RatingCriteria.objects.create(owner=self.contributor, name='Contributor Criteria')
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/rating-criteria/',
            {'rating_criteria_uuid': str(criteria2.uuid)},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_update_rating_criteria(self):
        auth_client(self.client, self.viewer)
        res = self.client.put(
            f'/api/property/projects/{self.project.uuid}/rating-criteria/',
            {'rating_criteria_uuid': str(self.criteria.uuid)},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class PropertyListPermissionsTest(APITestCase):
    """Test PropertyList CRUD permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.owner,
            title='Test List'
        )

    def test_viewer_can_read_property_list(self):
        auth_client(self.client, self.viewer)
        res = self.client.get(f'/api/property/property-lists/{self.property_list.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_contributor_can_update_property_list(self):
        auth_client(self.client, self.contributor)
        res = self.client.patch(
            f'/api/property/property-lists/{self.property_list.uuid}/',
            {'title': 'Updated by Contributor'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_update_property_list(self):
        auth_client(self.client, self.viewer)
        res = self.client.patch(
            f'/api/property/property-lists/{self.property_list.uuid}/',
            {'title': 'Unauthorized'},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_contributor_can_delete_property_list(self):
        auth_client(self.client, self.contributor)
        res = self.client.delete(f'/api/property/property-lists/{self.property_list.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_delete_property_list(self):
        auth_client(self.client, self.viewer)
        res = self.client.delete(f'/api/property/property-lists/{self.property_list.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class PropertyPermissionsTest(APITestCase):
    """Test Property CRUD permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.owner,
            title='Test List'
        )

        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=500000
        )
        self.property.property_lists.add(self.property_list)

    def test_viewer_can_read_property(self):
        auth_client(self.client, self.viewer)
        res = self.client.get(f'/api/property/properties/{self.property.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_contributor_can_update_property(self):
        auth_client(self.client, self.contributor)
        res = self.client.patch(
            f'/api/property/properties/{self.property.uuid}/',
            {'bedrooms': 4},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_update_property(self):
        auth_client(self.client, self.viewer)
        res = self.client.patch(
            f'/api/property/properties/{self.property.uuid}/',
            {'bedrooms': 4},
            format='json'
        )
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_contributor_can_delete_property(self):
        auth_client(self.client, self.contributor)
        res = self.client.delete(f'/api/property/properties/{self.property.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)

    def test_viewer_cannot_delete_property(self):
        auth_client(self.client, self.viewer)
        res = self.client.delete(f'/api/property/properties/{self.property.uuid}/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class StageActionsPermissionsTest(APITestCase):
    """Test Stage 2/3 action permissions"""

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')

        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)
        self.project.viewers.add(self.viewer)

        ContextOptions.objects.create(
            project=self.project,
            enable_crime=True,
            enable_schools=True
        )

        self.property_list = PropertyList.objects.create(
            project=self.project,
            owner=self.owner,
            title='Test List'
        )

        self.property = Property.objects.create(
            title='Test Property',
            address_line_1='123 Test St',
            postcode='SW1A 1AA',
            price=500000,
            latitude=51.5074,
            longitude=-0.1278
        )
        self.property.property_lists.add(self.property_list)

    def test_contributor_can_run_stage2(self):
        auth_client(self.client, self.contributor)
        res = self.client.post(f'/api/property/properties/{self.property.uuid}/run-stage2/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_run_stage2(self):
        auth_client(self.client, self.viewer)
        res = self.client.post(f'/api/property/properties/{self.property.uuid}/run-stage2/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_contributor_can_run_stage3_bulk(self):
        auth_client(self.client, self.contributor)
        criteria = RatingCriteria.objects.create(owner=self.owner, name='Test Criteria')
        self.project.rating_criteria = criteria
        self.project.save()

        res = self.client.post(f'/api/property/projects/{self.project.uuid}/run-stage3-bulk/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)

    def test_viewer_cannot_run_stage3_bulk(self):
        auth_client(self.client, self.viewer)
        criteria = RatingCriteria.objects.create(owner=self.owner, name='Test Criteria')
        self.project.rating_criteria = criteria
        self.project.save()

        res = self.client.post(f'/api/property/projects/{self.project.uuid}/run-stage3-bulk/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
