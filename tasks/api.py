from django.shortcuts import get_object_or_404
from rest_framework import permissions, status, viewsets
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response

from .models import Task, TaskActivity, Team, TeamMembership
from .serializers import TeamTaskSerializer
from .services import broadcast_team_event


class TeamTaskViewSet(viewsets.ModelViewSet):
    serializer_class = TeamTaskSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_membership(self):
        if not hasattr(self, '_team_membership'):
            self._team_membership = TeamMembership.objects.filter(
                user=self.request.user,
                team_id=self.kwargs['team_id'],
            ).select_related('team').first()
        if self._team_membership is None:
            raise NotFound('Team not found.')
        return self._team_membership

    def get_queryset(self):
        membership = self.get_membership()
        return Task.objects.filter(team=membership.team).select_related('created_by', 'assigned_to')

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context['team'] = self.get_membership().team
        return context

    def perform_create(self, serializer):
        membership = self.get_membership()
        task = serializer.save(team=membership.team, created_by=self.request.user)
        TaskActivity.objects.create(
            team=membership.team,
            actor=self.request.user,
            task=task,
            task_title=task.title,
            message='created this task through the API',
        )
        broadcast_team_event(team_id=membership.team_id, event='task_created', task_id=task.id)

    def perform_update(self, serializer):
        membership = self.get_membership()
        old_status = serializer.instance.get_status_display()
        task = serializer.save()
        TaskActivity.objects.create(
            team=membership.team,
            actor=self.request.user,
            task=task,
            task_title=task.title,
            message=f'updated this task through the API (status: {old_status} → {task.get_status_display()})',
        )
        broadcast_team_event(team_id=membership.team_id, event='task_edited', task_id=task.id)

    def destroy(self, request, *args, **kwargs):
        task = self.get_object()
        membership = self.get_membership()
        if task.created_by_id != request.user.id and membership.role != TeamMembership.Role.MANAGER:
            raise PermissionDenied('You can only delete tasks you created. A team manager can delete any task.')
        TaskActivity.objects.create(
            team=membership.team,
            actor=request.user,
            task=None,
            task_title=task.title,
            message='deleted this task through the API',
        )
        task_id = task.id
        task.delete()
        broadcast_team_event(team_id=membership.team_id, event='task_deleted', task_id=task_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
