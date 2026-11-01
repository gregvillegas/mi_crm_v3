from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from users.models import User

from .models import Delivery, WarehouseStaff


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
        self.warehouse_user = User.objects.create_user(
            username='wh_office',
            password='testpass123',
            role='warehouse',
            email='wh_office@example.com',
        )
        self.supervisor = User.objects.create_user(
            username='wh_sup',
            password='testpass123',
            role='supervisor',
            email='wh_sup@example.com',
        )
        self.warehouse_staff = WarehouseStaff.objects.create(name='R. Santos')

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
            driver_staff='J. Cruz', warehouse_staff=self.warehouse_staff,
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
        self.client.force_login(self.supervisor)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertIn('attachment; filename="deliveries_', response['Content-Disposition'])

    def test_export_forbidden_for_salesperson(self):
        # The Account Manager role may read the board but not export it.
        self.client.force_login(self.user)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 403)

    def test_export_allowed_for_warehouse_role(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 200)

    def test_export_forbidden_for_role_outside_monitoring_gate(self):
        self.client.force_login(self.outsider)

        response = self.client.get(reverse('warehouse:export'))

        self.assertEqual(response.status_code, 403)


class DeliveryEditViewTests(TestCase):
    """Add / update access rules for the warehouse office role."""

    def setUp(self):
        self.warehouse_user = User.objects.create_user(
            username='wh_editor', password='testpass123', role='warehouse',
            email='wh_editor@example.com',
        )
        self.salesperson = User.objects.create_user(
            username='wh_reader', password='testpass123', role='salesperson',
            email='wh_reader@example.com',
        )
        self.staff = WarehouseStaff.objects.create(name='M. Reyes')
        self.delivery = Delivery.objects.create(
            so_number='S.O. 4001', client='Acme Corp', item='Switch',
            area='Makati', ae='CSV', status=Delivery.STATUS_FOR_SCHEDULE,
        )

    def test_warehouse_role_can_create_delivery(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.post(reverse('warehouse:create'), {
            'so_number': 'S.O. 4002',
            'client': 'New Client',
            'item': 'Router',
            'area': 'Pasig',
            'ae': 'MGA',
            'warehouse_staff': self.staff.pk,
            'status': Delivery.STATUS_FOR_SCHEDULE,
        })

        self.assertRedirects(response, reverse('warehouse:dashboard'))
        self.assertTrue(Delivery.objects.filter(so_number='S.O. 4002').exists())

    def test_warehouse_role_can_update_delivery(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.post(
            reverse('warehouse:update', args=[self.delivery.pk]),
            {
                'so_number': self.delivery.so_number,
                'client': self.delivery.client,
                'item': self.delivery.item,
                'area': self.delivery.area,
                'ae': self.delivery.ae,
                'warehouse_staff': self.staff.pk,
                'status': Delivery.STATUS_ACCOMPLISHED,
            },
        )

        self.assertRedirects(response, reverse('warehouse:dashboard'))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_ACCOMPLISHED)
        self.assertEqual(self.delivery.warehouse_staff, self.staff)

    def test_salesperson_cannot_create_delivery(self):
        self.client.force_login(self.salesperson)

        response = self.client.get(reverse('warehouse:create'))

        self.assertEqual(response.status_code, 403)

    def test_salesperson_cannot_update_delivery(self):
        self.client.force_login(self.salesperson)

        response = self.client.get(reverse('warehouse:update', args=[self.delivery.pk]))

        self.assertEqual(response.status_code, 403)

    def test_warehouse_role_sees_edit_and_create_controls(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertContains(response, 'data-can-edit="1"')
        self.assertContains(response, reverse('warehouse:create'))
        self.assertContains(
            response, reverse('warehouse:update', args=[self.delivery.pk])
        )

    def test_reader_role_does_not_see_edit_controls(self):
        self.client.force_login(self.salesperson)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertContains(response, 'data-can-edit="0"')
        self.assertNotContains(response, '>New Delivery<')


class DeliveryHistoryViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wh_hist', password='testpass123', role='salesperson',
            email='wh_hist@example.com',
        )
        self.staff = WarehouseStaff.objects.create(name='L. Bautista')
        Delivery.objects.create(
            so_number='S.O. 5001', client='Done Corp', item='Printer',
            area='Makati', ae='CSV', status=Delivery.STATUS_ACCOMPLISHED,
            driver_staff='J. Cruz', warehouse_staff=self.staff,
        )
        Delivery.objects.create(
            so_number='S.O. 5002', client='Pending Corp', item='Scanner',
            area='Pasig', ae='MGA', status=Delivery.STATUS_FOR_SCHEDULE,
        )

    def test_history_requires_login(self):
        response = self.client.get(reverse('warehouse:history'))

        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_history_lists_only_completed_deliveries(self):
        self.client.force_login(self.user)

        response = self.client.get(reverse('warehouse:history'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Done Corp')
        self.assertContains(response, 'Printer')
        self.assertContains(response, 'J. Cruz')
        self.assertContains(response, 'L. Bautista')
        self.assertNotContains(response, 'Pending Corp')

    def test_history_forbidden_for_role_outside_monitoring_gate(self):
        outsider = User.objects.create_user(
            username='wh_hist_out', password='testpass123', role='marketing',
            email='wh_hist_out@example.com',
        )
        self.client.force_login(outsider)

        response = self.client.get(reverse('warehouse:history'))

        self.assertEqual(response.status_code, 403)


class WarehouseSoftLockTests(TestCase):
    """Warehouse staff are restricted to the warehouse app."""

    def setUp(self):
        self.warehouse_user = User.objects.create_user(
            username='wh_lock', password='testpass123', role='warehouse',
            email='wh_lock@example.com',
        )

    def test_home_redirects_warehouse_to_delivery_board(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('home'))

        self.assertRedirects(response, reverse('warehouse:dashboard'))

    def test_sales_monitoring_dashboard_forbidden_for_warehouse(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('sales_monitoring:dashboard'))

        self.assertEqual(response.status_code, 403)

    def test_proposal_list_forbidden_for_warehouse(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('proposal_list'))

        self.assertEqual(response.status_code, 403)

    def test_navbar_hides_other_modules_for_warehouse(self):
        self.client.force_login(self.warehouse_user)

        response = self.client.get(reverse('warehouse:dashboard'))

        self.assertContains(response, reverse('warehouse:dashboard'))
        self.assertNotContains(response, 'Company Shared')
        self.assertNotContains(response, 'Mass Mailing')
