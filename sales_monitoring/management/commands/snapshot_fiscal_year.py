"""
Freeze a fiscal year's performance into permanent FiscalYearSummary rows.

Run once shortly after the fiscal year ends (the company FY runs Dec 1 -> Nov 30,
so run in early December). This copies the final live numbers from SalesFunnel
into immutable per-scope rows (company / team / group / salesperson) so the year
stays stable for year-over-year comparison even if underlying deals later change.

Usage:
    python manage.py snapshot_fiscal_year 2026
    python manage.py snapshot_fiscal_year 2026 --force      # overwrite existing
    python manage.py snapshot_fiscal_year 2026 --dry-run    # show, write nothing

See docs/FISCAL_YEAR_WORKFLOW.md.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from sales_monitoring.fiscal import (
    compute_scope_performance,
    fiscal_window,
    fiscal_year_label,
)
from sales_monitoring.models import FiscalYearSummary, FiscalYearSnapshotLog


class Command(BaseCommand):
    help = "Snapshot a fiscal year's performance into FiscalYearSummary rows."

    def add_arguments(self, parser):
        parser.add_argument('fiscal_year', type=int, help='Fiscal year to snapshot, e.g. 2026')
        parser.add_argument('--force', action='store_true',
                            help='Overwrite an existing snapshot for this fiscal year.')
        parser.add_argument('--dry-run', action='store_true',
                            help='Compute and print totals without writing anything.')

    def handle(self, *args, **options):
        from teams.models import Team, Group, TeamMembership
        from users.models import User

        fy = options['fiscal_year']
        force = options['force']
        dry_run = options['dry_run']
        start, end = fiscal_window(fy)

        existing = FiscalYearSummary.objects.filter(fiscal_year=fy)
        if existing.exists() and not force and not dry_run:
            raise CommandError(
                f"A snapshot for FY{fy} already exists ({existing.count()} rows). "
                f"Re-run with --force to regenerate (this is audited)."
            )

        self.stdout.write(self.style.MIGRATE_HEADING(fiscal_year_label(fy)))
        self.stdout.write(f"Window: {start} -> {end}\n")

        rows = []  # (scope_type, scope_id, scope_name, ScopePerformance, quota or None)

        # --- Salespeople (quota = annualized monthly quota * 12) ---
        salespeople = User.objects.filter(role='salesperson', is_active=True)
        for sp in salespeople:
            perf = compute_scope_performance(fy, salesperson_ids=[sp.id])
            try:
                quota = TeamMembership.objects.get(user=sp).quota * 12
            except TeamMembership.DoesNotExist:
                quota = None
            rows.append((
                FiscalYearSummary.SCOPE_SALESPERSON, sp.id,
                sp.get_full_name() or sp.username, perf, quota,
            ))

        # --- Groups ---
        for group in Group.objects.select_related('team').all():
            member_ids = list(
                TeamMembership.objects.filter(group=group).values_list('user_id', flat=True)
            )
            perf = compute_scope_performance(fy, salesperson_ids=member_ids)
            # Sum members' annualized quotas (monthly quota * 12).
            from django.db.models import Sum as _Sum
            group_quota = TeamMembership.objects.filter(group=group).aggregate(
                v=_Sum('quota'))['v']
            group_quota = (group_quota * 12) if group_quota else None
            rows.append((
                FiscalYearSummary.SCOPE_GROUP, group.id, group.name, perf, group_quota,
            ))

        # --- Teams ---
        for team in Team.objects.all():
            member_ids = list(
                TeamMembership.objects.filter(group__team=team).values_list('user_id', flat=True)
            )
            perf = compute_scope_performance(fy, salesperson_ids=member_ids)
            from django.db.models import Sum as _Sum
            team_quota = TeamMembership.objects.filter(group__team=team).aggregate(
                v=_Sum('quota'))['v']
            team_quota = (team_quota * 12) if team_quota else None
            rows.append((
                FiscalYearSummary.SCOPE_TEAM, team.id, team.name, perf, team_quota,
            ))

        # --- Company (all salespeople) ---
        company_perf = compute_scope_performance(fy, salesperson_ids=None)
        company_quota = None
        try:
            from teams.models import CompanyAnnualTarget
            # CompanyAnnualTarget.year is the fiscal year (same convention as this
            # snapshot), so an exact match is correct.
            cat = CompanyAnnualTarget.objects.filter(year=fy).first()
            if cat:
                company_quota = cat.amount
        except Exception:
            company_quota = None
        rows.append((
            FiscalYearSummary.SCOPE_COMPANY, 0, 'Company', company_perf, company_quota,
        ))

        # Report
        for scope_type, scope_id, name, perf, quota in rows:
            if scope_type == FiscalYearSummary.SCOPE_COMPANY or perf.total_closed > 0:
                self.stdout.write(
                    f"  [{scope_type:11}] {name[:32]:32} "
                    f"won={perf.won_count:3} lost={perf.lost_count:3} "
                    f"profit=P{perf.total_profit:,.0f}"
                )

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run — nothing written."))
            return

        with transaction.atomic():
            if existing.exists():
                existing.delete()
                action = 'regenerated'
            else:
                action = 'created'

            objs = []
            for scope_type, scope_id, name, perf, quota in rows:
                objs.append(FiscalYearSummary(
                    fiscal_year=fy,
                    scope_type=scope_type,
                    scope_id=scope_id,
                    scope_name=name,
                    won_count=perf.won_count,
                    lost_count=perf.lost_count,
                    win_rate=Decimal(str(round(perf.win_rate, 2))),
                    total_revenue=perf.total_revenue,
                    total_profit=perf.total_profit,
                    avg_deal_size=perf.avg_deal_size,
                    monthly_profit=[str(v) for v in perf.monthly_profit],
                    quota=quota,
                ))
            FiscalYearSummary.objects.bulk_create(objs)

            FiscalYearSnapshotLog.objects.create(
                fiscal_year=fy,
                action=action,
                scope_rows=len(objs),
                notes=f"{action} via management command",
            )

        self.stdout.write(self.style.SUCCESS(
            f"\nFY{fy} snapshot {action}: {len(objs)} rows written."
        ))
