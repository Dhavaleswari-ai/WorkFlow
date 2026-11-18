from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer

from .models import TeamMembership


class TeamUpdatesConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        user = self.scope['user']
        self.team_id = int(self.scope['url_route']['kwargs']['team_id'])
        if not user.is_authenticated or not await self.is_team_member(user.id, self.team_id):
            await self.close(code=4403)
            return

        self.group_name = f'team_{self.team_id}'
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if hasattr(self, 'group_name'):
            await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def team_update(self, event):
        await self.send_json({
            'event': event.get('event', 'updated'),
            'task_id': event.get('task_id'),
        })

    @database_sync_to_async
    def is_team_member(self, user_id, team_id):
        return TeamMembership.objects.filter(user_id=user_id, team_id=team_id).exists()
