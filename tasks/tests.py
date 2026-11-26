from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from .models import Notification, Task, Team, TeamInvite, TeamMembership


class TeamAccessTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(username='manager', password='test-password-123')
        self.member = User.objects.create_user(username='member', password='test-password-123')
        self.outsider = User.objects.create_user(username='outsider', password='test-password-123')
        self.team = Team.objects.create(name='Alpha', created_by=self.manager)
        TeamMembership.objects.create(team=self.team, user=self.manager, role=TeamMembership.Role.MANAGER)
        TeamMembership.objects.create(team=self.team, user=self.member)
        self.other_team = Team.objects.create(name='Beta', created_by=self.outsider)
        TeamMembership.objects.create(team=self.other_team, user=self.outsider, role=TeamMembership.Role.MANAGER)
        self.task = Task.objects.create(team=self.team, created_by=self.manager, title='Alpha task')

    def test_team_dashboard_hides_other_team_tasks(self):
        self.client.force_login(self.member)
        Task.objects.create(team=self.other_team, created_by=self.outsider, title='Private task')
        response = self.client.get(reverse('task_list'))
        self.assertContains(response, 'Alpha task')
        self.assertNotContains(response, 'Private task')

    def test_member_cannot_delete_another_members_task(self):
        self.client.force_login(self.member)
        response = self.client.post(reverse('delete_task', args=[self.task.id]))
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Task.objects.filter(pk=self.task.pk).exists())

    def test_manager_can_delete_member_task(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('delete_task', args=[self.task.id]))
        self.assertRedirects(response, reverse('task_list'))
        self.assertFalse(Task.objects.filter(pk=self.task.pk).exists())

    def test_invite_can_be_used_more_than_once_and_revoked(self):
        invite = TeamInvite.objects.create(team=self.team, created_by=self.manager)
        self.client.force_login(self.outsider)
        response = self.client.post(reverse('join_team_with_invite'), {'invite_code': invite.code})
        self.assertRedirects(response, reverse('team_settings'))
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=self.outsider).exists())
        another = get_user_model().objects.create_user(username='another', password='test-password-123')
        self.client.force_login(another)
        self.client.post(reverse('join_team_with_invite'), {'invite_code': invite.code})
        self.assertTrue(TeamMembership.objects.filter(team=self.team, user=another).exists())
        self.client.force_login(self.manager)
        self.client.post(reverse('revoke_team_invite', args=[invite.id]))
        self.assertFalse(TeamInvite.objects.get(pk=invite.pk).is_active)


class TeamTaskAPITests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.member = User.objects.create_user(username='api-member', password='test-password-123')
        self.owner = User.objects.create_user(username='api-owner', password='test-password-123')
        self.outsider = User.objects.create_user(username='api-outsider', password='test-password-123')
        self.team = Team.objects.create(name='API team')
        TeamMembership.objects.create(team=self.team, user=self.member)
        TeamMembership.objects.create(team=self.team, user=self.owner, role=TeamMembership.Role.MANAGER)
        self.other_team = Team.objects.create(name='Other API team')
        TeamMembership.objects.create(team=self.other_team, user=self.outsider)
        self.task = Task.objects.create(team=self.team, created_by=self.owner, title='Visible')
        self.private_task = Task.objects.create(team=self.other_team, created_by=self.outsider, title='Private')
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Token {Token.objects.create(user=self.member).key}')

    def test_api_lists_only_member_team_tasks(self):
        response = self.api.get(reverse('api_task_list', args=[self.team.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual([task['id'] for task in response.data['results']] if isinstance(response.data, dict) else [task['id'] for task in response.data], [self.task.id])

    def test_nonmember_cannot_read_team_api(self):
        response = self.api.get(reverse('api_task_list', args=[self.other_team.id]))
        self.assertEqual(response.status_code, 404)

    def test_api_cannot_delete_another_members_task(self):
        response = self.api.delete(reverse('api_task_detail', args=[self.team.id, self.task.id]))
        self.assertEqual(response.status_code, 403)

    def test_api_rejects_assignment_to_nonmember(self):
        response = self.api.post(reverse('api_task_list', args=[self.team.id]), {
            'title': 'Bad assignment', 'assigned_to': self.outsider.id,
        }, format='json')
        self.assertEqual(response.status_code, 400)


class NotificationTests(TestCase):
    def test_notification_is_visible_only_to_its_recipient(self):
        User = get_user_model()
        recipient = User.objects.create_user(username='recipient', password='test-password-123')
        other = User.objects.create_user(username='other-user', password='test-password-123')
        team = Team.objects.create(name='Notify team')
        TeamMembership.objects.create(team=team, user=recipient)
        TeamMembership.objects.create(team=team, user=other)
        Notification.objects.create(team=team, recipient=recipient, message='Assigned a task')
        self.client.force_login(other)
        response = self.client.get(reverse('notification_list'))
        self.assertNotContains(response, 'Assigned a task')
