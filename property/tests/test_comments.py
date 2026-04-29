from django.test import TestCase
from django.contrib.auth.models import User
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken

from property.models import Project, ProjectComment
from property.serializers import ProjectCommentSerializer


class ProjectCommentSerializerTest(TestCase):
    """Test ProjectCommentSerializer"""

    def setUp(self):
        self.user = User.objects.create_user(
            username='author',
            email='author@test.com',
            first_name='Jane',
            last_name='Smith',
            password='testpass123',
        )
        self.project = Project.objects.create(owner=self.user, title='Test Project')

    def test_serializer_includes_expected_fields(self):
        """ProjectCommentSerializer includes uuid, body, author_email, author_name, timestamps"""
        comment = ProjectComment.objects.create(
            project=self.project,
            author=self.user,
            body='Looks great!',
        )
        data = ProjectCommentSerializer(comment).data

        self.assertIn('uuid', data)
        self.assertIn('body', data)
        self.assertIn('author_email', data)
        self.assertIn('author_name', data)
        self.assertIn('created_at', data)
        self.assertIn('updated_at', data)

    def test_author_email_reads_from_author(self):
        """author_email is derived from the comment author's email"""
        comment = ProjectComment.objects.create(
            project=self.project,
            author=self.user,
            body='Test comment',
        )
        data = ProjectCommentSerializer(comment).data

        self.assertEqual(data['author_email'], 'author@test.com')

    def test_author_name_combines_first_and_last_name(self):
        """author_name is first_name + last_name when both are set"""
        comment = ProjectComment.objects.create(
            project=self.project,
            author=self.user,
            body='Test comment',
        )
        data = ProjectCommentSerializer(comment).data

        self.assertEqual(data['author_name'], 'Jane Smith')

    def test_author_name_falls_back_to_email_when_name_is_blank(self):
        """author_name falls back to email when first/last name are blank"""
        nameless_user = User.objects.create_user(
            username='nameless',
            email='nameless@test.com',
            password='testpass123',
        )
        comment = ProjectComment.objects.create(
            project=self.project,
            author=nameless_user,
            body='No name comment',
        )
        data = ProjectCommentSerializer(comment).data

        self.assertEqual(data['author_name'], 'nameless@test.com')


class ProjectCommentAPITest(APITestCase):
    """Test ProjectComment API endpoints"""

    def setUp(self):
        self.owner = User.objects.create_user(
            username='owner', email='owner@test.com', password='testpass123'
        )
        self.contributor = User.objects.create_user(
            username='contributor', email='contributor@test.com', password='testpass123'
        )
        self.outsider = User.objects.create_user(
            username='outsider', email='outsider@test.com', password='testpass123'
        )
        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.contributors.add(self.contributor)

        self.owner_token = str(RefreshToken.for_user(self.owner).access_token)
        self.contributor_token = str(RefreshToken.for_user(self.contributor).access_token)
        self.outsider_token = str(RefreshToken.for_user(self.outsider).access_token)

    def _auth(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_owner_can_create_comment(self):
        """POST /api/property/comments/ creates comment for project owner"""
        self._auth(self.owner_token)
        response = self.client.post('/api/property/comments/', {
            'body': 'Great project!',
            'project_uuid': str(self.project.uuid),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['body'], 'Great project!')
        self.assertEqual(response.data['author_email'], 'owner@test.com')

    def test_contributor_can_create_comment(self):
        """POST /api/property/comments/ creates comment for project contributor"""
        self._auth(self.contributor_token)
        response = self.client.post('/api/property/comments/', {
            'body': 'Nice find!',
            'project_uuid': str(self.project.uuid),
        })

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['author_email'], 'contributor@test.com')

    def test_list_comments_filtered_by_project_uuid(self):
        """GET /api/property/comments/?project=<uuid> returns comments for that project"""
        self._auth(self.owner_token)
        ProjectComment.objects.create(project=self.project, author=self.owner, body='First')
        ProjectComment.objects.create(project=self.project, author=self.contributor, body='Second')

        response = self.client.get(f'/api/property/comments/?project={self.project.uuid}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)

    def test_outsider_cannot_list_comments(self):
        """GET /api/property/comments/?project=<uuid> returns empty list for non-member"""
        self._auth(self.outsider_token)
        ProjectComment.objects.create(project=self.project, author=self.owner, body='Secret')

        response = self.client.get(f'/api/property/comments/?project={self.project.uuid}')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 0)

    def test_author_can_delete_own_comment(self):
        """DELETE /api/property/comments/<uuid>/ succeeds for comment author"""
        self._auth(self.owner_token)
        comment = ProjectComment.objects.create(
            project=self.project, author=self.owner, body='My comment'
        )

        response = self.client.delete(f'/api/property/comments/{comment.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(ProjectComment.objects.filter(uuid=comment.uuid).exists())

    def test_non_author_cannot_delete_comment(self):
        """DELETE /api/property/comments/<uuid>/ returns 403 for non-author project member"""
        owner_comment = ProjectComment.objects.create(
            project=self.project, author=self.owner, body='Owners comment'
        )
        self._auth(self.contributor_token)

        response = self.client.delete(f'/api/property/comments/{owner_comment.uuid}/')

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertTrue(ProjectComment.objects.filter(uuid=owner_comment.uuid).exists())

    def test_unauthenticated_request_is_rejected(self):
        """POST /api/property/comments/ returns 401 without authentication"""
        self.client.credentials()
        response = self.client.post('/api/property/comments/', {
            'body': 'Sneaky!',
            'project_uuid': str(self.project.uuid),
        })

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
