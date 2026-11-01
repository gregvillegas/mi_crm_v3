from django.apps import AppConfig


class WarehouseConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'warehouse'

    def ready(self):
        # Register the post_save/post_delete receivers that push delivery
        # changes to the connected dashboards over WebSocket.
        from . import signals  # noqa: F401
