"""
Fiscal-year helpers for performance summaries and year-over-year comparison.

The company fiscal year runs December 1 -> November 30 and is named by the year
it ENDS in:  FY2026 = Dec 1 2025 -> Nov 30 2026,  FY2027 = Dec 1 2026 -> Nov 30 2027.

This module is the single source of truth for:
  * resolving a fiscal-year window (fiscal_window / fiscal_year_for_date),
  * computing live won/lost performance for a scope over a window
    (compute_scope_performance),
  * labels used across the snapshot command and the comparison view.

All revenue/profit here is computed LIVE from SalesFunnel. The FiscalYearSummary
model (see models.py) is what freezes these numbers at year-end so a closed
fiscal year stays stable for comparison even if underlying rows later change.
See docs/FISCAL_YEAR_WORKFLOW.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db.models import Sum, F, Q


FISCAL_START_MONTH = 12  # December


def fiscal_year_for_date(d: date) -> int:
    """The fiscal year (named by its END year) that a given date falls in."""
    return d.year + 1 if d.month == FISCAL_START_MONTH else d.year


def fiscal_window(fiscal_year: int) -> tuple[date, date]:
    """(start, end) dates for a fiscal year. FY2026 -> (2025-12-01, 2026-11-30)."""
    start = date(fiscal_year - 1, FISCAL_START_MONTH, 1)
    end = date(fiscal_year, FISCAL_START_MONTH - 1, 30)  # Nov 30
    return start, end


def fiscal_year_label(fiscal_year: int) -> str:
    start, end = fiscal_window(fiscal_year)
    return (
        f"FISCAL YEAR {fiscal_year} "
        f"({start.strftime('%B %Y').upper()} - {end.strftime('%B %Y').upper()})"
    )


def fiscal_months(fiscal_year: int) -> list[dict]:
    """Ordered list of the 12 months (Dec..Nov) with first-of-month date + label."""
    start, _ = fiscal_window(fiscal_year)
    months = []
    curr = start
    for _ in range(12):
        months.append({'date': curr, 'label': curr.strftime('%b').upper()})
        if curr.month == 12:
            curr = curr.replace(year=curr.year + 1, month=1)
        else:
            curr = curr.replace(month=curr.month + 1)
    return months


def _month_end(first_of_month: date) -> date:
    if first_of_month.month == 12:
        return first_of_month.replace(year=first_of_month.year + 1, month=1) - timedelta(days=1)
    return first_of_month.replace(month=first_of_month.month + 1) - timedelta(days=1)


@dataclass
class ScopePerformance:
    """Live performance figures for one scope over one fiscal window."""
    won_count: int
    lost_count: int
    total_revenue: Decimal     # Sum of retail on won deals
    total_profit: Decimal      # Sum of (retail - cost) on won deals
    monthly_profit: list[Decimal]  # 12 values, Dec..Nov

    @property
    def total_closed(self) -> int:
        return self.won_count + self.lost_count

    @property
    def win_rate(self) -> float:
        return (self.won_count / self.total_closed * 100) if self.total_closed else 0.0

    @property
    def avg_deal_size(self) -> Decimal:
        return (self.total_revenue / self.won_count) if self.won_count else Decimal('0')


def compute_scope_performance(fiscal_year: int, salesperson_ids=None,
                              months_through: int | None = None) -> ScopePerformance:
    """
    Compute live won/lost performance for a fiscal year, optionally restricted to
    a set of salesperson user IDs (None = company-wide, all salespeople).

    ``months_through`` (1-12) caps the window to the first N fiscal months
    (Dec..) for a same-period year-over-year (YTD) comparison. None = full year.
    Months beyond the cap report zero profit so monthly overlays stay aligned.

    Mirrors the aggregation used by the existing group fiscal summary and
    deals_history: a deal counts in a fiscal year by its ``closed_date`` and
    excludes throwaway test entries.
    """
    from sales_funnel.models import SalesFunnel

    start, end = fiscal_window(fiscal_year)
    months = fiscal_months(fiscal_year)

    # YTD cap: shrink the end to the last day of the Nth fiscal month.
    if months_through is not None:
        n = max(1, min(12, months_through))
        end = _month_end(months[n - 1]['date'])

    base = SalesFunnel.objects.filter(
        is_closed=True,
        is_test=False,
        closed_date__gte=start,
        closed_date__lte=end,
    )
    if salesperson_ids is not None:
        base = base.filter(salesperson_id__in=list(salesperson_ids))

    won = base.filter(deal_outcome='won')
    lost = base.filter(deal_outcome='lost')

    total_revenue = won.aggregate(v=Sum('retail'))['v'] or Decimal('0')
    total_profit = won.aggregate(v=Sum(F('retail') - F('cost')))['v'] or Decimal('0')

    monthly_profit = []
    for idx, m in enumerate(months):
        if months_through is not None and idx >= months_through:
            monthly_profit.append(Decimal('0'))
            continue
        m_start = m['date']
        m_end = _month_end(m_start)
        m_profit = won.filter(
            closed_date__gte=m_start, closed_date__lte=m_end
        ).aggregate(v=Sum(F('retail') - F('cost')))['v'] or Decimal('0')
        monthly_profit.append(m_profit)

    return ScopePerformance(
        won_count=won.count(),
        lost_count=lost.count(),
        total_revenue=total_revenue,
        total_profit=total_profit,
        monthly_profit=monthly_profit,
    )


def fiscal_month_index_for_date(d: date) -> int:
    """
    1-based index (1=Dec ... 12=Nov) of the fiscal month a date falls in.
    Used to cap the live (current) fiscal year for same-period YTD comparisons.
    """
    fy = fiscal_year_for_date(d)
    for idx, m in enumerate(fiscal_months(fy), start=1):
        if m['date'] <= d <= _month_end(m['date']):
            return idx
    return 12
