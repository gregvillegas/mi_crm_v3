"""
ASGI config for crm_project project.

It exposes the ASGI callable as a module-level variable named ``application``.
Besides plain HTTP it routes WebSocket connections (used by the Warehouse
Deliveries real-time dashboard).

For more information on this file, see
https://docs.djangoproject.com/en/5.2/howto/deployment/asgi/
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm_project.settings')

# Initialise Django first so the app registry is populated before we import
# anything that touches models (the warehouse routing/consumers).
django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from warehouse.routing import websocket_urlpatterns  # noqa: E402

application = ProtocolTypeRouter(
    {
        'http': django_asgi_app,
        'websocket': AuthMiddlewareStack(URLRouter(websocket_urlpatterns)),
    }
)
