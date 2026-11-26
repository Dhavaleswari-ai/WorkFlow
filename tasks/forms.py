from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.core.validators import MinLengthValidator
from django.core.exceptions import ValidationError

from .models import ProgressUpdate, Project, Task, TaskAttachment, TaskComment, Team, TeamInvite, TeamMembership, UserProfile


class SignupForm(UserCreationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].widget.attrs.update({
            'class': 'text-input',
            'autocomplete': 'username',
            'placeholder': 'Choose a username',
        })
        self.fields['password1'].validators.append(MinLengthValidator(9))
        self.fields['password1'].help_text = (
            'Use at least 9 characters. Avoid common or all-number passwords, and don’t make it too similar to your username.'
        )
        self.fields['password1'].widget.attrs.update({
            'class': 'text-input',
            'autocomplete': 'new-password',
            'placeholder': 'At least 9 characters',
        })
        self.fields['password2'].widget.attrs.update({
            'class': 'text-input',
            'autocomplete': 'new-password',
            'placeholder': 'Enter your password again',
        })
        for field in self.fields.values():
            field.error_messages['required'] = 'This field is mandatory.'

    class Meta:
        model = get_user_model()
        fields = ('username',)

class TaskForm(forms.ModelForm):
    def __init__(self, *args, team=None, **kwargs):
        super().__init__(*args, **kwargs)
        if team is not None:
            self.fields['project'].queryset = Project.objects.filter(team=team)
            self.fields['project'].empty_label = 'No project'
            self.fields['assigned_to'].queryset = get_user_model().objects.filter(
                team_memberships__team=team,
            ).order_by('username').distinct()
        else:
            self.fields['project'].queryset = Project.objects.none()

    class Meta:
        model = Task
        fields = ['title', 'description', 'project', 'assigned_to', 'status', 'priority', 'due_date']
        labels = {
            'project': 'Project',
            'assigned_to': 'Assign to',
            'status': 'Status',
            'priority': 'Priority',
            'due_date': 'Due date',
        }
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'e.g. Plan my week',
                'class': 'text-input',
                'maxlength': 160,
            }),
            'description': forms.Textarea(attrs={
                'placeholder': 'Add a note (optional)',
                'class': 'text-input description-input',
                'rows': 2,
            }),
            'project': forms.Select(attrs={'class': 'text-input select-input'}),
            'assigned_to': forms.Select(attrs={'class': 'text-input select-input'}),
            'status': forms.Select(attrs={'class': 'text-input select-input'}),
            'priority': forms.Select(attrs={'class': 'text-input select-input'}),
            'due_date': forms.DateInput(attrs={'class': 'text-input date-input', 'type': 'date'}),
        }


class ProjectForm(forms.ModelForm):
    class Meta:
        model = Project
        fields = ['name', 'description', 'start_date', 'due_date']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'text-input',
                'placeholder': 'e.g. Website redesign',
                'maxlength': 120,
            }),
            'description': forms.Textarea(attrs={
                'class': 'text-input description-input',
                'placeholder': 'What is this project about? (optional)',
                'rows': 3,
            }),
            'start_date': forms.DateInput(attrs={'class': 'text-input', 'type': 'date'}),
            'due_date': forms.DateInput(attrs={'class': 'text-input', 'type': 'date'}),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        due_date = cleaned_data.get('due_date')
        if start_date and due_date and due_date < start_date:
            self.add_error('due_date', 'The project due date must be on or after its start date.')
        return cleaned_data


class TaskAttachmentForm(forms.ModelForm):
    class Meta:
        model = TaskAttachment
        fields = ['file']
        widgets = {'file': forms.ClearableFileInput(attrs={'class': 'text-input'})}

    def clean_file(self):
        uploaded_file = self.cleaned_data['file']
        allowed_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.doc', '.docx', '.xls', '.xlsx', '.txt', '.csv'}
        extension = '.' + uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
        if extension not in allowed_extensions:
            raise ValidationError('Attach a PDF, image, Word, Excel, text, or CSV file.')
        if uploaded_file.size > 10 * 1024 * 1024:
            raise ValidationError('Files must be 10 MB or smaller.')
        return uploaded_file


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ['avatar']
        widgets = {'avatar': forms.ClearableFileInput(attrs={'class': 'text-input', 'accept': 'image/png,image/jpeg,image/gif,image/webp'})}

    def clean_avatar(self):
        uploaded_file = self.cleaned_data.get('avatar')
        if not uploaded_file:
            return uploaded_file
        if uploaded_file.size > 3 * 1024 * 1024:
            raise ValidationError('Profile pictures must be 3 MB or smaller.')
        extension = '.' + uploaded_file.name.rsplit('.', 1)[-1].lower() if '.' in uploaded_file.name else ''
        signatures = {
            '.png': lambda data: data.startswith(b'\x89PNG\r\n\x1a\n'),
            '.jpg': lambda data: data.startswith(b'\xff\xd8\xff'),
            '.jpeg': lambda data: data.startswith(b'\xff\xd8\xff'),
            '.gif': lambda data: data.startswith((b'GIF87a', b'GIF89a')),
            '.webp': lambda data: len(data) >= 12 and data[:4] == b'RIFF' and data[8:12] == b'WEBP',
        }
        checker = signatures.get(extension)
        uploaded_file.seek(0)
        signature = uploaded_file.read(12)
        uploaded_file.seek(0)
        if checker is None or not checker(signature):
            raise ValidationError('Choose a valid PNG, JPEG, GIF, or WebP image.')
        return uploaded_file


class ProgressUpdateForm(forms.ModelForm):
    class Meta:
        model = ProgressUpdate
        fields = ['title', 'details']
        widgets = {
            'title': forms.TextInput(attrs={
                'placeholder': 'What did you work on? (e.g. Built the task page)',
                'class': 'text-input',
                'maxlength': 120,
            }),
            'details': forms.Textarea(attrs={
                'placeholder': 'Describe what you completed and how you did it.',
                'class': 'text-input description-input',
                'rows': 3,
            }),
        }


class TaskCommentForm(forms.ModelForm):
    class Meta:
        model = TaskComment
        fields = ['message']
        widgets = {
            'message': forms.Textarea(attrs={
                'placeholder': 'Write a comment for your team…',
                'class': 'text-input comment-input',
                'rows': 2,
                'maxlength': 1000,
            }),
        }


class CreateTeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ['name']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'text-input',
                'placeholder': 'e.g. Product team',
                'maxlength': 120,
            }),
        }


class TeamInviteForm(forms.ModelForm):
    class Meta:
        model = TeamInvite
        fields = ['label']
        widgets = {
            'label': forms.TextInput(attrs={
                'class': 'text-input',
                'placeholder': 'Optional: who is this invite for?',
                'maxlength': 100,
            }),
        }


class JoinTeamForm(forms.Form):
    invite_code = forms.CharField(
        max_length=64,
        label='Team invite code',
        widget=forms.TextInput(attrs={
            'class': 'text-input',
            'placeholder': 'Paste a team invite code',
            'autocomplete': 'off',
        }),
    )

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_invite_code(self):
        code = self.cleaned_data['invite_code'].strip()
        invite = TeamInvite.objects.filter(code=code, is_active=True).select_related('team').first()
        if invite is None:
            raise ValidationError('This invite code is invalid or has been revoked.')
        if self.user and TeamMembership.objects.filter(team=invite.team, user=self.user).exists():
            raise ValidationError('You are already a member of this team.')
        self.validated_invite = invite
        return code


