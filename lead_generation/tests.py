from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import LeadSource


User = get_user_model()


class LeadSourceCostEditingTests(TestCase):
    def setUp(self):
        self.source = LeadSource.objects.create(
            name='Website',
            source_type='website',
            cost_per_lead=Decimal('25.00'),
        )
        self.marketing = User.objects.create_user(
            username='marketing_user',
            password='testpass123',
            role='marketing',
        )
        self.admin = User.objects.create_user(
            username='admin_user',
            password='testpass123',
            role='admin',
        )
        self.salesperson = User.objects.create_user(
            username='sales_user',
            password='testpass123',
            role='salesperson',
        )

    def test_marketing_can_edit_cost_inline(self):
        self.client.force_login(self.marketing)

        response = self.client.post(
            reverse(
                'lead_generation:lead_source_update_cost',
                args=[self.source.pk],
            ),
            {'cost_per_lead': '125.50'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['display'], '₱125.50')
        self.source.refresh_from_db()
        self.assertEqual(self.source.cost_per_lead, Decimal('125.50'))

    def test_admin_can_edit_cost_inline(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            reverse(
                'lead_generation:lead_source_update_cost',
                args=[self.source.pk],
            ),
            {'cost_per_lead': '0'},
        )

        self.assertEqual(response.status_code, 200)
        self.source.refresh_from_db()
        self.assertEqual(self.source.cost_per_lead, Decimal('0.00'))

    def test_other_roles_cannot_edit_cost(self):
        self.client.force_login(self.salesperson)

        response = self.client.post(
            reverse(
                'lead_generation:lead_source_update_cost',
                args=[self.source.pk],
            ),
            {'cost_per_lead': '125.50'},
        )

        self.assertEqual(response.status_code, 403)
        self.source.refresh_from_db()
        self.assertEqual(self.source.cost_per_lead, Decimal('25.00'))

    def test_invalid_cost_is_rejected(self):
        self.client.force_login(self.marketing)

        response = self.client.post(
            reverse(
                'lead_generation:lead_source_update_cost',
                args=[self.source.pk],
            ),
            {'cost_per_lead': '-1'},
        )

        self.assertEqual(response.status_code, 400)
        self.source.refresh_from_db()
        self.assertEqual(self.source.cost_per_lead, Decimal('25.00'))

    def test_marketing_can_edit_source_details(self):
        self.client.force_login(self.marketing)

        response = self.client.post(
            reverse(
                'lead_generation:lead_source_edit',
                args=[self.source.pk],
            ),
            {
                'name': 'Updated Website',
                'source_type': 'website',
                'description': 'Updated source details',
                'cost_per_lead': '30.00',
                'is_active': 'on',
            },
        )

        self.assertRedirects(response, reverse('lead_generation:lead_sources'))
        self.source.refresh_from_db()
        self.assertEqual(self.source.name, 'Updated Website')
        self.assertEqual(self.source.description, 'Updated source details')

    def test_other_roles_cannot_edit_source_details(self):
        self.client.force_login(self.salesperson)

        response = self.client.get(
            reverse(
                'lead_generation:lead_source_edit',
                args=[self.source.pk],
            )
        )

        self.assertEqual(response.status_code, 403)

    def test_source_list_only_offers_inline_editing_to_managers(self):
        url = reverse('lead_generation:lead_sources')

        self.client.force_login(self.marketing)
        marketing_response = self.client.get(url)
        self.assertContains(marketing_response, 'Double-click to edit cost per lead')
        self.assertContains(marketing_response, 'lead-source-cost-edit')
        self.assertContains(marketing_response, 'Edit source details')

        self.client.force_login(self.salesperson)
        salesperson_response = self.client.get(url)
        self.assertNotContains(salesperson_response, 'lead-source-cost-edit')
        self.assertContains(salesperson_response, '₱25.00')

    def test_import_actions_render_as_a_compact_group(self):
        self.client.force_login(self.marketing)

        response = self.client.get(reverse('lead_generation:lead_import'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'lead-import-actions')
        self.assertContains(response, 'Import Leads')
