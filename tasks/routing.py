from django.urls import path

from .consumers import TeamUpdatesConsumer

websocket_urlpatterns = [
    path('ws/teams/<int:team_id>/', TeamUpdatesConsumer.as_asgi()),
]
