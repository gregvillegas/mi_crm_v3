from django.conf import settings
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


class BacklogReason(models.Model):
    """Managed lookup list for structured backlog / failed-delivery reasons."""

    GROUP_CUSTOMER = 'CUSTOMER'
    GROUP_SALES = 'SALES'
    GROUP_WAREHOUSE = 'WAREHOUSE'
    GROUP_LOGISTICS = 'LOGISTICS'
    GROUP_SITE = 'SITE'
    GROUP_SYSTEM = 'SYSTEM'
    GROUP_CHOICES = [
        (GROUP_CUSTOMER, 'Customer'),
        (GROUP_SALES, 'Sales Coordination'),
        (GROUP_WAREHOUSE, 'Warehouse/Internal'),
        (GROUP_LOGISTICS, 'Logistics'),
        (GROUP_SITE, 'Site/Compliance'),
        (GROUP_SYSTEM, 'System/Process'),
    ]

    name = models.CharField(max_length=120, unique=True)
    reason_group = models.CharField(max_length=20, choices=GROUP_CHOICES)
    sort_order = models.PositiveIntegerField(default=100)
    is_active = models.BooleanField(
        default=True,
        help_text='Uncheck to hide this reason from new selections without losing history.',
    )

    class Meta:
        ordering = ['reason_group', 'sort_order', 'name']
        verbose_name = 'Backlog Reason'
        verbose_name_plural = 'Backlog Reasons'

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
            .select_related('warehouse_staff', 'backlog_reason')
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
    backlog_reason = models.ForeignKey(
        BacklogReason,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='deliveries',
    )
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
        old_instance = None
        old_status = None
        old_remarks = ''
        old_backlog_reason_name = ''
        was_created = self.pk is None
        note = (getattr(self, '_event_note', '') or '').strip()
        actor = getattr(self, '_event_user', None)
        skip_event_log = getattr(self, '_skip_event_log', False)
        tracked_change = was_created

        if self.pk:
            old_instance = Delivery.objects.get(pk=self.pk)
            old_status = old_instance.status
            old_remarks = old_instance.remarks or ''
            old_backlog_reason_name = (
                old_instance.backlog_reason.name if old_instance.backlog_reason_id else ''
            )
            tracked_change = any(
                [
                    old_instance.client != self.client,
                    old_instance.item != self.item,
                    (old_instance.area or '') != (self.area or ''),
                    (old_instance.driver_staff or '') != (self.driver_staff or ''),
                    (old_instance.vehicle_plate or '') != (self.vehicle_plate or ''),
                    old_instance.warehouse_staff_id != self.warehouse_staff_id,
                    old_instance.ae != self.ae,
                    (old_instance.remarks or '') != (self.remarks or ''),
                    old_instance.backlog_reason_id != self.backlog_reason_id,
                    old_instance.status != self.status,
                    old_instance.scheduled_date != self.scheduled_date,
                    old_instance.accomplished_date != self.accomplished_date,
                ]
            )
            # If moving from Scheduled/Accomplished back to For Schedule, mark as backlog.
            if (
                old_instance.status != self.STATUS_FOR_SCHEDULE
                and self.status == self.STATUS_FOR_SCHEDULE
            ):
                self.is_backlog = True
                self.backlog_count = old_instance.backlog_count + 1

        if self.status == self.STATUS_SCHEDULED and not self.scheduled_date:
            self.scheduled_date = today
        if self.status == self.STATUS_ACCOMPLISHED and not self.accomplished_date:
            self.accomplished_date = today
        super().save(*args, **kwargs)

        if not skip_event_log and tracked_change:
            if was_created:
                action = DeliveryEvent.ACTION_CREATED
            elif old_status != self.status:
                action = DeliveryEvent.ACTION_STATUS_CHANGED
            elif old_remarks != (self.remarks or ''):
                action = DeliveryEvent.ACTION_REMARKS_CHANGED
            else:
                action = DeliveryEvent.ACTION_UPDATED

            DeliveryEvent.objects.create(
                delivery=self,
                so_number=self.so_number,
                action=action,
                from_status=old_status,
                to_status=self.status,
                previous_remarks=old_remarks,
                remarks=self.remarks or '',
                previous_backlog_reason=old_backlog_reason_name,
                backlog_reason=self.backlog_reason.name if self.backlog_reason_id else '',
                note=note,
                changed_by=actor if getattr(actor, 'pk', None) else None,
            )

        for attr in ('_event_note', '_event_user', '_skip_event_log'):
            if hasattr(self, attr):
                delattr(self, attr)

    @property
    def is_for_schedule(self):
        return self.status == self.STATUS_FOR_SCHEDULE

    @property
    def warehouse_staff_name(self):
        return self.warehouse_staff.name if self.warehouse_staff else ''

    @property
    def backlog_reason_name(self):
        return self.backlog_reason.name if self.backlog_reason else ''

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
            'backlog_reason': self.backlog_reason_name,
            'status': self.status,
            'is_backlog': self.is_backlog,
            'backlog_count': self.backlog_count,
            'scheduled_date': self.scheduled_date.isoformat() if self.scheduled_date else '',
            'accomplished_date': (
                self.accomplished_date.isoformat() if self.accomplished_date else ''
            ),
            'updated_at': self.updated_at.isoformat() if self.updated_at else '',
        }


def get_transition_remarks_error(old_status, new_status, remarks):
    """Return the required operator note for status changes, if any."""
    if not new_status or old_status == new_status:
        return ''

    if new_status == Delivery.STATUS_SCHEDULED and not remarks:
        return 'Please enter scheduling remarks before moving this delivery to Scheduled.'

    if new_status == Delivery.STATUS_ACCOMPLISHED and not remarks:
        return 'Please enter completion remarks before marking this delivery Accomplished.'

    if old_status != Delivery.STATUS_FOR_SCHEDULE and new_status == Delivery.STATUS_FOR_SCHEDULE and not remarks:
        return 'Please enter a backlog reason before moving this delivery back to For Schedule.'

    return ''


def get_transition_backlog_reason_error(old_status, new_status, backlog_reason):
    """Return the required structured backlog reason for status changes, if any."""
    if (
        old_status != Delivery.STATUS_FOR_SCHEDULE
        and new_status == Delivery.STATUS_FOR_SCHEDULE
        and backlog_reason is None
    ):
        return 'Please select a backlog category before moving this delivery back to For Schedule.'

    return ''


class DeliveryEvent(models.Model):
    """Immutable timeline entry for status/remark changes on a delivery."""

    ACTION_CREATED = 'CREATED'
    ACTION_UPDATED = 'UPDATED'
    ACTION_STATUS_CHANGED = 'STATUS_CHANGED'
    ACTION_REMARKS_CHANGED = 'REMARKS_CHANGED'
    ACTION_CHOICES = [
        (ACTION_CREATED, 'Created'),
        (ACTION_UPDATED, 'Updated'),
        (ACTION_STATUS_CHANGED, 'Status changed'),
        (ACTION_REMARKS_CHANGED, 'Remarks changed'),
    ]

    delivery = models.ForeignKey(
        Delivery,
        on_delete=models.CASCADE,
        related_name='events',
    )
    so_number = models.CharField(max_length=100, db_index=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    from_status = models.CharField(
        max_length=20,
        choices=Delivery.STATUS_CHOICES,
        null=True,
        blank=True,
    )
    to_status = models.CharField(
        max_length=20,
        choices=Delivery.STATUS_CHOICES,
        null=True,
        blank=True,
    )
    previous_remarks = models.TextField(blank=True)
    remarks = models.TextField(blank=True)
    previous_backlog_reason = models.CharField(max_length=120, blank=True)
    backlog_reason = models.CharField(max_length=120, blank=True)
    note = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='warehouse_delivery_events',
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at', '-pk']
        verbose_name = 'Delivery Event'
        verbose_name_plural = 'Delivery Events'

    def __str__(self):
        return f'{self.so_number} — {self.get_action_display()}'
