from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from .consumers import broadcast_delivery_event
from .models import Delivery


@receiver(post_save, sender=Delivery)
def broadcast_delivery_saved(sender, instance, created, **kwargs):
    broadcast_delivery_event(instance, 'created' if created else 'updated')


@receiver(post_delete, sender=Delivery)
def broadcast_delivery_deleted(sender, instance, **kwargs):
    broadcast_delivery_event(instance, 'deleted')
