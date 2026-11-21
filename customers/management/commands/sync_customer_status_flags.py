from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db.models import Max, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from customers.models import Customer, CustomerHistory
from sales_funnel.models import SalesFunnel
from sales_monitoring.models import SalesActivity
from sales_proposals.models import ProposalEmailLog


class Command(BaseCommand):
    help = (
        "Synchronize system-managed customer flags: last activity, auto inactive flag, "
        "lifetime won revenue, and millionaire account status."
    )

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Preview changes without saving.')
        parser.add_argument('--customer-id', type=int, help='Sync only one customer by ID.')

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        customer_id = options.get('customer_id')
        now = timezone.now()
        inactivity_cutoff = now - timedelta(days=90)
        inactivity_cutoff_date = timezone.localdate(inactivity_cutoff)
        millionaire_threshold = Decimal('1000000.00')

        customers = Customer.objects.select_related('salesperson').all()
        if customer_id:
            customers = customers.filter(id=customer_id)

        customer_ids = list(customers.values_list('id', flat=True))
        if not customer_ids:
            self.stdout.write(self.style.WARNING('No customers matched the sync criteria.'))
            return

        activity_map = {
            row['customer_id']: row['last_activity_at']
            for row in SalesActivity.objects.filter(customer_id__in=customer_ids)
            .filter(status='completed')
            .values('customer_id')
            .annotate(last_activity_at=Max(Coalesce('actual_end', 'created_at')))
        }
        proposal_sent_map = {
            row['proposal__customer_id']: row['last_sent_at']
            for row in ProposalEmailLog.objects.filter(
                proposal__customer_id__in=customer_ids,
                status='sent',
            )
            .values('proposal__customer_id')
            .annotate(last_sent_at=Max('sent_at'))
        }
        closed_deal_map = {
            row['customer_id']: row['last_closed_date']
            for row in SalesFunnel.objects.filter(
                customer_id__in=customer_ids,
                is_test=False,
                deal_outcome__in=['won', 'lost'],
                closed_date__isnull=False,
            )
            .values('customer_id')
            .annotate(last_closed_date=Max('closed_date'))
        }
        won_revenue_map = {
            row['customer_id']: row['total_revenue'] or Decimal('0.00')
            for row in SalesFunnel.objects.filter(
                customer_id__in=customer_ids,
                deal_outcome='won',
            )
            .values('customer_id')
            .annotate(total_revenue=Sum('retail'))
        }

        synced = 0
        changed = 0

        for customer in customers:
            synced += 1
            last_activity_at = activity_map.get(customer.id)
            last_proposal_sent_at = proposal_sent_map.get(customer.id)
            last_closed_date = closed_deal_map.get(customer.id)
            engagement_dates = [
                timezone.localdate(value)
                for value in (last_activity_at, last_proposal_sent_at)
                if value is not None
            ]
            if last_closed_date:
                engagement_dates.append(last_closed_date)
            reference_date = (
                max(engagement_dates)
                if engagement_dates
                else timezone.localdate(customer.created_at)
            )
            auto_inactive_flag = reference_date <= inactivity_cutoff_date
            lifetime_won_revenue = won_revenue_map.get(customer.id, Decimal('0.00'))
            is_millionaire_account = lifetime_won_revenue > millionaire_threshold

            update_fields = []
            if customer.last_sales_activity_at != last_activity_at:
                customer.last_sales_activity_at = last_activity_at
                update_fields.append('last_sales_activity_at')
            if customer.lifetime_won_revenue != lifetime_won_revenue:
                customer.lifetime_won_revenue = lifetime_won_revenue
                update_fields.append('lifetime_won_revenue')

            auto_inactive_changed = customer.auto_inactive_flag != auto_inactive_flag
            millionaire_changed = customer.is_millionaire_account != is_millionaire_account

            if auto_inactive_changed:
                old_value = customer.auto_inactive_flag
                customer.auto_inactive_flag = auto_inactive_flag
                update_fields.append('auto_inactive_flag')
            else:
                old_value = customer.auto_inactive_flag

            if millionaire_changed:
                old_millionaire = customer.is_millionaire_account
                customer.is_millionaire_account = is_millionaire_account
                update_fields.append('is_millionaire_account')
            else:
                old_millionaire = customer.is_millionaire_account

            if update_fields:
                customer.status_last_synced_at = now
                update_fields.append('status_last_synced_at')
                changed += 1

                if dry_run:
                    self.stdout.write(
                        f"[DRY RUN] Customer {customer.id} {customer.company_name}: "
                        f"auto_inactive={customer.auto_inactive_flag}, "
                        f"millionaire={customer.is_millionaire_account}, "
                        f"won_revenue={customer.lifetime_won_revenue}, "
                        f"last_engagement={reference_date}, "
                        f"last_activity={customer.last_sales_activity_at or 'None'}"
                    )
                else:
                    customer.save(update_fields=update_fields)

                    if auto_inactive_changed:
                        CustomerHistory.objects.create(
                            customer=customer,
                            action='field_updated',
                            description=(
                                f"System sync updated auto inactive flag to "
                                f"{'Inactive' if auto_inactive_flag else 'Active'} "
                                f"using latest qualifying engagement date {reference_date}."
                            ),
                            changed_by=None,
                            salesperson_at_time=customer.salesperson,
                            old_value={'auto_inactive_flag': old_value},
                            new_value={'auto_inactive_flag': auto_inactive_flag},
                            user_agent='system/sync_customer_status_flags',
                        )

                    if millionaire_changed:
                        CustomerHistory.objects.create(
                            customer=customer,
                            action='field_updated',
                            description=(
                                f"System sync updated millionaire account flag to "
                                f"{'enabled' if is_millionaire_account else 'disabled'} "
                                f"based on cumulative won revenue of P{lifetime_won_revenue:,.2f}."
                            ),
                            changed_by=None,
                            salesperson_at_time=customer.salesperson,
                            old_value={'is_millionaire_account': old_millionaire},
                            new_value={'is_millionaire_account': is_millionaire_account},
                            user_agent='system/sync_customer_status_flags',
                        )

        summary = f"Processed {synced} customers; {'would update' if dry_run else 'updated'} {changed}."
        self.stdout.write(self.style.SUCCESS(summary))
