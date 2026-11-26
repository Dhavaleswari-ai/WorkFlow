from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from django.conf import settings
import json
import logging

from .models import Notification, PushSubscription

logger = logging.getLogger(__name__)


def notify_team_members(*, team, actor, recipient_ids, message, task=None):
    recipients = set(recipient_ids)
    if actor is not None:
        recipients.discard(actor.id)
    if not recipients:
        return
    User = get_user_model()
    notifications = Notification.objects.bulk_create([
        Notification(
            recipient_id=user_id,
            team=team,
            actor=actor,
            task=task,
            message=message,
        )
        for user_id in User.objects.filter(
            id__in=recipients,
            team_memberships__team=team,
        ).values_list('id', flat=True).distinct()
    ])
    for notification in notifications:
        send_push_notification(notification)


def send_push_notification(notification):
    if not settings.VAPID_PUBLIC_KEY or not settings.VAPID_PRIVATE_KEY:
        return
    from pywebpush import WebPushException, webpush

    subscriptions = PushSubscription.objects.filter(user=notification.recipient)
    for subscription in subscriptions:
        try:
            webpush(
                subscription_info={
                    'endpoint': subscription.endpoint,
                    'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
                },
                data=json.dumps({
                    'title': notification.team.name,
                    'body': notification.message,
                    'url': '/notifications/',
                }),
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={'sub': settings.VAPID_SUBJECT},
            )
        except WebPushException as error:
            status_code = getattr(getattr(error, 'response', None), 'status_code', None)
            if status_code in (404, 410):
                subscription.delete()
            else:
                logger.warning('Could not send a WorkFlow browser push notification.')
        except Exception:
            logger.warning('Could not send a WorkFlow browser push notification.')


def broadcast_team_event(*, team_id, event, task_id=None):
    channel_layer = get_channel_layer()
    if channel_layer is None:
        return
    async_to_sync(channel_layer.group_send)(
        f'team_{team_id}',
        {
            'type': 'team.update',
            'event': event,
            'task_id': task_id,
        },
    )
