from django.db import models
from django.utils import timezone


class WarehouseStaff(models.Model):
    """
    A warehouse person who can be credited on a delivery.

    Deliberately not a User account: drivers and helpers do not log in, they
    only need to appear in the "warehouse staff" dropdown and history report.
    """

    name = models.CharField(max_length=120, unique=True)
    is_active = models.BooleanField(
        default=True,
        help_text='Uncheck to hide from the dropdown without losing history.',
    )

    class Meta:
        ordering = ['name']
        verbose_name = 'Warehouse Staff'
        verbose_name_plural = 'Warehouse Staff'

    def __str__(self):
        return self.name


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

    def delivery_history(self):
        """
        All scheduled or completed deliveries, plus any backlog items, newest first.
        """
        return (
            self.exclude(
                models.Q(status=Delivery.STATUS_FOR_SCHEDULE) & models.Q(is_backlog=False)
            )
            .select_related('warehouse_staff')
            .order_by('-scheduled_date', '-accomplished_date', 'so_number')
        )


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
    warehouse_staff = models.ForeignKey(
        WarehouseStaff,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries',
        verbose_name='Warehouse Staff',
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
    is_backlog = models.BooleanField(default=False, db_index=True)
    backlog_count = models.PositiveIntegerField(default=0)
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
        """Stamp the workflow date and detect backlog transitions."""
        today = timezone.localdate()

        if self.pk:
            old_instance = Delivery.objects.get(pk=self.pk)
            # If moving from Scheduled/Accomplished back to For Schedule, mark as backlog.
            if (
                old_instance.status != self.STATUS_FOR_SCHEDULE
                and self.status == self.STATUS_FOR_SCHEDULE
            ):
                self.is_backlog = True
                self.backlog_count += 1

        if self.status == self.STATUS_SCHEDULED and not self.scheduled_date:
            self.scheduled_date = today
        if self.status == self.STATUS_ACCOMPLISHED and not self.accomplished_date:
            self.accomplished_date = today
        super().save(*args, **kwargs)

    @property
    def is_for_schedule(self):
        return self.status == self.STATUS_FOR_SCHEDULE

    @property
    def warehouse_staff_name(self):
        return self.warehouse_staff.name if self.warehouse_staff else ''

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
            'warehouse_staff': self.warehouse_staff_name,
            'ae': self.ae,
            'remarks': self.remarks or '',
            'status': self.status,
            'is_backlog': self.is_backlog,
            'backlog_count': self.backlog_count,
            'scheduled_date': self.scheduled_date.isoformat() if self.scheduled_date else '',
            'accomplished_date': (
                self.accomplished_date.isoformat() if self.accomplished_date else ''
            ),
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
        }
