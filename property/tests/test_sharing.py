from django.test import TestCase
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework import status
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from property.models import Project, ProjectInvitation, AppNotification
from property.utils.invitation_tokens import generate_invite_token, verify_invite_token, hash_token


class InvitationTokenTests(TestCase):
    """Unit tests for invitation token utilities"""

    def test_generate_and_verify_token(self):
        token = generate_invite_token('test-uuid')
        result = verify_invite_token(token)
        self.assertEqual(result, 'test-uuid')

    def test_tampered_token_raises(self):
        from django.core import signing
        token = generate_invite_token('test-uuid')
        with self.assertRaises(signing.BadSignature):
            verify_invite_token(token + 'tampered')

    def test_hash_token_is_deterministic(self):
        token = generate_invite_token('test-uuid')
        self.assertEqual(hash_token(token), hash_token(token))

    def test_hash_token_differs_for_different_tokens(self):
        t1 = generate_invite_token('uuid-1')
        t2 = generate_invite_token('uuid-2')
        self.assertNotEqual(hash_token(t1), hash_token(t2))

    def test_hash_is_64_chars(self):
        token = generate_invite_token('test-uuid')
        self.assertEqual(len(hash_token(token)), 64)


def make_user(username, email, password='testpass123'):
    return User.objects.create_user(username=username, email=email, password=password)


def auth_client(client, user):
    token = RefreshToken.for_user(user).access_token
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {token}')


class ProjectMembersAPITest(APITestCase):

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.viewer = make_user('viewer', 'viewer@test.com')
        self.contributor = make_user('contributor', 'contributor@test.com')
        self.project = Project.objects.create(owner=self.owner, title='Test Project')
        self.project.viewers.add(self.viewer)
        self.project.contributors.add(self.contributor)
        auth_client(self.client, self.owner)

    def test_members_returns_owner_viewers_contributors(self):
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/members/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['owner']['email'], 'owner@test.com')
        self.assertEqual(len(res.data['viewers']), 1)
        self.assertEqual(len(res.data['contributors']), 1)

    def test_remove_viewer(self):
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/members/viewer@test.com/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(self.project.viewers.filter(email='viewer@test.com').exists())

    def test_remove_nonmember_returns_400(self):
        stranger = make_user('stranger', 'stranger@test.com')
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/members/stranger@test.com/')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_owner_cannot_remove_member(self):
        auth_client(self.client, self.contributor)
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/members/viewer@test.com/')
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)

    def test_remove_member_creates_notification(self):
        res = self.client.delete(f'/api/property/projects/{self.project.uuid}/members/viewer@test.com/')
        self.assertEqual(res.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(
            AppNotification.objects.filter(
                recipient=self.viewer,
                notification_type='member_removed'
            ).exists()
        )


class ProjectInviteAPITest(APITestCase):

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.project = Project.objects.create(owner=self.owner, title='My Project')
        auth_client(self.client, self.owner)

    @patch('property.views.send_mail')
    def test_invite_creates_invitation(self, mock_mail):
        res = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        self.assertEqual(res.status_code, status.HTTP_201_CREATED)
        self.assertEqual(res.data['invited_email'], 'jane@test.com')
        self.assertEqual(res.data['role'], 'viewer')
        self.assertEqual(res.data['status'], 'pending')
        self.assertIn('invite_url', res.data)
        mock_mail.assert_called_once()

    @patch('property.views.send_mail')
    def test_invite_sends_notification_to_existing_user(self, mock_mail):
        invited = make_user('jane', 'jane@test.com')
        self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'contributor'}
        )
        self.assertTrue(
            AppNotification.objects.filter(
                recipient=invited,
                notification_type='invite_received'
            ).exists()
        )

    @patch('property.views.send_mail')
    def test_invite_idempotent_returns_existing(self, mock_mail):
        self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        res2 = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        self.assertEqual(res2.status_code, status.HTTP_200_OK)
        self.assertEqual(ProjectInvitation.objects.filter(project=self.project).count(), 1)

    @patch('property.views.send_mail')
    def test_invite_existing_member_returns_400(self, mock_mail):
        member = make_user('member', 'member@test.com')
        self.project.viewers.add(member)
        res = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'member@test.com', 'role': 'viewer'}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_invite_invalid_role_returns_400(self):
        res = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'admin'}
        )
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_owner_cannot_invite(self):
        other = make_user('other', 'other@test.com')
        auth_client(self.client, other)
        res = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        self.assertIn(res.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])

    @patch('property.views.send_mail')
    def test_revoke_invitation(self, mock_mail):
        res = self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        invitation_uuid = res.data['uuid']
        res2 = self.client.delete(
            f'/api/property/projects/{self.project.uuid}/invitations/{invitation_uuid}/'
        )
        self.assertEqual(res2.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(
            ProjectInvitation.objects.get(uuid=invitation_uuid).status, 'revoked'
        )

    @patch('property.views.send_mail')
    def test_list_invitations_owner_only(self, mock_mail):
        self.client.post(
            f'/api/property/projects/{self.project.uuid}/invite/',
            {'email': 'jane@test.com', 'role': 'viewer'}
        )
        res = self.client.get(f'/api/property/projects/{self.project.uuid}/invitations/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

        other = make_user('other', 'other@test.com')
        auth_client(self.client, other)
        res2 = self.client.get(f'/api/property/projects/{self.project.uuid}/invitations/')
        self.assertIn(res2.status_code, [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND])


class PreviewInviteAPITest(APITestCase):

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.project = Project.objects.create(owner=self.owner, title='My Project')

    def _create_invitation(self, email='jane@test.com', role='viewer'):
        token = generate_invite_token(str(self.project.uuid) + '|' + email)
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invited_by=self.owner,
            invited_email=email,
            role=role,
            token_hash=hash_token(token),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        return invitation, token

    def test_preview_returns_invite_details(self):
        _, token = self._create_invitation()
        res = self.client.get(f'/api/property/projects/preview-invite/?token={token}')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['project_title'], 'My Project')
        self.assertEqual(res.data['role'], 'viewer')
        self.assertIn('invited_by_name', res.data)
        self.assertIn('expires_at', res.data)

    def test_preview_invalid_token_returns_400(self):
        res = self.client.get('/api/property/projects/preview-invite/?token=bad.token.here')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['error'], 'invalid_or_expired_token')

    def test_preview_used_invitation_returns_400(self):
        invitation, token = self._create_invitation()
        invitation.status = 'accepted'
        invitation.save()
        res = self.client.get(f'/api/property/projects/preview-invite/?token={token}')
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['error'], 'invitation_already_used')


class AcceptInviteAPITest(APITestCase):

    def setUp(self):
        self.owner = make_user('owner', 'owner@test.com')
        self.invitee = make_user('jane', 'jane@test.com')
        self.project = Project.objects.create(owner=self.owner, title='My Project')
        auth_client(self.client, self.invitee)

    def _create_invitation(self, email='jane@test.com', role='viewer'):
        token = generate_invite_token(str(self.project.uuid) + '|' + email)
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invited_by=self.owner,
            invited_email=email,
            role=role,
            token_hash=hash_token(token),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        return invitation, token

    def test_accept_viewer_invite(self):
        _, token = self._create_invitation(role='viewer')
        res = self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['role'], 'viewer')
        self.assertEqual(str(res.data['project_uuid']), str(self.project.uuid))
        self.assertTrue(self.project.viewers.filter(pk=self.invitee.pk).exists())

    def test_accept_contributor_invite(self):
        _, token = self._create_invitation(role='contributor')
        res = self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertTrue(self.project.contributors.filter(pk=self.invitee.pk).exists())

    def test_accept_marks_invitation_accepted(self):
        invitation, token = self._create_invitation()
        self.client.post('/api/property/projects/accept-invite/', {'token': token})
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'accepted')
        self.assertEqual(invitation.accepted_by, self.invitee)
        self.assertIsNotNone(invitation.accepted_at)

    def test_accept_notifies_owner(self):
        _, token = self._create_invitation()
        self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertTrue(
            AppNotification.objects.filter(
                recipient=self.owner,
                notification_type='invite_accepted'
            ).exists()
        )

    def test_accept_email_mismatch_returns_403(self):
        other = make_user('bob', 'bob@test.com')
        auth_client(self.client, other)
        _, token = self._create_invitation(email='jane@test.com')
        res = self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(res.data['error'], 'email_mismatch')

    def test_accept_already_used_returns_400(self):
        invitation, token = self._create_invitation()
        invitation.status = 'revoked'
        invitation.save()
        res = self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['error'], 'invitation_already_used')

    def test_accept_invalid_token_returns_400(self):
        res = self.client.post('/api/property/projects/accept-invite/', {'token': 'bad.token'})
        self.assertEqual(res.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(res.data['error'], 'invalid_or_expired_token')

    def test_accept_unauthenticated_returns_401(self):
        self.client.credentials()
        _, token = self._create_invitation()
        res = self.client.post('/api/property/projects/accept-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)


class DeclineInviteAPITest(APITestCase):

    def setUp(self):
        self.owner = make_user('owner2', 'owner2@test.com')
        self.invitee = make_user('jane2', 'jane2@test.com')
        self.project = Project.objects.create(owner=self.owner, title='Project B')
        auth_client(self.client, self.invitee)

    def _create_invitation(self, email='jane2@test.com', role='viewer'):
        token = generate_invite_token(str(self.project.uuid) + '|' + email)
        invitation = ProjectInvitation.objects.create(
            project=self.project,
            invited_by=self.owner,
            invited_email=email,
            role=role,
            token_hash=hash_token(token),
            expires_at=timezone.now() + timezone.timedelta(days=7),
        )
        return invitation, token

    def test_decline_marks_invitation_declined(self):
        invitation, token = self._create_invitation()
        res = self.client.post('/api/property/projects/decline-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        invitation.refresh_from_db()
        self.assertEqual(invitation.status, 'declined')

    def test_decline_does_not_add_to_project(self):
        _, token = self._create_invitation()
        self.client.post('/api/property/projects/decline-invite/', {'token': token})
        self.assertFalse(self.project.viewers.filter(pk=self.invitee.pk).exists())
        self.assertFalse(self.project.contributors.filter(pk=self.invitee.pk).exists())

    def test_decline_notifies_owner(self):
        _, token = self._create_invitation()
        self.client.post('/api/property/projects/decline-invite/', {'token': token})
        self.assertTrue(
            AppNotification.objects.filter(
                recipient=self.owner,
                notification_type='invite_declined'
            ).exists()
        )

    def test_decline_email_mismatch_returns_403(self):
        other = make_user('bob2', 'bob2@test.com')
        auth_client(self.client, other)
        _, token = self._create_invitation(email='jane2@test.com')
        res = self.client.post('/api/property/projects/decline-invite/', {'token': token})
        self.assertEqual(res.status_code, status.HTTP_403_FORBIDDEN)


class NotificationAPITest(APITestCase):

    def setUp(self):
        self.user = make_user('notif_user', 'notif@test.com')
        self.other = make_user('other_user', 'other@test.com')
        self.project = Project.objects.create(owner=self.user, title='Notif Project')
        auth_client(self.client, self.user)

    def _create_notification(self, user=None, read=False):
        return AppNotification.objects.create(
            recipient=user or self.user,
            actor=self.other,
            notification_type='invite_received',
            title='Test notification',
            message='You have been invited.',
            related_object_uuid=self.project.uuid,
            related_object_type='project',
            is_read=read,
        )

    def test_list_returns_own_notifications_only(self):
        self._create_notification()
        self._create_notification(user=self.other)
        res = self.client.get('/api/property/notifications/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(len(res.data), 1)

    def test_unread_count(self):
        self._create_notification()
        self._create_notification()
        self._create_notification(read=True)
        res = self.client.get('/api/property/notifications/unread-count/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data['count'], 2)

    def test_mark_single_read(self):
        n = self._create_notification()
        res = self.client.post(f'/api/property/notifications/{n.uuid}/read/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        n.refresh_from_db()
        self.assertTrue(n.is_read)

    def test_mark_all_read(self):
        self._create_notification()
        self._create_notification()
        res = self.client.post('/api/property/notifications/read-all/')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(AppNotification.objects.filter(recipient=self.user, is_read=False).count(), 0)

    def test_cannot_read_other_users_notification(self):
        n = self._create_notification(user=self.other)
        res = self.client.post(f'/api/property/notifications/{n.uuid}/read/')
        self.assertEqual(res.status_code, status.HTTP_404_NOT_FOUND)


class UserSearchAPITest(APITestCase):

    def setUp(self):
        self.user = make_user('searcher', 'searcher@test.com')
        auth_client(self.client, self.user)
        make_user('alice_smith', 'alice@test.com')
        User.objects.filter(username='alice_smith').update(first_name='Alice', last_name='Smith')
        make_user('bob_jones', 'bob@test.com')
        User.objects.filter(username='bob_jones').update(first_name='Bob', last_name='Jones')

    def test_search_by_email(self):
        res = self.client.get('/api/accounts/users/search/?q=alice')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u['email'] for u in res.data]
        self.assertIn('alice@test.com', emails)

    def test_search_excludes_self(self):
        res = self.client.get('/api/accounts/users/search/?q=searcher')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        emails = [u['email'] for u in res.data]
        self.assertNotIn('searcher@test.com', emails)

    def test_search_too_short_returns_empty(self):
        res = self.client.get('/api/accounts/users/search/?q=a')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertEqual(res.data, [])

    def test_search_unauthenticated_returns_401(self):
        self.client.credentials()
        res = self.client.get('/api/accounts/users/search/?q=alice')
        self.assertEqual(res.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_search_returns_correct_fields(self):
        res = self.client.get('/api/accounts/users/search/?q=alice')
        self.assertEqual(res.status_code, status.HTTP_200_OK)
        self.assertGreater(len(res.data), 0)
        for result in res.data:
            self.assertIn('email', result)
            self.assertIn('first_name', result)
            self.assertIn('last_name', result)
