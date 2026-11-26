from django.contrib import admin

from .models import Notification, ProgressUpdate, Project, Task, TaskActivity, TaskAttachment, Team, TeamInvite, TeamMembership, UserProfile


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('title', 'team', 'project', 'status', 'assigned_to', 'created_by', 'created_at')
    list_filter = ('status',)
    search_fields = ('title', 'description')


@admin.register(Project)
class ProjectAdmin(admin.ModelAdmin):
    list_display = ('name', 'team', 'created_by', 'created_at')
    list_filter = ('team',)
    search_fields = ('name', 'description', 'team__name')


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ('original_name', 'task', 'uploaded_by', 'uploaded_at')
    search_fields = ('original_name', 'task__title', 'uploaded_by__username')


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ('user',)
    search_fields = ('user__username',)


@admin.register(ProgressUpdate)
class ProgressUpdateAdmin(admin.ModelAdmin):
    list_display = ('title', 'author', 'created_at')
    search_fields = ('title', 'details', 'author__username')


@admin.register(TaskActivity)
class TaskActivityAdmin(admin.ModelAdmin):
    list_display = ('task_title', 'actor', 'message', 'created_at')
    search_fields = ('task_title', 'actor__username', 'message')


@admin.register(TeamInvite)
class TeamInviteAdmin(admin.ModelAdmin):
    list_display = ('label', 'team', 'code', 'is_active', 'created_by', 'created_at', 'used_by', 'used_at')
    list_filter = ('is_active', 'team')
    search_fields = ('label', 'code', 'created_by__username', 'used_by__username')
    readonly_fields = ('code', 'created_by', 'created_at', 'used_by', 'used_at')
    fields = ('team', 'label', 'code', 'is_active', 'created_by', 'created_at', 'used_by', 'used_at')

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'created_at')
    search_fields = ('name', 'created_by__username')


@admin.register(TeamMembership)
class TeamMembershipAdmin(admin.ModelAdmin):
    list_display = ('team', 'user', 'role', 'joined_at')
    list_filter = ('role', 'team')
    search_fields = ('team__name', 'user__username')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'team', 'message', 'created_at', 'read_at')
    list_filter = ('team', 'read_at')
    search_fields = ('recipient__username', 'message')
