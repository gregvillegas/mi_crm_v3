from django.test import TestCase
from django.urls import reverse

from users.models import User


class HomeFunnelOverviewTests(TestCase):
    def test_technical_sales_home_shows_sales_funnel_overview(self):
        technical_sales = User.objects.create_user(
            username='techsales_home',
            password='testpass123',
            role='technical_sales',
            email='techsales_home@example.com',
        )

        self.client.force_login(technical_sales)
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sales Funnel Overview')
        self.assertContains(response, '0 active')
        self.assertNotContains(response, 'Add Entry')

    def test_technical_manager_home_shows_sales_funnel_overview(self):
        technical_manager = User.objects.create_user(
            username='techmgr_home',
            password='testpass123',
            role='techmgr',
            email='techmgr_home@example.com',
        )

        self.client.force_login(technical_manager)
        response = self.client.get(reverse('home'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sales Funnel Overview')
        self.assertContains(response, '0 active')
        self.assertNotContains(response, 'Add Entry')
