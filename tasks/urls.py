from django.urls import include, path
from rest_framework.authtoken.views import obtain_auth_token

from . import views
from .api import TeamTaskViewSet

team_task_list = TeamTaskViewSet.as_view({'get': 'list', 'post': 'create'})
team_task_detail = TeamTaskViewSet.as_view({
    'get': 'retrieve',
    'put': 'update',
    'patch': 'partial_update',
    'delete': 'destroy',
})

urlpatterns = [
    path('accounts/register/', views.register, name='register'),
    path('accounts/', include('django.contrib.auth.urls')),
    path('', views.task_list, name='task_list'),
    path('tasks/', views.task_list, name='tasks_page'),
    path('projects/', views.project_list, name='project_list'),
    path('projects/<int:project_id>/edit/', views.edit_project, name='edit_project'),
    path('calendar/', views.calendar_view, name='calendar_view'),
    path('analytics/export.csv', views.export_analytics_csv, name='export_analytics_csv'),
    path('profile/', views.profile_settings, name='profile_settings'),
    path('profile-icons/<int:profile_id>/', views.profile_icon, name='profile_icon'),
    path('progress/', views.task_list, name='progress_page'),
    path('analytics/', views.task_list, name='analytics_page'),
    path('updates/new/', views.add_progress_update, name='add_progress_update'),
    path('tasks/<int:task_id>/edit/', views.edit_task, name='edit_task'),
    path('tasks/<int:task_id>/comments/', views.add_task_comment, name='add_task_comment'),
    path('tasks/<int:task_id>/attachments/', views.add_task_attachment, name='add_task_attachment'),
    path('attachments/<int:attachment_id>/download/', views.download_task_attachment, name='download_task_attachment'),
    path('tasks/<int:task_id>/status/', views.set_task_status, name='set_task_status'),
    path('tasks/<int:task_id>/delete/', views.delete_task, name='delete_task'),
    path('teams/settings/', views.team_settings, name='team_settings'),
    path('teams/create/', views.create_team, name='create_team'),
    path('teams/invites/create/', views.create_team_invite, name='create_team_invite'),
    path('teams/invites/join/', views.join_team_with_invite, name='join_team_with_invite'),
    path('teams/invites/<int:invite_id>/revoke/', views.revoke_team_invite, name='revoke_team_invite'),
    path('teams/members/<int:membership_id>/remove/', views.remove_team_member, name='remove_team_member'),
    path('teams/switch/', views.set_active_team, name='set_active_team'),
    path('notifications/', views.notification_list, name='notification_list'),
    path('notifications/<int:notification_id>/read/', views.mark_notification_read, name='mark_notification_read'),
    path('notifications/push/subscribe/', views.save_push_subscription, name='save_push_subscription'),
    path('notifications/push/unsubscribe/', views.remove_push_subscription, name='remove_push_subscription'),
    path('service-worker.js', views.service_worker, name='service_worker'),
    path('api/auth/token/', obtain_auth_token, name='api_token_auth'),
    path('api/teams/<int:team_id>/tasks/', team_task_list, name='api_task_list'),
    path('api/teams/<int:team_id>/tasks/<int:pk>/', team_task_detail, name='api_task_detail'),
]
