import io
from datetime import date

import openpyxl
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from users.models import User
from .models import BacklogReason, Delivery, DeliveryEvent, WarehouseStaff

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
        self.backlog_reason, _ = BacklogReason.objects.get_or_create(
            name='Customer requested reschedule',
            defaults={
                'reason_group': BacklogReason.GROUP_CUSTOMER,
                'sort_order': 10,
            },
        )
        self.delivery = Delivery.objects.create(
            so_number='S.O. 4001', client='ACME', item='Laptop',
            area='Manila', ae='CSV', status=Delivery.STATUS_SCHEDULED,
            scheduled_date=date(2026, 10, 30),
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
        response = self.client.get(
            reverse('warehouse:dashboard'),
            {'date': '2026-10-30'},
        )
        van_details = response.context['van_details']
        self.assertEqual(len(van_details), 1)
        self.assertEqual(van_details[0]['driver_staff'], 'J. Cruz')
        self.assertEqual(van_details[0]['warehouse_staff'], 'R. Santos')
        self.assertEqual(van_details[0]['driver_staff_display'], 'J. Cruz - R. Santos')

    def test_dashboard_includes_backlog_summary(self):
        self.delivery.status = Delivery.STATUS_FOR_SCHEDULE
        self.delivery.remarks = 'Customer unavailable at scheduled slot.'
        self.delivery.backlog_reason = self.backlog_reason
        self.delivery.save()
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Active Backlog')
        self.assertContains(response, self.backlog_reason.name)

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
            'remarks': 'Waiting for customer schedule confirmation.',
            'status': Delivery.STATUS_FOR_SCHEDULE,
        })
        self.assertRedirects(response, reverse('warehouse:dashboard'))
        delivery = Delivery.objects.get(so_number='S.O. 4002')
        self.assertEqual(delivery.events.count(), 1)
        self.assertEqual(delivery.events.first().action, DeliveryEvent.ACTION_CREATED)

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
                'backlog_reason': '',
                'remarks': 'Delivered to customer receiving desk.',
                'status': Delivery.STATUS_ACCOMPLISHED,
            },
        )
        self.assertRedirects(response, reverse('warehouse:dashboard'))
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_ACCOMPLISHED)
        latest_event = self.delivery.events.first()
        self.assertEqual(latest_event.action, DeliveryEvent.ACTION_STATUS_CHANGED)
        self.assertEqual(latest_event.changed_by, self.warehouse_user)
        self.assertEqual(latest_event.remarks, 'Delivered to customer receiving desk.')

    def test_delivery_update_status_view(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_ACCOMPLISHED,
                'remarks': 'Completed and received by guard.',
                'backlog_reason': '',
                'accomplished_date': '2026-10-30',
            }
        )
        self.assertEqual(response.status_code, 200)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_ACCOMPLISHED)
        self.assertEqual(self.delivery.remarks, 'Completed and received by guard.')
        self.assertEqual(self.delivery.accomplished_date, date(2026, 10, 30))
        latest_event = self.delivery.events.first()
        self.assertEqual(latest_event.action, DeliveryEvent.ACTION_STATUS_CHANGED)
        self.assertEqual(latest_event.changed_by, self.warehouse_user)

    def test_delivery_update_status_forbidden_for_salesperson(self):
        self.client.force_login(self.salesperson)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {'status': Delivery.STATUS_ACCOMPLISHED}
        )
        self.assertEqual(response.status_code, 403)

    def test_delivery_update_status_requires_completion_remarks(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_ACCOMPLISHED,
                'accomplished_date': '2026-10-30',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)

    def test_delivery_update_status_requires_accomplished_date(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_ACCOMPLISHED,
                'remarks': 'Completed and received by guard.',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(
            response.content,
            {'error': 'Please select the actual accomplished date.'},
        )
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)

    def test_delivery_update_status_rejects_invalid_accomplished_date(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_ACCOMPLISHED,
                'remarks': 'Completed and received by guard.',
                'accomplished_date': 'bad-date',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertJSONEqual(response.content, {'error': 'Invalid accomplished date'})
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)

    def test_delivery_update_status_requires_backlog_reason(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_FOR_SCHEDULE,
                'remarks': 'Customer unavailable at agreed schedule.',
            },
        )
        self.assertEqual(response.status_code, 400)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)

    def test_delivery_update_status_accepts_backlog_reason(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:update_status', args=[self.delivery.pk]),
            {
                'status': Delivery.STATUS_FOR_SCHEDULE,
                'remarks': 'Customer unavailable at agreed schedule.',
                'backlog_reason': str(self.backlog_reason.pk),
            },
        )
        self.assertEqual(response.status_code, 200)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_FOR_SCHEDULE)
        self.assertEqual(self.delivery.backlog_reason, self.backlog_reason)
        latest_event = self.delivery.events.first()
        self.assertEqual(latest_event.backlog_reason, self.backlog_reason.name)

    def test_delivery_update_form_requires_scheduling_remarks(self):
        self.delivery.status = Delivery.STATUS_FOR_SCHEDULE
        self.delivery.save()
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
                'backlog_reason': '',
                'status': Delivery.STATUS_SCHEDULED,
                'remarks': '',
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'Please enter scheduling remarks before moving this delivery to Scheduled.',
        )

    def test_warehouse_role_sees_quick_actions_for_scheduled(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(
            reverse('warehouse:dashboard'),
            {'date': '2026-10-30'},
        )
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
        self.assertNotContains(response, 'Backlog Categories')

    def test_warehouse_role_sees_scheduled_import_control(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:dashboard'))
        self.assertContains(response, reverse('warehouse:import_scheduled'))
        self.assertContains(response, 'Import File')

    def test_backlog_reason_list_accessible_to_warehouse(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.get(reverse('warehouse:backlog_reason_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.backlog_reason.name)

    def test_backlog_reason_list_forbidden_for_salesperson(self):
        self.client.force_login(self.salesperson)
        response = self.client.get(reverse('warehouse:backlog_reason_list'))
        self.assertEqual(response.status_code, 403)

    def test_warehouse_can_create_backlog_reason(self):
        self.client.force_login(self.warehouse_user)
        response = self.client.post(
            reverse('warehouse:backlog_reason_create'),
            {
                'name': 'Warehouse reroute required',
                'reason_group': BacklogReason.GROUP_LOGISTICS,
                'sort_order': 20,
                'is_active': 'on',
            },
        )
        self.assertRedirects(response, reverse('warehouse:backlog_reason_list'))
        self.assertTrue(
            BacklogReason.objects.filter(name='Warehouse reroute required').exists()
        )

    def test_import_scheduled_excel_updates_and_creates_deliveries(self):
        self.client.force_login(self.warehouse_user)
        self.delivery.status = Delivery.STATUS_FOR_SCHEDULE
        self.delivery.remarks = 'Waiting for file import.'
        self.delivery.vehicle_plate = ''
        self.delivery.driver_staff = ''
        self.delivery.warehouse_staff = None
        self.delivery.save()

        workbook = openpyxl.Workbook()
        worksheet = workbook.active
        worksheet.title = 'SCHEDULED DELIVERY '
        worksheet.cell(row=3, column=1, value='SCHEDULED DELIVERY : ')
        worksheet.cell(row=3, column=3, value=date(2026, 11, 4))
        headers = ['S.O.', 'CLIENT', 'ITEM', 'AREA', 'DRIVER/STAFF', 'AE', 'REMARKS']
        for index, header in enumerate(headers, start=1):
            worksheet.cell(row=4, column=index, value=header)
        worksheet.append(['S.O. 4001', 'ACME', 'Laptop', 'Quezon City', 'ROMMEL-BENJIE', 'CSV', 'DELIVER'])
        worksheet.append(['S.O. 4010', 'Globex', 'Printer', 'Makati', 'GERRY-MARLON', 'MGA', 'FOR PICK-UP'])
        worksheet.append(['VAN DETAILS'])
        worksheet.append(['NHN 4415 - ROMMEL/BENJIE'])
        worksheet.append(['NIJ 4097 - GERRY/MARLON'])

        payload = io.BytesIO()
        workbook.save(payload)
        upload = SimpleUploadedFile(
            'scheduled_delivery.xlsx',
            payload.getvalue(),
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )

        response = self.client.post(
            reverse('warehouse:import_scheduled'),
            {
                'selected_date': '2026-11-05',
                'file': upload,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('warehouse:dashboard')}?date=2026-11-04",
        )

        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)
        self.assertEqual(self.delivery.scheduled_date, date(2026, 11, 4))
        self.assertEqual(self.delivery.driver_staff, 'ROMMEL')
        self.assertEqual(self.delivery.warehouse_staff.name, 'BENJIE')
        self.assertEqual(self.delivery.vehicle_plate, 'NHN 4415')
        self.assertEqual(self.delivery.area, 'Quezon City')

        imported = Delivery.objects.get(so_number='S.O. 4010')
        self.assertEqual(imported.status, Delivery.STATUS_SCHEDULED)
        self.assertEqual(imported.scheduled_date, date(2026, 11, 4))
        self.assertEqual(imported.vehicle_plate, 'NIJ 4097')
        self.assertEqual(imported.driver_staff, 'GERRY')
        self.assertEqual(imported.warehouse_staff.name, 'MARLON')

    def test_import_scheduled_csv_uses_selected_date_and_preserves_existing_plate(self):
        self.client.force_login(self.warehouse_user)
        self.delivery.status = Delivery.STATUS_FOR_SCHEDULE
        self.delivery.vehicle_plate = 'OLD 123'
        self.delivery.save()

        csv_content = (
            'S.O.,CLIENT,ITEM,AREA,DRIVER/STAFF,AE,REMARKS\n'
            'S.O. 4001,ACME,Laptop,Pasig,GERRY-MARLON,CSV,DELIVER\n'
        )
        upload = SimpleUploadedFile(
            'scheduled_delivery.csv',
            csv_content.encode('utf-8'),
            content_type='text/csv',
        )

        response = self.client.post(
            reverse('warehouse:import_scheduled'),
            {
                'selected_date': '2026-11-06',
                'file': upload,
            },
        )

        self.assertRedirects(
            response,
            f"{reverse('warehouse:dashboard')}?date=2026-11-06",
        )
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, Delivery.STATUS_SCHEDULED)
        self.assertEqual(self.delivery.scheduled_date, date(2026, 11, 6))
        self.assertEqual(self.delivery.vehicle_plate, 'OLD 123')
        self.assertEqual(self.delivery.driver_staff, 'GERRY')
        self.assertEqual(self.delivery.warehouse_staff.name, 'MARLON')

    def test_import_scheduled_forbidden_for_salesperson(self):
        self.client.force_login(self.salesperson)
        upload = SimpleUploadedFile('scheduled_delivery.csv', b'S.O.,CLIENT,ITEM\n1,A,B\n')
        response = self.client.post(
            reverse('warehouse:import_scheduled'),
            {
                'selected_date': '2026-11-06',
                'file': upload,
            },
        )
        self.assertEqual(response.status_code, 403)

class DeliveryHistoryViewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='wh_hist', password='testpass123', role='salesperson',
            email='wh_hist@example.com',
        )
        self.staff = WarehouseStaff.objects.create(name='L. Bautista')
        self.backlog_reason, _ = BacklogReason.objects.get_or_create(
            name='AE confirmation pending',
            defaults={
                'reason_group': BacklogReason.GROUP_SALES,
                'sort_order': 20,
            },
        )
        self.completed_delivery = Delivery.objects.create(
            so_number='S.O. 5001', client='Done Corp', item='Printer',
            area='Makati', ae='CSV', status=Delivery.STATUS_ACCOMPLISHED,
            accomplished_date=date(2026, 11, 5),
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

    def test_history_filters_by_company_ae_date_and_item(self):
        self.client.force_login(self.user)
        filters = (
            {'company': 'Done C'},
            {'ae': 'CS'},
            {'date': '2026-11-05'},
            {'item': 'Print'},
        )

        for filter_params in filters:
            with self.subTest(filter_params=filter_params):
                response = self.client.get(
                    reverse('warehouse:history'), filter_params
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    list(response.context['page_obj'].object_list),
                    [self.completed_delivery],
                )
                self.assertEqual(response.context['total_count'], 1)

    def test_history_date_filter_matches_scheduled_delivery_date(self):
        scheduled_delivery = Delivery.objects.create(
            so_number='S.O. 5003',
            client='Scheduled Corp',
            item='Monitor',
            area='Pasig',
            ae='MGA',
            status=Delivery.STATUS_SCHEDULED,
            scheduled_date=date(2026, 11, 6),
        )
        self.client.force_login(self.user)

        response = self.client.get(
            reverse('warehouse:history'), {'date': '2026-11-06'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(response.context['page_obj'].object_list),
            [scheduled_delivery],
        )

    def test_history_first_page_pagination_does_not_raise_empty_page(self):
        for index in range(60):
            Delivery.objects.create(
                so_number=f'S.O. H{index:04d}',
                client=f'History Client {index}',
                item='Monitor',
                area='Pasig',
                ae='CSV',
                status=Delivery.STATUS_SCHEDULED,
                scheduled_date=date(2026, 11, 5),
            )

        self.client.force_login(self.user)
        response = self.client.get(reverse('warehouse:history'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Page 1 of')
        self.assertContains(response, '?page=1">Previous</a>', html=False)

    def test_history_pagination_preserves_active_filters(self):
        for index in range(51):
            Delivery.objects.create(
                so_number=f'S.O. F{index:04d}',
                client=f'Filter Corp {index}',
                item='Monitor',
                area='Pasig',
                ae='XYZ',
                status=Delivery.STATUS_SCHEDULED,
                scheduled_date=date(2026, 11, 5),
            )

        self.client.force_login(self.user)
        response = self.client.get(
            reverse('warehouse:history'),
            {'company': 'Filter', 'ae': 'XY'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_count'], 51)
        self.assertContains(
            response,
            '?company=Filter&amp;ae=XY&amp;page=2',
            html=False,
        )

    def test_history_forbidden_for_role_outside_monitoring_gate(self):
        outsider = User.objects.create_user(
            username='wh_hist_out', password='testpass123', role='marketing',
            email='wh_hist_out@example.com',
        )
        self.client.force_login(outsider)
        response = self.client.get(reverse('warehouse:history'))
        self.assertEqual(response.status_code, 403)

    def test_timeline_accessible_to_reader_roles(self):
        delivery = Delivery.objects.get(so_number='S.O. 5001')
        self.client.force_login(self.user)
        response = self.client.get(reverse('warehouse:timeline', args=[delivery.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Delivery Timeline')
        self.assertContains(response, delivery.so_number)

    def test_timeline_shows_status_and_remark_history(self):
        delivery = Delivery.objects.get(so_number='S.O. 5001')
        delivery.remarks = 'Delivered to warehouse.'
        delivery._event_user = self.user
        delivery.save()
        delivery.status = Delivery.STATUS_FOR_SCHEDULE
        delivery.remarks = 'Customer requested reschedule.'
        delivery.backlog_reason = self.backlog_reason
        delivery._event_user = self.user
        delivery._event_note = 'Customer requested reschedule.'
        delivery.save()

        self.client.force_login(self.user)
        response = self.client.get(reverse('warehouse:timeline', args=[delivery.pk]))
        self.assertContains(response, 'Remarks changed')
        self.assertContains(response, 'Status changed')
        self.assertContains(response, 'Customer requested reschedule.')
        self.assertContains(response, self.backlog_reason.name)

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
