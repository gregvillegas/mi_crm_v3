from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User

from .models import Delivery


class DeliveryModelTests(TestCase):
    def test_scheduled_status_stamps_scheduled_date(self):
        today = timezone.localdate()
        delivery = Delivery.objects.create(
            so_number='S.O. 1001',
            client='Acme Corp',
            item='Network Switch',
            area='Makati',
            ae='CSV',
            status=Delivery.STATUS_SCHEDULED,
        )

        self.assertEqual(delivery.scheduled_date, today)

    def test_accomplished_status_stamps_accomplished_date(self):
        today = timezone.localdate()
        delivery = Delivery.objects.create(
            so_number='S.O. 1002',
            client='Beta Inc',
            item='Server Rack',
            area='Pasig',
            ae='MGA',
            status=Delivery.STATUS_ACCOMPLISHED,
        )

        self.assertEqual(delivery.accomplished_date, today)

    def test_existing_dates_are_not_overwritten(self):
        past = timezone.localdate() - timedelta(days=3)
        delivery = Delivery.objects.create(
            so_number='S.O. 1003',
            client='Gamma Co',
            item='Laptop',
            area='Taguig',
            ae='CSV',
            status=Delivery.STATUS_SCHEDULED,
            scheduled_date=past,
        )

        self.assertEqual(delivery.scheduled_date, past)

    def test_for_schedule_queryset_excludes_other_statuses(self):
        Delivery.objects.create(
            so_number='S.O. 1004', client='A', item='X', area='A1', ae='CSV',
            status=Delivery.STATUS_FOR_SCHEDULE, remarks='WAITING FOR AES CONFIRMATION',
        )
        Delivery.objects.create(
            so_number='S.O. 1005', client='B', item='Y', area='A2', ae='CSV',
            status=Delivery.STATUS_ACCOMPLISHED,
        )

        self.assertEqual(
            list(Delivery.objects.for_schedule().values_list('so_number', flat=True)),
            ['S.O. 1004'],
        )

    def test_to_dict_serialises_dates_for_the_websocket_payload(self):
        delivery = Delivery.objects.create(
            so_number='S.O. 1006', client='Delta', item='Router', area='Pasay',
            ae='MGA', status=Delivery.STATUS_SCHEDULED, vehicle_plate='ABC 123',
            driver_staff='J. Cruz',
        )

        payload = delivery.to_dict()

        self.assertEqual(payload['so_number'], 'S.O. 1006')
        self.assertEqual(payload['status'], Delivery.STATUS_SCHEDULED)
        self.assertEqual(payload['vehicle_plate'], 'ABC 123')
        self.assertEqual(payload['scheduled_date'], delivery.scheduled_date.isoformat())
        self.assertEqual(payload['accomplished_date'], '')


class DeliveryDashboardViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wh_seller',
            password='testpass123',
            role='salesperson',
            email='wh_seller@example.com',
            initials='WHS',
        )
        self.outsider = User.objects.create_user(
            username='wh_marketing',
            password='testpass123',
            role='marketing',
            email='wh_marketing@example.com',
        )

        today = timezone.localdate()
        Delivery.objects.create(
            so_number='S.O. 2001', client='Acme Corp', item='Network Switch',
            area='Makati', ae='CSV', status=Delivery.STATUS_FOR_SCHEDULE,
            remarks='WAITING FOR AES CONFIRMATION',
        )
        Delivery.objects.create(
            so_number='S.O. 2002', client='Beta Inc', item='Server Rack',
            area='Pasig', ae='MGA', status=Delivery.STATUS_SCHEDULED,
            vehicle_plate='ABC 123', driver_staff='J. Cruz',
            scheduled_date=today,
        )
        Delivery.objects.create(
            so_number='S.O. 2003', client='Gamma Co', item='Laptop',
            area='Taguig', ae='CSV', status=Delivery.STATUS_ACCOMPLISHED,
            accomplished_date=today - timedelta(days=1),
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_dashboard_forbidden_for_role_outside_monitoring_gate(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertEqual(response.status_code, 403)

    def test_dashboard_renders_three_sections_and_van_details(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'FOR SCHEDULE')
        self.assertContains(response, 'SCHEDULED DELIVERY')
        self.assertContains(response, 'ACCOMPLISHED DELIVERY')
        self.assertContains(response, 'VAN DETAILS')
        self.assertContains(response, 'ABC 123')
        self.assertContains(response, 'J. Cruz')
        self.assertContains(response, 'S.O. 2001')
        self.assertContains(response, 'S.O. 2002')
        self.assertContains(response, 'S.O. 2003')

    def test_for_schedule_remarks_render_in_bold_red(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertContains(response, 'remarks-urgent')
        self.assertContains(response, 'WAITING FOR AES CONFIRMATION')

    def test_selected_date_moves_accomplished_section(self):
        two_days_ago = timezone.localdate() - timedelta(days=2)
        Delivery.objects.create(
            so_number='S.O. 2004', client='Delta', item='Router', area='Pasay',
            ae='MGA', status=Delivery.STATUS_ACCOMPLISHED,
            accomplished_date=two_days_ago,
        )
        self.client.force_login(self.user)

        # Selecting yesterday makes "yesterday minus one day" the accomplished day.
        response = self.client.get(
            reverse('warehouse:dashboard'),
            {'date': (timezone.localdate() - timedelta(days=1)).isoformat()},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'S.O. 2004')

    def test_export_returns_xlsx_attachment(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="deliveries_', response['Content-Disposition'])

    def test_export_forbidden_for_role_outside_monitoring_gate(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 403)
