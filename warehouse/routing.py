from django.urls import path

from .consumers import DeliveryFeedConsumer

websocket_urlpatterns = [
    path('ws/warehouse/deliveries/', DeliveryFeedConsumer.as_asgi()),
]
