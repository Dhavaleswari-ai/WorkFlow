from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.http import FileResponse, HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.timezone import localdate
from django.utils.text import slugify
from django.views.decorators.http import require_GET
import json
from pathlib import Path
from datetime import date
from urllib.parse import urlsplit
import logging
import calendar as month_calendar
import csv

from .forms import (
    CreateTeamForm,
    JoinTeamForm,
    ProfileForm,
    ProgressUpdateForm,
    ProjectForm,
    SignupForm,
    TaskCommentForm,
    TaskAttachmentForm,
    TaskForm,
    TeamInviteForm,
)
from .models import (
    ProgressUpdate,
    Project,
    Task,
    TaskAttachment,
    TaskActivity,
    TaskComment,
    Team,
    TeamInvite,
    TeamMembership,
    UserProfile,
    Notification,
    PushSubscription,
)
from .services import broadcast_team_event, notify_team_members

logger = logging.getLogger(__name__)


def _active_membership(request):
    memberships = TeamMembership.objects.filter(user=request.user).select_related('team').order_by('joined_at', 'id')
    active_team_id = request.session.get('active_team_id')
    membership = memberships.filter(team_id=active_team_id).first() if active_team_id else None
    if membership is None:
        membership = memberships.first()
    if membership is not None:
        request.session['active_team_id'] = membership.team_id
    return membership


def register(request):
    if request.user.is_authenticated:
        return redirect('task_list')
    if request.method == 'POST':
        form = SignupForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    user = form.save()
                    team = Team.objects.create(
                        name=f"{user.username}'s team"[:120],
                        created_by=user,
                    )
                    TeamMembership.objects.create(
                        team=team,
                        user=user,
                        role=TeamMembership.Role.MANAGER,
                    )
            except IntegrityError:
                form.add_error(None, 'We could not create the account. Please try again.')
            else:
                messages.success(request, 'Account created. Sign in with your username and password.')
                return redirect('login')
    else:
        form = SignupForm()
    return render(request, 'registration/register.html', {'form': form})


@login_required
def project_list(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    team = membership.team

    if request.method == 'POST':
        if membership.role != TeamMembership.Role.MANAGER:
            return HttpResponseForbidden('Only a team manager can create projects.')
        form = ProjectForm(request.POST)
        if form.is_valid():
            project = form.save(commit=False)
            project.team = team
            project.created_by = request.user
            try:
                project.save()
            except IntegrityError:
                form.add_error('name', 'A project with this name already exists in this team.')
            else:
                messages.success(request, f'Project “{project.name}” created.')
                return redirect('project_list')
    else:
        form = ProjectForm()

    projects = Project.objects.filter(team=team).annotate(
        task_count=Count('tasks'),
        completed_task_count=Count('tasks', filter=Q(tasks__status=Task.Status.DONE)),
    )
    for project in projects:
        project.completion_percent = round(
            project.completed_task_count * 100 / project.task_count
        ) if project.task_count else 0

    return render(request, 'tasks/projects.html', {
        'team': team,
        'membership': membership,
        'projects': projects,
        'form': form,
        'my_memberships': TeamMembership.objects.filter(user=request.user).select_related('team'),
        'unread_notification_count': Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
            team=team,
        ).count(),
    })


@login_required
def edit_project(request, project_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if membership.role != TeamMembership.Role.MANAGER:
        return HttpResponseForbidden('Only a team manager can edit projects.')
    project = get_object_or_404(Project, pk=project_id, team=membership.team)
    form = ProjectForm(request.POST or None, instance=project)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, f'Project “{project.name}” updated.')
        return redirect('project_list')
    return render(request, 'tasks/edit_project.html', {
        'team': membership.team,
        'project': project,
        'form': form,
        'membership': membership,
    })


@login_required
def calendar_view(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    today = localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
        if month < 1 or month > 12 or year < 1900 or year > 9998:
            raise ValueError
    except (TypeError, ValueError):
        year, month = today.year, today.month

    month_tasks = Task.objects.filter(
        team=membership.team,
        due_date__year=year,
        due_date__month=month,
    ).select_related('project', 'assigned_to').order_by('due_date', 'title')
    tasks_by_day = {}
    for task in month_tasks:
        tasks_by_day.setdefault(task.due_date.day, []).append(task)
    weeks = [
        [{'day': day, 'tasks': tasks_by_day.get(day, [])} for day in week]
        for week in month_calendar.Calendar(firstweekday=0).monthdayscalendar(year, month)
    ]
    previous_year, previous_month = (year - 1, 12) if month == 1 else (year, month - 1)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    return render(request, 'tasks/calendar.html', {
        'team': membership.team,
        'membership': membership,
        'weeks': weeks,
        'month_name': month_calendar.month_name[month],
        'year': year,
        'today': today,
        'previous_year': previous_year,
        'previous_month': previous_month,
        'next_year': next_year,
        'next_month': next_month,
        'my_memberships': TeamMembership.objects.filter(user=request.user).select_related('team'),
    })


@login_required
def export_analytics_csv(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    tasks = Task.objects.filter(team=membership.team).select_related('project', 'assigned_to', 'created_by')
    project_id = request.GET.get('project', '').strip()
    if project_id:
        if not project_id.isdigit():
            return HttpResponseForbidden('Invalid project selection.')
        project = get_object_or_404(Project, pk=project_id, team=membership.team)
        tasks = tasks.filter(project=project)
        report_name = f'{slugify(project.name) or "project"}-report.csv'
    else:
        report_name = f'{slugify(membership.team.name) or "team"}-report.csv'

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = f'attachment; filename="{report_name}"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['Project', 'Task', 'Status', 'Priority', 'Assigned to', 'Created by', 'Due date', 'Completed'])
    for task in tasks:
        writer.writerow([
            task.project.name if task.project else 'No project',
            task.title,
            task.get_status_display(),
            task.get_priority_display(),
            task.assigned_to.username if task.assigned_to else 'Unassigned',
            task.created_by.username if task.created_by else 'Team',
            task.due_date.isoformat() if task.due_date else '',
            'Yes' if task.status == Task.Status.DONE else 'No',
        ])
    return response


@login_required
def profile_settings(request):
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    old_avatar_name = profile.avatar.name if profile.avatar else ''
    form = ProfileForm(request.POST or None, request.FILES or None, instance=profile)
    if request.method == 'POST' and form.is_valid():
        profile = form.save()
        if old_avatar_name and old_avatar_name != (profile.avatar.name if profile.avatar else ''):
            profile.avatar.storage.delete(old_avatar_name)
        messages.success(request, 'Your profile picture was updated.')
        return redirect('profile_settings')
    return render(request, 'tasks/profile_settings.html', {
        'team': _active_membership(request).team if _active_membership(request) else None,
        'form': form,
        'profile': profile,
    })


@login_required
def profile_icon(request, profile_id):
    profile = get_object_or_404(UserProfile.objects.select_related('user'), pk=profile_id)
    visible_to_user = TeamMembership.objects.filter(
        user=profile.user,
        team__memberships__user=request.user,
    ).exists()
    if profile.user_id != request.user.id and not visible_to_user:
        return HttpResponseForbidden('Profile pictures are visible to teammates only.')
    if not profile.avatar:
        return HttpResponse(status=404)
    suffix = Path(profile.avatar.name).suffix.lower()
    content_types = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp'}
    file_response = FileResponse(profile.avatar.open('rb'), content_type=content_types.get(suffix, 'application/octet-stream'))
    file_response['Cache-Control'] = 'private, max-age=300'
    file_response['X-Content-Type-Options'] = 'nosniff'
    return file_response


@login_required
def task_list(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    team = membership.team

    if request.method == 'POST':
        form = TaskForm(request.POST, team=team)
        if form.is_valid():
            task = form.save(commit=False)
            task.team = team
            task.created_by = request.user
            task.save()
            TaskActivity.objects.create(
                team=team,
                actor=request.user,
                task=task,
                task_title=task.title,
                message='created this task',
            )
            if task.assigned_to_id:
                notify_team_members(
                    team=team,
                    actor=request.user,
                    recipient_ids=[task.assigned_to_id],
                    message=f'{request.user.username} assigned you "{task.title}".',
                    task=task,
                )
            broadcast_team_event(team_id=team.id, event='task_created', task_id=task.id)
            return redirect('tasks_page')
    else:
        form = TaskForm(team=team)

    projects = Project.objects.filter(team=team)
    selected_project = None
    requested_project_id = request.GET.get('project', '').strip()
    if requested_project_id.isdigit():
        selected_project = projects.filter(pk=requested_project_id).first()
    team_tasks = Task.objects.filter(team=team)
    all_tasks = team_tasks
    if selected_project is not None:
        all_tasks = all_tasks.filter(project=selected_project)
    tasks = all_tasks.select_related('created_by', 'assigned_to', 'project').prefetch_related(
        'comments__author', 'activities__actor', 'attachments__uploaded_by',
    )
    query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '')
    priority_filter = request.GET.get('priority', '')
    sort_by = request.GET.get('sort', 'newest')
    if query:
        tasks = tasks.filter(
            Q(title__icontains=query)
            | Q(description__icontains=query)
            | Q(project__name__icontains=query)
            | Q(assigned_to__username__icontains=query)
        )
    if status_filter in Task.Status.values:
        tasks = tasks.filter(status=status_filter)
    if priority_filter in Task.Priority.values:
        tasks = tasks.filter(priority=priority_filter)
    if sort_by == 'due_date':
        tasks = tasks.order_by('due_date', '-created_at')
    elif sort_by == 'priority':
        tasks = tasks.annotate(priority_order=Case(
            When(priority=Task.Priority.URGENT, then=Value(0)),
            When(priority=Task.Priority.HIGH, then=Value(1)),
            When(priority=Task.Priority.MEDIUM, then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )).order_by('priority_order', 'due_date', '-created_at')
    else:
        sort_by = 'newest'
        tasks = tasks.order_by('-created_at')
    updates = ProgressUpdate.objects.filter(team=team).select_related('author')[:12]
    task_activities = TaskActivity.objects.filter(team=team).select_related('actor')[:12]
    member_task_scope = Q(user__assigned_tasks__team=team)
    if request.resolver_match.url_name == 'analytics_page' and selected_project is not None:
        member_task_scope &= Q(user__assigned_tasks__project=selected_project)
    members = TeamMembership.objects.filter(team=team).select_related('user').annotate(
        assigned_task_count=Count('user__assigned_tasks', filter=member_task_scope, distinct=True),
        open_task_count=Count(
            'user__assigned_tasks',
            filter=member_task_scope & ~Q(user__assigned_tasks__status=Task.Status.DONE),
            distinct=True,
        ),
        overdue_task_count=Count(
            'user__assigned_tasks',
            filter=member_task_scope & Q(user__assigned_tasks__due_date__lt=localdate())
            & ~Q(user__assigned_tasks__status=Task.Status.DONE),
            distinct=True,
        ),
        completed_task_count=Count(
            'user__assigned_tasks',
            filter=member_task_scope & Q(user__assigned_tasks__status=Task.Status.DONE),
            distinct=True,
        ),
        progress_update_count=Count(
            'user__progress_updates',
            filter=Q(user__progress_updates__team=team),
            distinct=True,
        ),
    ).order_by('joined_at')
    for member in members:
        member.contribution_count = member.assigned_task_count
        member.contribution_done_percent = round(
            member.completed_task_count * 100 / member.assigned_task_count
        ) if member.assigned_task_count else 0

    chart_colors = ['#7657e8', '#45b989', '#e9a23b', '#4f86d9', '#e16c85', '#45a7a0', '#9b71c8']

    def make_pie_style(items):
        total = sum(item['value'] for item in items)
        if not total:
            return 'background: conic-gradient(#eeedf3 0% 100%)'
        stop = 0
        stops = []
        for item in items:
            item['percentage'] = round(item['value'] * 100 / total)
            next_stop = stop + item['value'] * 100 / total
            stops.append(f"{item['color']} {stop:.2f}% {next_stop:.2f}%")
            stop = next_stop
        return 'background: conic-gradient(' + ', '.join(stops) + ')'

    status_segments = [
        {'label': label, 'value': all_tasks.filter(status=value).count(), 'color': color}
        for (value, label), color in zip(Task.Status.choices, chart_colors)
    ]
    contribution_segments = [
        {
            'label': member.user.username,
            'value': member.contribution_count,
            'color': chart_colors[index % len(chart_colors)],
        }
        for index, member in enumerate(members)
        if member.contribution_count
    ]
    status_chart_style = make_pie_style(status_segments)
    contribution_chart_style = make_pie_style(contribution_segments)
    my_memberships = TeamMembership.objects.filter(user=request.user).select_related('team').order_by('team__name')
    section_templates = {
        'task_list': 'tasks/dashboard.html',
        'tasks_page': 'tasks/tasks_page.html',
        'progress_page': 'tasks/progress.html',
        'analytics_page': 'tasks/analytics.html',
    }
    return render(request, section_templates.get(request.resolver_match.url_name, 'tasks/dashboard.html'), {
        'form': form,
        'tasks': tasks,
        'recent_tasks': tasks[:5],
        'team': team,
        'projects': projects,
        'selected_project': selected_project,
        'project_filter': str(selected_project.pk) if selected_project else '',
        'project_task_counts': {
            project.pk: team_tasks.filter(project=project).count()
            for project in projects
        },
        'membership': membership,
        'query': query,
        'status_filter': status_filter,
        'priority_filter': priority_filter,
        'sort_by': sort_by,
        'my_memberships': my_memberships,
        'task_statuses': Task.Status.choices,
        'task_priorities': Task.Priority.choices,
        'comment_form': TaskCommentForm(),
        'update_form': ProgressUpdateForm(),
        'updates': updates,
        'task_activities': task_activities,
        'members': members,
        'status_segments': status_segments,
        'contribution_segments': contribution_segments,
        'status_chart_style': status_chart_style,
        'contribution_chart_style': contribution_chart_style,
        'todo_count': all_tasks.filter(status=Task.Status.TODO).count(),
        'in_progress_count': all_tasks.filter(status=Task.Status.IN_PROGRESS).count(),
        'remaining_count': all_tasks.exclude(status=Task.Status.DONE).count(),
        'completed_count': all_tasks.filter(status=Task.Status.DONE).count(),
        'total_task_count': all_tasks.count(),
        'overdue_count': all_tasks.filter(
            due_date__lt=localdate(),
        ).exclude(status=Task.Status.DONE).count(),
        'unread_notification_count': Notification.objects.filter(
            recipient=request.user,
            read_at__isnull=True,
            team__memberships__user=request.user,
        ).distinct().count(),
    })


@login_required
def add_task_comment(request, task_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    task = get_object_or_404(Task, id=task_id, team=membership.team)
    if request.method == 'POST':
        form = TaskCommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.task = task
            comment.author = request.user
            comment.save()
            TaskActivity.objects.create(
                team=membership.team,
                actor=request.user,
                task=task,
                task_title=task.title,
                message='commented on this task',
            )
            notify_team_members(
                team=membership.team,
                actor=request.user,
                recipient_ids=TeamMembership.objects.filter(team=membership.team).values_list('user_id', flat=True),
                message=f'{request.user.username} commented on "{task.title}".',
                task=task,
            )
            broadcast_team_event(team_id=membership.team.id, event='comment_added', task_id=task.id)
    return redirect('tasks_page')


@login_required
def add_task_attachment(request, task_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    task = get_object_or_404(Task, pk=task_id, team=membership.team)
    if request.method == 'POST':
        form = TaskAttachmentForm(request.POST, request.FILES)
        if form.is_valid():
            attachment = form.save(commit=False)
            attachment.task = task
            attachment.uploaded_by = request.user
            attachment.original_name = Path(attachment.file.name).name[:255]
            attachment.save()
            TaskActivity.objects.create(
                team=membership.team,
                actor=request.user,
                task=task,
                task_title=task.title,
                message=f'attached {attachment.original_name}',
            )
            broadcast_team_event(team_id=membership.team.id, event='task_edited', task_id=task.id)
            messages.success(request, 'File attached to the task.')
        else:
            messages.error(request, form.errors.get('file', ['The file could not be uploaded.'])[0])
    return redirect('tasks_page')


@login_required
def download_task_attachment(request, attachment_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    attachment = get_object_or_404(
        TaskAttachment.objects.select_related('task'),
        pk=attachment_id,
        task__team=membership.team,
    )
    if not attachment.file:
        return HttpResponse(status=404)
    return FileResponse(
        attachment.file.open('rb'),
        as_attachment=True,
        filename=attachment.original_name,
        content_type='application/octet-stream',
    )


@login_required
def add_progress_update(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if request.method == 'POST':
        form = ProgressUpdateForm(request.POST)
        if form.is_valid():
            update = form.save(commit=False)
            update.team = membership.team
            update.author = request.user
            update.save()
            notify_team_members(
                team=membership.team,
                actor=request.user,
                recipient_ids=TeamMembership.objects.filter(team=membership.team).values_list('user_id', flat=True),
                message=f'{request.user.username} posted a team progress update: "{update.title}".',
            )
            broadcast_team_event(team_id=membership.team.id, event='progress_posted')
    return redirect('progress_page')


@login_required
def edit_task(request, task_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    task = get_object_or_404(Task, id=task_id, team=membership.team)
    if request.method == 'POST':
        form = TaskForm(request.POST, instance=task, team=membership.team)
        if form.is_valid():
            old_values = {
                'title': task.title,
                'description': task.description,
                'status': task.status,
                'project_id': task.project_id,
                'assigned_to_id': task.assigned_to_id,
                'priority': task.priority,
                'due_date': task.due_date,
            }
            task = form.save()
            status_labels = dict(Task.Status.choices)
            changes = []
            if old_values['title'] != task.title:
                changes.append('changed the title')
            if old_values['description'] != task.description:
                changes.append('updated the description')
            if old_values['status'] != task.status:
                changes.append(
                    f"changed the status from {status_labels[old_values['status']]} to {task.get_status_display()}"
                )
            if old_values['project_id'] != task.project_id:
                old_project = Project.objects.filter(pk=old_values['project_id']).first()
                old_name = old_project.name if old_project else 'No project'
                new_name = task.project.name if task.project else 'No project'
                changes.append(f'moved the task from {old_name} to {new_name}')
            if old_values['assigned_to_id'] != task.assigned_to_id:
                old_assignee = get_user_model().objects.filter(pk=old_values['assigned_to_id']).first()
                old_name = old_assignee.username if old_assignee else 'Unassigned'
                new_name = task.assigned_to.username if task.assigned_to else 'Unassigned'
                changes.append(f'changed the assignee from {old_name} to {new_name}')
                if task.assigned_to_id:
                    notify_team_members(
                        team=membership.team,
                        actor=request.user,
                        recipient_ids=[task.assigned_to_id],
                        message=f'{request.user.username} assigned you "{task.title}".',
                        task=task,
                    )
            if old_values['priority'] != task.priority:
                changes.append(f"changed the priority to {task.get_priority_display()}")
            if old_values['due_date'] != task.due_date:
                changes.append('changed the due date')
            for change in changes:
                TaskActivity.objects.create(
                    team=membership.team,
                    actor=request.user,
                    task=task,
                    task_title=task.title,
                    message=change,
                )
            if changes:
                broadcast_team_event(team_id=membership.team.id, event='task_edited', task_id=task.id)
            return redirect('tasks_page')
    else:
        form = TaskForm(instance=task, team=membership.team)
    return render(request, 'tasks/edit_task.html', {
        'form': form,
        'task': task,
        'team': membership.team,
        'membership': membership,
    })


@login_required
def set_task_status(request, task_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, team=membership.team)
        new_status = request.POST.get('status')
        if new_status in Task.Status.values and new_status != task.status:
            old_status = task.get_status_display()
            task.status = new_status
            task.save(update_fields=['status'])
            TaskActivity.objects.create(
                team=membership.team,
                actor=request.user,
                task=task,
                task_title=task.title,
                message=f'changed the status from {old_status} to {task.get_status_display()}',
            )
            notify_team_members(
                team=membership.team,
                actor=request.user,
                recipient_ids=[task.created_by_id, task.assigned_to_id],
                message=f'{request.user.username} changed "{task.title}" to {task.get_status_display()}.',
                task=task,
            )
            broadcast_team_event(team_id=membership.team.id, event='task_status_changed', task_id=task.id)
    return redirect('tasks_page')


@login_required
def delete_task(request, task_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if request.method == 'POST':
        task = get_object_or_404(Task, id=task_id, team=membership.team)
        if task.created_by_id != request.user.id and membership.role != TeamMembership.Role.MANAGER:
            return HttpResponseForbidden('You can only delete tasks you created. A team manager can delete any task.')
        TaskActivity.objects.create(
            team=membership.team,
            actor=request.user,
            task=None,
            task_title=task.title,
            message='deleted this task',
        )
        task.delete()
        broadcast_team_event(team_id=membership.team.id, event='task_deleted', task_id=task_id)
    return redirect('task_list')


@login_required
def team_settings(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    team = membership.team
    members = TeamMembership.objects.filter(team=team).select_related('user').order_by('joined_at')
    invites = TeamInvite.objects.filter(team=team, is_active=True).order_by('-created_at')
    revoked_invites = TeamInvite.objects.filter(team=team, is_active=False).order_by('-created_at')
    my_memberships = TeamMembership.objects.filter(user=request.user).select_related('team').order_by('team__name')
    return render(request, 'tasks/team_settings.html', {
        'team': team,
        'membership': membership,
        'members': members,
        'invites': invites if membership.role == TeamMembership.Role.MANAGER else [],
        'revoked_invites': revoked_invites if membership.role == TeamMembership.Role.MANAGER else [],
        'invite_form': TeamInviteForm(),
        'create_team_form': CreateTeamForm(),
        'join_team_form': JoinTeamForm(user=request.user),
        'my_memberships': my_memberships,
    })


@login_required
def create_team_invite(request):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if membership.role != TeamMembership.Role.MANAGER:
        return HttpResponseForbidden('Only a team manager can create invite codes.')
    if request.method == 'POST':
        form = TeamInviteForm(request.POST)
        if form.is_valid():
            invite = form.save(commit=False)
            invite.team = membership.team
            invite.created_by = request.user
            invite.save()
            messages.success(request, f'Invite code created: {invite.code}')
    return redirect('team_settings')


@login_required
def join_team_with_invite(request):
    if request.method == 'POST':
        form = JoinTeamForm(request.POST, user=request.user)
        if form.is_valid():
            invite = form.validated_invite
            with transaction.atomic():
                active_invite = TeamInvite.objects.filter(
                    pk=invite.pk,
                    is_active=True,
                ).select_related('team').first()
                if active_invite is None:
                    messages.error(request, 'That invite code has been revoked.')
                elif TeamMembership.objects.filter(team=active_invite.team, user=request.user).exists():
                    messages.error(request, 'You are already a member of that team.')
                else:
                    if active_invite.used_at is None:
                        TeamInvite.objects.filter(pk=active_invite.pk, used_at__isnull=True).update(
                            used_by=request.user,
                            used_at=timezone.now(),
                        )
                    TeamMembership.objects.create(
                        team=active_invite.team,
                        user=request.user,
                        role=TeamMembership.Role.MEMBER,
                    )
                    request.session['active_team_id'] = active_invite.team_id
                    messages.success(request, f'You joined {active_invite.team.name}.')
        else:
            messages.error(request, form.errors.get('invite_code', ['Enter a valid invite code.'])[0])
    return redirect('team_settings')


@login_required
def revoke_team_invite(request, invite_id):
    membership = _active_membership(request)
    if membership is None:
        return redirect('create_team')
    if membership.role != TeamMembership.Role.MANAGER:
        return HttpResponseForbidden('Only a team manager can revoke invite codes.')
    if request.method == 'POST':
        invite = get_object_or_404(
            TeamInvite,
            id=invite_id,
            team=membership.team,
            is_active=True,
        )
        invite.is_active = False
        invite.save(update_fields=['is_active'])
        messages.success(request, 'Invite code revoked. Current team members keep their access.')
    return redirect('team_settings')


@login_required
def remove_team_member(request, membership_id):
    manager_membership = _active_membership(request)
    if manager_membership is None:
        return redirect('create_team')
    if manager_membership.role != TeamMembership.Role.MANAGER:
        return HttpResponseForbidden('Only a team manager can remove team members.')
    if request.method == 'POST':
        membership = get_object_or_404(
            TeamMembership.objects.select_related('user'),
            id=membership_id,
            team=manager_membership.team,
            role=TeamMembership.Role.MEMBER,
        )
        username = membership.user.username
        membership.delete()
        messages.success(
            request,
            f'{username} was removed from this team. They can rejoin with an active invite code.',
        )
    return redirect('team_settings')


@login_required
def create_team(request):
    if request.method == 'POST':
        form = CreateTeamForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                team = form.save(commit=False)
                team.created_by = request.user
                team.save()
                TeamMembership.objects.create(
                    team=team,
                    user=request.user,
                    role=TeamMembership.Role.MANAGER,
                )
            request.session['active_team_id'] = team.id
            messages.success(request, f'Created the {team.name} team.')
            return redirect('task_list')
    else:
        form = CreateTeamForm()
    memberships = TeamMembership.objects.filter(user=request.user).select_related('team')
    return render(request, 'tasks/create_team.html', {
        'form': form,
        'my_memberships': memberships,
    })


@login_required
def set_active_team(request):
    if request.method == 'POST':
        membership = get_object_or_404(
            TeamMembership.objects.select_related('team'),
            user=request.user,
            team_id=request.POST.get('team_id'),
        )
        request.session['active_team_id'] = membership.team_id
    return redirect('task_list')


@login_required
def notification_list(request):
    notifications = Notification.objects.filter(
        recipient=request.user,
        team__memberships__user=request.user,
    ).select_related('team', 'actor', 'task').distinct()[:100]
    return render(request, 'tasks/notifications.html', {'notifications': notifications})


@login_required
def mark_notification_read(request, notification_id):
    if request.method == 'POST':
        notification = get_object_or_404(
            Notification,
            id=notification_id,
            recipient=request.user,
            team__memberships__user=request.user,
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=['read_at'])
    return redirect('notification_list')


@login_required
def save_push_subscription(request):
    from django.conf import settings

    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        return JsonResponse({'error': 'Desktop notifications are not configured on this server yet.'}, status=503)
    try:
        data = json.loads(request.body)
        endpoint = data['endpoint']
        keys = data['keys']
        p256dh, auth = keys['p256dh'], keys['auth']
        parsed_endpoint = urlsplit(endpoint)
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({'error': 'Invalid push subscription.'}, status=400)
    allowed_push_hosts = {
        'fcm.googleapis.com',
        'updates.push.services.mozilla.com',
        'push.services.mozilla.com',
        'web.push.apple.com',
    }
    host_is_allowed = (
        parsed_endpoint.hostname in allowed_push_hosts
        or parsed_endpoint.hostname.endswith('.notify.windows.com')
    ) if parsed_endpoint.hostname else False
    if parsed_endpoint.scheme != 'https' or not host_is_allowed:
        return JsonResponse({'error': 'Invalid push service endpoint.'}, status=400)
    if not all(isinstance(value, str) for value in (endpoint, p256dh, auth)):
        return JsonResponse({'error': 'Invalid push subscription.'}, status=400)
    if len(endpoint) > 2048 or len(p256dh) > 255 or len(auth) > 255:
        return JsonResponse({'error': 'Invalid push subscription.'}, status=400)
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth},
    )
    return JsonResponse({'saved': True})


@login_required
def remove_push_subscription(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required.'}, status=405)
    try:
        endpoint = json.loads(request.body)['endpoint']
    except (json.JSONDecodeError, KeyError, TypeError):
        return JsonResponse({'error': 'Invalid push subscription.'}, status=400)
    PushSubscription.objects.filter(user=request.user, endpoint=endpoint).delete()
    return JsonResponse({'saved': True})


@require_GET
@require_GET
def service_worker(request):
    worker_path = Path(__file__).resolve().parent / 'static' / 'tasks' / 'service-worker.js'
    response = HttpResponse(worker_path.read_text(encoding='utf-8'), content_type='application/javascript')
    response['Service-Worker-Allowed'] = '/'
    response['Cache-Control'] = 'no-cache'
    return response
