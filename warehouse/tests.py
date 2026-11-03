from django.test import TestCase
from django.urls import reverse
from users.models import User
from .models import Delivery, WarehouseStaff

class DeliveryDashboardViewTests(TestCase):
    def setUp(self):
        self.warehouse_user = User.objects.create_user(
            username='wh_dash', password='testpass123', role='warehouse',
            email='wh_dash@example.com',
        )
        self.salesperson = User.objects.create_user(
            username='wh_sp', password='testpass123', role='salesperson',
            email='wh_sp@example.com',
        )
        self.staff = WarehouseStaff.objects.create(name='R. Santos')
        self.delivery = Delivery.objects.create(
            so_number='S.O. 4001', client='ACME', item='Laptop',
            area='Manila', ae='CSV', status=Delivery.STATUS_SCHEDULED,
            driver_staff='J. Cruz', warehouse_staff=self.staff,
        )

    def test_dashboard_requires_login(self):
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertEqual(response.status_code, 302)

    def test_dashboard_accessible_to_warehouse_role(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_accessible_to_salesperson_role(self):
        self.client.force_login(self.salesperson)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_dashboard_forbidden_for_role_outside_monitoring_gate(self):
        outsider = User.objects.create_user(
            username='wh_dash_out', password='testpass123', role='marketing',
            email='wh_dash_out@example.com',
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertEqual(response.status_code, 403)

    def test_dashboard_van_details_grouping(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
        van_details = response.context['van_details']
        self.assertEqual(len(van_details), 1)
        self.assertEqual(van_details[0]['driver_staff'], 'J. Cruz')

    def test_export_requires_login(self):
        response = self.client.get(reverse('warehouse:export'))
        self.assertEqual(response.status_code, 302)

    def test_export_forbidden_for_salesperson_role(self):
        self.client.force_login(self.salesperson)
        response = self.client.get(reverse('warehouse:export'))
        self.assertEqual(response.status_code, 403)

    def test_export_allowed_for_warehouse_role(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:export'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    def test_warehouse_role_can_create_delivery(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(reverse('warehouse:create'), {
            'so_number': 'S.O. 4002',
            'client': 'Globex',
            'item': 'Server',
            'area': 'Cebu',
            'ae': 'MGA',
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

    def test_delivery_update_status_view(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {'status': Delivery.STATUS_ACCOMPLISHED}
        )
        self.assertEqual(response.status_code, 200)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_ACCOMPLISHED)

    def test_delivery_update_status_forbidden_for_salesperson(self):
        self.client.force_login(self.salesperson)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {'status': Delivery.STATUS_ACCOMPLISHED}
        )
        self.assertEqual(response.status_code, 403)

    def test_warehouse_role_sees_quick_actions_for_scheduled(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertContains(response, 'data-can-edit="1"')
        self.assertContains(response, 'quick-status-btn')
        self.assertContains(response, 'data-status="ACCOMPLISHED"')
        self.assertContains(response, 'data-status="FOR_SCHEDULE"')
        # The edit link is replaced by arrows for scheduled items
        self.assertNotContains(
            response, reverse('warehouse:update', args=[self.delivery.pk])
        )

    def test_warehouse_role_sees_edit_link_for_other_statuses(self):
        self.delivery.status = Delivery.STATUS_FOR_SCHEDULE
        self.delivery.save()
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
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

    def test_history_lists_deliveries(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('warehouse:history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Done Corp')
        self.assertContains(response, 'Printer')
        self.assertContains(response, 'J. Cruz')
        self.assertContains(response, 'L. Bautista')

    def test_history_forbidden_for_role_outside_monitoring_gate(self):
        outsider = User.objects.create_user(
            username='wh_hist_out', password='testpass123', role='marketing',
            email='wh_hist_out@example.com',
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse('warehouse:history'))
        self.assertEqual(response.status_code, 403)

class WarehouseSoftLockTests(TestCase):
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
