from django.contrib.auth import get_user_model
from rest_framework import serializers

from .models import Project, Task, TeamMembership


class TeamTaskSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source='created_by.username', read_only=True)
    assigned_to_username = serializers.CharField(source='assigned_to.username', read_only=True)
    project_name = serializers.CharField(source='project.name', read_only=True, allow_null=True)

    class Meta:
        model = Task
        fields = [
            'id', 'title', 'description', 'status', 'priority', 'due_date',
            'created_at', 'created_by', 'created_by_username',
            'assigned_to', 'assigned_to_username',
            'project', 'project_name',
        ]
        read_only_fields = ['id', 'created_at', 'created_by', 'created_by_username', 'assigned_to_username']
        extra_kwargs = {
            'assigned_to': {'required': False, 'allow_null': True},
            'project': {'required': False, 'allow_null': True},
        }

    def validate_assigned_to(self, user):
        team = self.context['team']
        if user is not None and not TeamMembership.objects.filter(team=team, user=user).exists():
            raise serializers.ValidationError('Choose a member of this team.')
        return user

    def validate_project(self, project):
        team = self.context['team']
        if project is not None and not Project.objects.filter(team=team, pk=project.pk).exists():
            raise serializers.ValidationError('Choose a project in this team.')
        return project
