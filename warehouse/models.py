from django.db import models
from django.utils import timezone


class DeliveryQuerySet(models.QuerySet):
    """Section helpers for the three-table delivery dashboard."""

    def for_schedule(self):
        """Section 1 — new deliveries, pending confirmations, failed deliveries."""
        return self.filter(status=Delivery.STATUS_FOR_SCHEDULE)

    def scheduled_on(self, day):
        """Section 2 — active deliveries for the given day."""
        return self.filter(status=Delivery.STATUS_SCHEDULED, scheduled_date=day)

    def accomplished_on(self, day):
        """Section 3 — deliveries completed on the given day."""
        return self.filter(status=Delivery.STATUS_ACCOMPLISHED, accomplished_date=day)


class Delivery(models.Model):
    """
    A single warehouse delivery row.

    Mirrors the columns of the Excel itinerary that was previously emailed
    around, so the sales team can track deliveries in real time instead.
    """

    STATUS_FOR_SCHEDULE = 'FOR_SCHEDULE'
    STATUS_SCHEDULED = 'SCHEDULED'
    STATUS_ACCOMPLISHED = 'ACCOMPLISHED'
    STATUS_CHOICES = [
        (STATUS_FOR_SCHEDULE, 'For Schedule'),
        (STATUS_SCHEDULED, 'Scheduled'),
        (STATUS_ACCOMPLISHED, 'Accomplished'),
    ]

    so_number = models.CharField(
        max_length=100,
        unique=True,
        verbose_name='S.O. / SRF# / POR#',
    )
    client = models.CharField(max_length=255)
    item = models.CharField(max_length=255, verbose_name='Item / Particular')
    area = models.CharField(max_length=255, blank=True)
    driver_staff = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        verbose_name='Driver / Staff',
    )
    vehicle_plate = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Vehicle Plate',
    )
    ae = models.CharField(
        max_length=20,
        verbose_name='AE',
        help_text='Account Executive initials (e.g. CSV, MGA).',
    )
    remarks = models.TextField(blank=True, null=True)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_FOR_SCHEDULE,
        db_index=True,
    )
    scheduled_date = models.DateField(null=True, blank=True)
    accomplished_date = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = DeliveryQuerySet.as_manager()

    class Meta:
        ordering = ['status', 'so_number']
        verbose_name = 'Delivery'
        verbose_name_plural = 'Deliveries'

    def __str__(self):
        return f'{self.so_number} — {self.client}'

    def save(self, *args, **kwargs):
        """Stamp the workflow date as the row moves through the board."""
        today = timezone.localdate()
        if self.status == self.STATUS_SCHEDULED and not self.scheduled_date:
            self.scheduled_date = today
        if self.status == self.STATUS_ACCOMPLISHED and not self.accomplished_date:
            self.accomplished_date = today
        super().save(*args, **kwargs)

    @property
    def is_for_schedule(self):
        return self.status == self.STATUS_FOR_SCHEDULE

    def to_dict(self):
        """JSON-ready payload used by the WebSocket feed."""
        return {
            'id': self.pk,
            'so_number': self.so_number,
            'client': self.client,
            'item': self.item,
            'area': self.area or '',
            'driver_staff': self.driver_staff or '',
            'vehicle_plate': self.vehicle_plate or '',
            'ae': self.ae,
            'remarks': self.remarks or '',
            'status': self.status,
            'scheduled_date': self.scheduled_date.isoformat() if self.scheduled_date else '',
            'accomplished_date': (
                self.accomplished_date.isoformat() if self.accomplished_date else ''
            ),
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
        }
