"""
Phase 0 "Pipeline Intelligence" analytics — read-only.

Everything in this module is derived from data the CRM already records. There is
no new model and no migration; results are computed live, consistent with how the
rest of the CRM derives sales performance from ``SalesFunnel`` and the fiscal
helpers in ``sales_monitoring.fiscal``.

Scope model
-----------
Every public function takes ``user_ids``:
  * ``None``     -> company-wide (unrestricted)
  * ``set()``    -> see nothing
  * ``{id, ...}``-> restrict to those salespeople

Callers should pass ``crm_project.scoping.scoped_user_ids(request.user)`` so the
numbers obey exactly the same visibility rules as the rest of the CRM.

Deliberate limits (documented, not bugs)
----------------------------------------
  * Pipeline value uses ``SalesFunnel.retail`` (the quoted SRP), not the
    proposal's converted amount, because this must aggregate in SQL.
  * There is no stage-transition history in the schema, so "time in stage" is out
    of scope for Phase 0; "stalled" is measured against ``expected_close_date``.
  * ``Proposal.discount_amount`` is informational, so discounting numbers are
    directional (labelled as such in the UI).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Avg, Count, Q, Sum
from django.db.models.functions import Length
from django.utils import timezone

from sales_monitoring.models import SalesActivity
from teams.models import CompanyAnnualTarget, Team, TeamMembership
from users.models import User
from .fiscal import (
    fiscal_months,
    fiscal_window,
    fiscal_year_for_date,
    fiscal_year_label,
)

ZERO = Decimal('0.00')

# Management's coverage question was phrased as "3x to 4x" — surface both marks.
COVERAGE_TARGET_LOW = Decimal('3')
COVERAGE_TARGET_HIGH = Decimal('4')

# Same bar as the proposal approval threshold, so the stalled list lines up with
# what management already treats as high-value.
HIGH_VALUE_THRESHOLD = Decimal('500000.00')

STALE_DEAL_DAYS = 30
STALE_REP_DAYS = 30
MIN_LOST_REASON_CHARS = 10
WEAK_NOTES_CHARS = 5


# --------------------------------------------------------------------------- #
# Period helpers
# --------------------------------------------------------------------------- #
def _month_end(first_of_month: date) -> date:
    if first_of_month.month == 12:
        return first_of_month.replace(year=first_of_month.year + 1, month=1) - timedelta(days=1)
    return first_of_month.replace(month=first_of_month.month + 1) - timedelta(days=1)


def fiscal_quarters(fiscal_year: int) -> list[dict]:
    """The four fiscal quarters (Dec-Feb, Mar-May, Jun-Aug, Sep-Nov)."""
    months = fiscal_months(fiscal_year)
    quarters = []
    for index in range(4):
        chunk = months[index * 3:(index + 1) * 3]
        quarters.append({
            'index': index + 1,
            'label': f'Q{index + 1}',
            'start': chunk[0]['date'],
            'end': _month_end(chunk[-1]['date']),
        })
    return quarters


def resolve_period(fiscal_year: int, quarter: int | None) -> dict:
    """
    Resolve the reporting window (and the equal-length window before it, used for
    trend arrows). ``quarter`` is 1-4, or None for the full fiscal year.
    """
    quarters = fiscal_quarters(fiscal_year)
    start, end = fiscal_window(fiscal_year)
    label = fiscal_year_label(fiscal_year)
    quarter = int(quarter) if quarter in (1, 2, 3, 4) else None
    if quarter:
        chosen = quarters[quarter - 1]
        start, end = chosen['start'], chosen['end']
        label = f"{chosen['label']} · FY{fiscal_year}"

    length = (end - start).days + 1
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=length - 1)
    months_in_period = 3 if quarter else 12

    return {
        'fiscal_year': fiscal_year,
        'quarter': quarter,
        'quarters': quarters,
        'start': start,
        'end': end,
        'label': label,
        'months_in_period': months_in_period,
        'prev_start': prev_start,
        'prev_end': prev_end,
        'prev_label': f"{prev_start.strftime('%b %d, %Y')} – {prev_end.strftime('%b %d, %Y')}",
    }


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def _scoped(queryset, user_ids, field: str = 'salesperson_id'):
    """Narrow a queryset to ``user_ids``. None = unrestricted, empty = nothing."""
    if user_ids is None:
        return queryset
    if not user_ids:
        return queryset.none()
    return queryset.filter(**{f'{field}__in': list(user_ids)})


def _pct(numerator, denominator) -> float:
    if not denominator:
        return 0.0
    return float(numerator) / float(denominator) * 100


def _ratio(numerator, denominator):
    """Coverage multiple, or None when there is no target to divide by."""
    if not denominator:
        return None
    return float(numerator) / float(denominator)


def _ratio_display(value) -> str:
    return '—' if value is None else f'{value:.1f}×'


def _days_display(value) -> str:
    return '—' if value is None else f'{value:.1f} days'


def _money_display(value) -> str:
    return '—' if value is None else f'₱{value:,.2f}'


def _open_pipeline(user_ids):
    from sales_funnel.models import SalesFunnel
    qs = SalesFunnel.objects.filter(is_active=True, is_test=False, deal_outcome='active')
    qs = _scoped(qs, user_ids)
    agg = qs.aggregate(total=Sum('retail'), count=Count('id'))
    return agg['total'] or ZERO, agg['count'] or 0


# --------------------------------------------------------------------------- #
# 1. Coverage
# --------------------------------------------------------------------------- #
def company_targets(fiscal_year: int, period: dict) -> dict:
    """Annual + period target. Falls back to summed rep quotas when no target set."""
    annual = CompanyAnnualTarget.objects.filter(year=fiscal_year).first()
    annual_amount = annual.amount if annual else ZERO
    source = 'Company annual target'
    if not annual_amount:
        rep_monthly = (
            TeamMembership.objects
            .filter(user__role='salesperson', user__is_active=True)
            .aggregate(s=Sum('quota'))['s']
        ) or ZERO
        annual_amount = rep_monthly * 12
        source = 'Derived from assigned rep quotas'

    period_target = annual_amount / 4 if period['quarter'] else annual_amount
    return {
        'annual': annual_amount,
        'period_target': period_target,
        'quarterly': annual_amount / 4,
        'source': source,
        'has_explicit_annual': bool(annual and annual.amount),
    }


def coverage_section(user_ids, fiscal_year: int, period: dict) -> dict:
    pipeline_total, pipeline_count = _open_pipeline(user_ids)
    targets = company_targets(fiscal_year, period)
    months = period['months_in_period']

    teams = []
    for team in Team.objects.order_by('name'):
        memberships = TeamMembership.objects.filter(group__team=team)
        if user_ids is not None:
            memberships = memberships.filter(user_id__in=list(user_ids))
        member_ids = list(memberships.values_list('user_id', flat=True))
        if not member_ids:
            continue

        team_pipeline = (
            _open_pipeline(set(member_ids))
        )
        team_quota = memberships.aggregate(s=Sum('quota'))['s'] or ZERO
        team_target = team_quota * months
        teams.append({
            'name': team.name,
            'pipeline': team_pipeline[0],
            'deal_count': team_pipeline[1],
            'target': team_target,
            'coverage': _ratio(team_pipeline[0], team_target),
            'coverage_display': _ratio_display(_ratio(team_pipeline[0], team_target)),
            'coverage_severity': _coverage_severity(_ratio(team_pipeline[0], team_target)),
        })
    teams.sort(key=lambda t: (t['coverage'] is None, -(t['coverage'] or 0)))

    coverage = _ratio(pipeline_total, targets['period_target'])
    coverage_annual = _ratio(pipeline_total, targets['annual'])
    return {
        'pipeline': pipeline_total,
        'deal_count': pipeline_count,
        'targets': targets,
        'coverage': coverage,
        'coverage_display': _ratio_display(coverage),
        'coverage_severity': _coverage_severity(coverage),
        'coverage_annual': coverage_annual,
        'coverage_annual_display': _ratio_display(coverage_annual),
        'coverage_annual_severity': _coverage_severity(coverage_annual),
        'target_low': COVERAGE_TARGET_LOW,
        'target_high': COVERAGE_TARGET_HIGH,
        'teams': teams,
    }


def _coverage_severity(value) -> str:
    """Badge colour for a coverage multiple against management's 3x–4x rule."""
    if value is None:
        return 'secondary'
    if value >= COVERAGE_TARGET_LOW:
        return 'success'
    if value >= Decimal('1'):
        return 'warning'
    return 'danger'


# --------------------------------------------------------------------------- #
# 2. Stalled deals
# --------------------------------------------------------------------------- #
def stalled_queryset(user_ids, today: date, min_value=None):
    from sales_funnel.models import SalesFunnel
    qs = (
        SalesFunnel.objects
        .filter(
            is_active=True,
            is_test=False,
            deal_outcome='active',
            expected_close_date__lt=today,
        )
        .select_related('salesperson', 'customer')
        .order_by('-retail')
    )
    qs = _scoped(qs, user_ids)
    if min_value:
        qs = qs.filter(retail__gte=min_value)
    return qs


def stalled_rows(queryset, today: date, limit=None) -> list[dict]:
    rows = []
    for entry in (queryset[:limit] if limit else queryset):
        rows.append({
            'id': entry.pk,
            'company': entry.company_name,
            'stage': entry.get_stage_display(),
            'salesperson': entry.salesperson.get_full_name() or entry.salesperson.username,
            'value': entry.retail,
            'expected_close_date': entry.expected_close_date,
            'days_overdue': (today - entry.expected_close_date).days,
            'probability': entry.probability,
            'high_value': entry.retail >= HIGH_VALUE_THRESHOLD,
        })
    return rows


# --------------------------------------------------------------------------- #
# 3. Top vs bottom performers
# --------------------------------------------------------------------------- #
def performer_section(user_ids, period: dict, limit: int = 5) -> dict:
    from sales_funnel.models import SalesFunnel
    start, end = period['start'], period['end']

    closed = SalesFunnel.objects.filter(
        is_closed=True, is_test=False,
        closed_date__gte=start, closed_date__lte=end,
    )
    closed = _scoped(closed, user_ids)

    won_by = {
        r['salesperson_id']: r
        for r in closed.filter(deal_outcome='won')
        .values('salesperson_id')
        .annotate(revenue=Sum('retail'), deals=Count('id'))
    }
    lost_by = {
        r['salesperson_id']: r['deals']
        for r in closed.filter(deal_outcome='lost')
        .values('salesperson_id')
        .annotate(deals=Count('id'))
    }

    activities = SalesActivity.objects.filter(
        created_at__date__gte=start, created_at__date__lte=end,
    )
    activities = _scoped(activities, user_ids)
    act_by = {
        r['salesperson_id']: r['n']
        for r in activities.values('salesperson_id').annotate(n=Count('id'))
    }

    ids = set(won_by) | set(lost_by) | set(act_by)
    people = {u.id: u for u in User.objects.filter(id__in=ids)}
    people = {uid: u for uid, u in people.items() if u.role == 'salesperson'}

    rows = []
    for uid, user in people.items():
        won = won_by.get(uid, {})
        won_count = won.get('deals', 0)
        lost_count = lost_by.get(uid, 0)
        total_closed = won_count + lost_count
        rows.append({
            'name': user.get_full_name() or user.username,
            'revenue': won.get('revenue') or ZERO,
            'won_count': won_count,
            'lost_count': lost_count,
            'win_rate': round(_pct(won_count, total_closed), 1),
            'activities': act_by.get(uid, 0),
        })
    rows.sort(key=lambda r: r['revenue'], reverse=True)

    total_revenue = sum((r['revenue'] for r in rows), ZERO)
    cumulative = ZERO
    pareto_count = 0
    for row in rows:
        cumulative += row['revenue']
        pareto_count += 1
        if total_revenue and cumulative >= total_revenue * Decimal('0.8'):
            break

    return {
        'rows': rows,
        'top': rows[:limit],
        'bottom': rows[-limit:][::-1] if len(rows) > limit else [],
        'total_revenue': total_revenue,
        'reps_with_revenue': sum(1 for r in rows if r['revenue'] > 0),
        'pareto_count': pareto_count if total_revenue else 0,
        'pareto_pct': round(_pct(pareto_count, len(rows)), 1) if rows and total_revenue else 0.0,
    }


# --------------------------------------------------------------------------- #
# 4. Lead quality (MQL/SQL proxy)
# --------------------------------------------------------------------------- #
def lead_quality_section(user_ids, period: dict) -> dict:
    from lead_generation.models import ConversionTracking, Lead
    start, end = period['start'], period['end']

    leads = Lead.objects.filter(created_at__date__gte=start, created_at__date__lte=end)
    leads = _scoped(leads, user_ids, field='assigned_to_id')

    per_source = []
    for row in (
        leads.values('source__name', 'source__cost_per_lead')
        .annotate(
            total=Count('id'),
            converted=Count('id', filter=Q(status='converted')),
            qualified=Count('id', filter=Q(status='qualified')),
            lost=Count('id', filter=Q(status='lost')),
        )
        .order_by('-total')
    ):
        total = row['total'] or 0
        converted = row['converted'] or 0
        cost_per_lead = row['source__cost_per_lead'] or ZERO
        cost_per_conversion = (cost_per_lead * total / converted) if converted else None
        per_source.append({
            'name': row['source__name'] or '—',
            'total': total,
            'converted': converted,
            'qualified': row['qualified'] or 0,
            'lost': row['lost'] or 0,
            'conversion_rate': round(_pct(converted, total), 1),
            'cost_per_lead': cost_per_lead,
            'total_cost': cost_per_lead * total,
            'cost_per_conversion': cost_per_conversion,
            'cost_per_conversion_display': _money_display(cost_per_conversion),
        })

    overall = leads.aggregate(
        total=Count('id'),
        converted=Count('id', filter=Q(status='converted')),
        qualified=Count('id', filter=Q(status='qualified')),
        lost=Count('id', filter=Q(status='lost')),
        unqualified=Count('id', filter=Q(status='unqualified')),
    )

    conversions = ConversionTracking.objects.filter(
        conversion_date__date__gte=start, conversion_date__date__lte=end,
    )
    conversions = _scoped(conversions, user_ids, field='converted_by_id')
    conv = conversions.aggregate(
        n=Count('id'),
        avg_days=Avg('days_to_convert'),
        acquisition_cost=Sum('acquisition_cost'),
        value=Sum('conversion_value'),
    )

    total = overall['total'] or 0
    return {
        'per_source': per_source,
        'total': total,
        'converted': overall['converted'] or 0,
        'qualified': overall['qualified'] or 0,
        'lost': overall['lost'] or 0,
        'unqualified': overall['unqualified'] or 0,
        'conversion_rate': round(_pct(overall['converted'] or 0, total), 1),
        'qualified_rate': round(_pct(overall['qualified'] or 0, total), 1),
        'conversions': conv['n'] or 0,
        'avg_days_to_convert': round(conv['avg_days'], 1) if conv['avg_days'] is not None else None,
        'acquisition_cost': conv['acquisition_cost'] or ZERO,
        'conversion_value': conv['value'] or ZERO,
    }


# --------------------------------------------------------------------------- #
# 5. CRM hygiene scorecard
# --------------------------------------------------------------------------- #
def hygiene_section(user_ids, period: dict, today: date) -> dict:
    from sales_funnel.models import SalesFunnel
    start, end = period['start'], period['end']
    stale_before = today - timedelta(days=STALE_DEAL_DAYS)

    active = _scoped(
        SalesFunnel.objects.filter(is_active=True, is_test=False, deal_outcome='active'),
        user_ids,
    )
    total_active = active.count()
    missing_close = active.filter(expected_close_date__isnull=True).count()
    stale_deals = active.filter(updated_at__date__lt=stale_before).count()

    lost = _scoped(
        SalesFunnel.objects.filter(
            is_closed=True, is_test=False, deal_outcome='lost',
            closed_date__gte=start, closed_date__lte=end,
        ),
        user_ids,
    )
    total_lost = lost.count()
    weak_reason = lost.annotate(rl=Length('lost_reason')).filter(rl__lt=MIN_LOST_REASON_CHARS).count()

    completed = _scoped(
        SalesActivity.objects.filter(
            status='completed',
            created_at__date__gte=start, created_at__date__lte=end,
        ),
        user_ids,
    )
    total_completed = completed.count()
    no_notes = completed.annotate(nl=Length('notes')).filter(nl__lt=WEAK_NOTES_CHARS).count()

    reps = User.objects.filter(role='salesperson', is_active=True)
    if user_ids is not None:
        reps = reps.filter(id__in=list(user_ids))
    total_reps = reps.count()
    recent_ids = set(
        SalesActivity.objects
        .filter(created_at__date__gte=today - timedelta(days=STALE_REP_DAYS))
        .values_list('salesperson_id', flat=True)
    )
    idle_reps = sum(1 for rid in reps.values_list('id', flat=True) if rid not in recent_ids)

    def check(key, label, count, total, hint, count_only=False):
        return {
            'key': key,
            'label': label,
            'count': count,
            'total': total,
            'pct': round(_pct(count, total), 1),
            'hint': hint,
            'count_only': count_only,
            'severity': _severity(count, total, count_only),
        }

    checks = [
        check('missing_close', 'Active deals with no expected close date', missing_close, total_active,
              'Deals without a close date cannot be forecast or flagged as stalled.'),
        check('stale_deals', f'Active deals untouched for {STALE_DEAL_DAYS}+ days', stale_deals, total_active,
              'No edits in a month usually means the deal is drifting.'),
        check('weak_reason', 'Lost deals with no meaningful reason', weak_reason, total_lost,
              'Reasons under %d characters cannot be trended.' % MIN_LOST_REASON_CHARS),
        check('no_notes', 'Completed activities with no notes', no_notes, total_completed,
              'Activities without outcomes give no coaching signal.'),
        check('idle_reps', f'Salespeople with no activity in {STALE_REP_DAYS} days', idle_reps, total_reps,
              'Reps with no logged activity in a month.', count_only=True),
    ]
    return {'checks': checks}


def _severity(count, total, count_only=False) -> str:
    if count_only:
        if count == 0:
            return 'success'
        if total and count / total >= 0.34:
            return 'danger'
        return 'warning'
    if not total or count == 0:
        return 'success'
    pct = count / total
    if pct >= 0.25:
        return 'danger'
    if pct >= 0.10:
        return 'warning'
    return 'success'


# --------------------------------------------------------------------------- #
# 6. Sales velocity
# --------------------------------------------------------------------------- #
def _avg_funnel_cycle_days(user_ids, start: date, end: date):
    """Average (closed_date - date_created) in days for won deals in a window.

    Computed in Python rather than SQL: date subtraction is not portable between
    SQLite (dev) and MariaDB (prod). The row set is bounded by the period.
    """
    from sales_funnel.models import SalesFunnel
    qs = SalesFunnel.objects.filter(
        is_test=False, deal_outcome='won', is_closed=True,
        closed_date__gte=start, closed_date__lte=end,
    )
    qs = _scoped(qs, user_ids)
    total_days = 0
    count = 0
    for created, closed in qs.values_list('date_created', 'closed_date').iterator():
        if created and closed:
            total_days += (closed - created).days
            count += 1
    return (total_days / count) if count else None, count


def velocity_section(user_ids, period: dict) -> dict:
    from lead_generation.models import ConversionTracking

    start, end = period['start'], period['end']
    cycle_now, cycle_count = _avg_funnel_cycle_days(user_ids, start, end)
    cycle_prev, _ = _avg_funnel_cycle_days(user_ids, period['prev_start'], period['prev_end'])

    conversions = ConversionTracking.objects.filter(
        conversion_date__date__gte=start, conversion_date__date__lte=end,
    )
    conversions = _scoped(conversions, user_ids, field='converted_by_id')
    lead_avg = conversions.aggregate(avg=Avg('days_to_convert'), n=Count('id'))

    conversions_prev = ConversionTracking.objects.filter(
        conversion_date__date__gte=period['prev_start'],
        conversion_date__date__lte=period['prev_end'],
    )
    conversions_prev = _scoped(conversions_prev, user_ids, field='converted_by_id')
    lead_prev = conversions_prev.aggregate(avg=Avg('days_to_convert'))['avg']

    def delta(now, prev):
        if now is None or prev is None:
            return None
        return round(now - prev, 1)

    return {
        'funnel_cycle_days': round(cycle_now, 1) if cycle_now is not None else None,
        'funnel_cycle_prev': round(cycle_prev, 1) if cycle_prev is not None else None,
        'funnel_cycle_delta': delta(cycle_now, cycle_prev),
        'funnel_cycle_count': cycle_count,
        'lead_convert_days': round(lead_avg['avg'], 1) if lead_avg['avg'] is not None else None,
        'lead_convert_prev': round(lead_prev, 1) if lead_prev is not None else None,
        'lead_convert_delta': delta(lead_avg['avg'], lead_prev),
        'lead_convert_count': lead_avg['n'] or 0,
    }


# --------------------------------------------------------------------------- #
# 7. Discounting & margin
# --------------------------------------------------------------------------- #
def discounting_section(user_ids, period: dict) -> dict:
    from sales_proposals.models import Proposal
    start, end = period['start'], period['end']

    proposals = Proposal.objects.filter(is_test=False, date__gte=start, date__lte=end)
    proposals = _scoped(proposals, user_ids, field='created_by_id')

    rows = []
    grouped = (
        proposals.values('created_by_id')
        .annotate(
            count=Count('id'),
            amount=Sum('total_amount'),
            discount=Sum('discount_amount'),
            profit=Sum('gross_profit'),
            margin=Avg('sales_margin_pct'),
        )
        .order_by('-amount')
    )
    user_ids_in_rows = [r['created_by_id'] for r in grouped]
    people = {u.id: u for u in User.objects.filter(id__in=user_ids_in_rows)}
    for row in grouped:
        amount = row['amount'] or ZERO
        discount = row['discount'] or ZERO
        profit = row['profit'] or ZERO
        user = people.get(row['created_by_id'])
        rows.append({
            'name': (user.get_full_name() or user.username) if user else '—',
            'count': row['count'],
            'amount': amount,
            'discount': discount,
            'discount_pct': round(_pct(discount, amount), 2),
            'profit': profit,
            'margin_pct': round(float(row['margin']), 1) if row['margin'] is not None else None,
            'effective_margin_pct': round(_pct(profit, amount), 1),
        })

    overall = proposals.aggregate(
        count=Count('id'),
        amount=Sum('total_amount'),
        discount=Sum('discount_amount'),
        profit=Sum('gross_profit'),
        margin=Avg('sales_margin_pct'),
    )
    amount = overall['amount'] or ZERO
    discount = overall['discount'] or ZERO
    profit = overall['profit'] or ZERO

    return {
        'rows': rows,
        'count': overall['count'] or 0,
        'amount': amount,
        'discount': discount,
        'discount_pct': round(_pct(discount, amount), 2),
        'profit': profit,
        'margin_pct': round(float(overall['margin']), 1) if overall['margin'] is not None else None,
        'effective_margin_pct': round(_pct(profit, amount), 1),
    }


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def build_pipeline_intelligence(user, fiscal_year=None, quarter=None) -> dict:
    """Assemble the full Phase 0 context for the Pipeline Intelligence page."""
    from crm_project.scoping import scoped_user_ids

    today = timezone.now().date()
    if not fiscal_year:
        fiscal_year = fiscal_year_for_date(today)
    period = resolve_period(fiscal_year, quarter)
    user_ids = scoped_user_ids(user)

    if user_ids is None:
        scope_label = 'Company-wide'
    else:
        scope_label = f'{len(user_ids)} salespeople in scope'

    stalled_qs = stalled_queryset(user_ids, today)
    return {
        'period': period,
        'today': today,
        'scope_label': scope_label,
        'coverage': coverage_section(user_ids, fiscal_year, period),
        'stalled': {
            'rows': stalled_rows(stalled_qs, today, limit=25),
            'total': stalled_qs.count(),
            'preview_limit': 25,
        },
        'performers': performer_section(user_ids, period),
        'lead_quality': lead_quality_section(user_ids, period),
        'hygiene': hygiene_section(user_ids, period, today),
        'velocity': velocity_section(user_ids, period),
        'discounting': discounting_section(user_ids, period),
    }
