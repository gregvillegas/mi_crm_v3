"""
WebSocket consumer for the Warehouse Deliveries dashboard.

Every delivery change (create / update / delete) is broadcast to a single
global group. The dashboard template listens on that group and moves the
affected row between the three sections ("For Schedule", "Scheduled",
"Accomplished") without reloading the page.
"""
import json
import logging

from asgiref.sync import async_to_sync
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

# Single global broadcast group shared by all connected dashboards.
# The payload carries the ``ae`` initials, so the browser can optionally
# ignore events that do not belong to the logged-in salesperson.
DELIVERY_FEED_GROUP = 'warehouse_deliveries'


class DeliveryFeedConsumer(AsyncWebsocketConsumer):
    """Pushes delivery create/update/delete events to connected dashboards."""

    async def connect(self):
        user = self.scope.get('user')
        if user is None or not user.is_authenticated:
            # Internal-only board: refuse anonymous sockets.
            await self.close(code=4401)
            return

        self.group_name = DELIVERY_FEED_GROUP
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        if getattr(self, 'group_name', None):
            await self.channel_layer.group_discard(
                self.group_name, self.channel_name
            )

    async def receive(self, text_data=None, bytes_data=None):
        # The board is a read-only feed; client messages are ignored.
        return

    async def delivery_event(self, event):
        """Fan a delivery payload out to the browser as JSON."""
        await self.send(text_data=json.dumps(event['payload']))


def broadcast_delivery_event(delivery, event_type):
    """
    Broadcast a delivery change to every connected dashboard.

    Called from the post_save/post_delete receivers so that a status change
    made anywhere (dashboard, Django admin inline edit, shell) reaches the
    open browsers immediately.
    """
    if delivery is None:
        return

    channel_layer = get_channel_layer()
    if channel_layer is None:
        # No channel layer configured (e.g. during tests) — nothing to do.
        return

    payload = {'event': event_type, 'delivery': delivery.to_dict()}
    try:
        async_to_sync(channel_layer.group_send)(
            DELIVERY_FEED_GROUP,
            {'type': 'delivery.event', 'payload': payload},
        )
    except Exception:
        # A failed broadcast must never break the save/delete that triggered it.
        logger.exception('Failed to broadcast delivery event for pk=%s', delivery.pk)
