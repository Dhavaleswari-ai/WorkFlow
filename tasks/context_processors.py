from django.conf import settings


def push_settings(request):
    return {'VAPID_PUBLIC_KEY': settings.VAPID_PUBLIC_KEY}
