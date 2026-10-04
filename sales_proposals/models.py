from django.db import models
from users.models import User
from customers.models import Customer
from django.utils import timezone
from decimal import Decimal, InvalidOperation
from django.core.validators import MinValueValidator
from pathlib import Path
import re

class Proposal(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('accepted', 'Accepted'),
        ('declined', 'Declined'),
        ('expired', 'Expired'),
    ]

    proposal_number = models.CharField(max_length=50, unique=True, editable=False)
    reference_number = models.CharField(max_length=50, blank=True, null=True, help_text="Optional manual reference number (e.g., Ref No: GGV20260523001)")
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='proposals')
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_proposals')
    date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    PRICE_VALIDITY_MODE_CHOICES = [
        ('date_only', 'Valid until selected date'),
        ('market_notice', 'Use market-condition notice'),
    ]
    STOCK_AVAILABILITY_CHOICES = [
        ('', '---------'),
        ('ON-STOCK 3 TO 5 WORKING DAYS', 'ON-STOCK 3 TO 5 WORKING DAYS'),
        ('LIMITED STOCK', 'LIMITED STOCK'),
        ('ORDER BASIS', 'ORDER BASIS'),
        ('ORDER BASIS (30 TO 45 WORKING DAYS)', 'ORDER BASIS (30 TO 45 WORKING DAYS)'),
        ('ORDER BASIS (60 TO 90 WORKING DAYS)', 'ORDER BASIS (60 TO 90 WORKING DAYS)'),
        ('ORDER BASIS (90 TO 120 WORKING DAYS)', 'ORDER BASIS (90 TO 120 WORKING DAYS)'),
        ('ORDER BASIS (7 TO 10 WORKING DAYS)', 'ORDER BASIS (7 TO 10 WORKING DAYS)'),
        ('CONFIG TO ORDER (30 TO 45 WORKING DAYS)', 'CONFIG TO ORDER (30 TO 45 WORKING DAYS)'),
        ('CONFIG TO ORDER (60 TO 90 WORKING DAYS)', 'CONFIG TO ORDER (60 TO 90 WORKING DAYS)'),
        ('CONFIG TO ORDER (90 TO 120 WORKING DAYS)', 'CONFIG TO ORDER (90 TO 120 WORKING DAYS)'),
    ]
    price_validity_mode = models.CharField(max_length=20, choices=PRICE_VALIDITY_MODE_CHOICES, default='date_only')
    stock_availability = models.CharField(max_length=80, choices=STOCK_AVAILABILITY_CHOICES, blank=True, default='')
    subject = models.CharField(max_length=200)
    # Attention contact snapshot
    contact_name = models.CharField(max_length=120, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)
    
    # Currency
    CURRENCY_CHOICES = [
        ('PHP', 'PHP - Philippine Peso'),
        ('USD', 'USD - US Dollar'),
    ]
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='PHP')
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=2, default=1.00, help_text="Exchange rate to PHP (1.0 for PHP)")

    # Terms
    payment_terms = models.TextField(default="30 days", help_text="e.g., 30 days, Cash on Delivery")
    delivery_lead_time = models.CharField(max_length=200, default="Within three (3) to seven (7) working days once the stock arrived.", help_text="e.g., 3-7 working days once the stock arrived")
    warranty = models.CharField(max_length=200, default="1 year - Parts Warranty", help_text="e.g., 1 year - Parts Warranty")

    # Cancellation terms — always uses the short & polite wording; no user selection needed.
    cancellation_terms = models.CharField(max_length=20, default='polite', editable=False)
    
    # Content
    special_note = models.TextField(help_text="Optional special note (e.g. SUBJECT PRICE CHANGE...)", blank=True)
    introduction = models.TextField(help_text="Opening text of the proposal", blank=True)
    closing = models.TextField(help_text="Terms and conditions or closing text", blank=True)
    
    # Optional Fields
    include_bank_details = models.BooleanField(default=False, help_text="Include bank details in the proposal PDF")
    show_discount = models.BooleanField(default=False, help_text="Show discount line in the proposal PDF")
    show_vat = models.BooleanField(default=False, help_text="Show VAT 12% line in the proposal (most proposals exclude VAT)")
    use_availability_column = models.BooleanField(
        default=True,
        help_text="Show 'Availability' column in the proposal (uncheck to show 'Warranty' column instead)"
    )
    use_total_price_label = models.BooleanField(default=False, help_text="Use 'Total Price' instead of 'Extended Price' as column header in PDF and detail view")
    hide_part_number = models.BooleanField(
        default=False,
        help_text="Hide the 'Part No.' column in the proposal PDF and detail view; the freed space is given to the Description column. Use for proposals that don't quote part numbers."
    )
    discount_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Manual discount amount (informational; does not change totals).",
    )
    
    # Bank details (per-currency, editable per proposal)
    # PHP — BDO
    php_bank_name = models.CharField(max_length=200, default="Banco De Oro")
    php_account_name = models.CharField(max_length=200, default="MICRO IMAGE INTERNATIONAL CORPORATION")
    php_account_number = models.CharField(max_length=100, default="00204-0042969 (SAVINGS)")
    php_account_type = models.CharField(max_length=200, default="Savings Account")
    php_branch = models.CharField(max_length=200, default="SALCEDO-DELA ROSA")
    php_bank_address = models.CharField(max_length=300, default="Golden Rock Bldg, 168 Salcedo, Legaspi Village, Makati, 1229 Metro Manila")
    php_swift_code = models.CharField(max_length=50, default="BNORPHMM")
    php_branch_code = models.CharField(max_length=20, default="00204")
    # PHP — BPI
    php_bpi_account_name = models.CharField(max_length=200, default="MICRO IMAGE INTERNATIONAL CORPORATION")
    php_bpi_account_number = models.CharField(max_length=100, default="0075-336527 (CURRENT)")
    php_bpi_account_type = models.CharField(max_length=200, default="Current Account")
    php_bpi_branch = models.CharField(max_length=200, default="LEGASPI-SALCEDO")
    php_bpi_bank_address = models.CharField(max_length=300, default="Golden Rock Bldg, 168 Salcedo, Legaspi Village, Makati, 1229 Metro Manila")
    php_bpi_swift_code = models.CharField(max_length=50, default="BOPIPHMMXXX")
    # USD — BDO
    usd_beneficiary_name = models.CharField(max_length=200, default="MICRO IMAGE INTERNATIONAL CORPORATION")
    usd_beneficiary_address = models.CharField(max_length=300, default="Unit 53 & 101 Legaspi Suites Building, 178 Salcedo St., Legaspi Village, Makati City 1229")
    usd_account_number = models.CharField(max_length=100, default="10204-0146004")
    usd_bank_name = models.CharField(max_length=200, default="Banco De Oro")
    usd_bank_address = models.CharField(max_length=300, default="Golden Rock Bldg, 168 Salcedo, Legaspi Village, Makati, 1229 Metro Manila")
    usd_swift_code = models.CharField(max_length=50, default="BNORPHMMXXX")
    usd_branch_code = models.CharField(max_length=20, default="10204")
    
    # Price Validity options
    validity_subject_to_prior_sale = models.BooleanField(default=False)
    validity_availability_at_order = models.BooleanField(default=False)

    # Multi-Option Proposal
    is_multi_option = models.BooleanField(
        default=False,
        help_text='Enable multi-option format (OPTION 1, OPTION 2, etc.) with separate item tables per option'
    )
    
    # Financials
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    TAX_TYPE_CHOICES = [
        ('VAT', 'VAT (12%)'),
        ('ZERO', 'Zero-Rated (0%)'),
        ('EXEMPT', 'VAT-Exempt (0%)'),
    ]
    tax_type = models.CharField(max_length=10, choices=TAX_TYPE_CHOICES, default='VAT')
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('12.00'), help_text="Tax rate in percentage (e.g. 12 for 12%)")
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Costing (Internal)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Total cost of all items")
    gross_profit = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Total Amount - Total Cost")
    sales_margin_pct = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        default=Decimal('0.00'),
        validators=[MinValueValidator(Decimal('0.00'))],
        help_text="Internal total-level salesperson margin percentage.",
    )
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    
    APPROVAL_STATUS_CHOICES = [
        ('not_required', 'Not Required'),
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    approval_status = models.CharField(max_length=20, choices=APPROVAL_STATUS_CHOICES, default='not_required')
    approval_required = models.BooleanField(default=False)
    approval_submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approval_total_php = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    approval_version = models.IntegerField(default=0)
    
    # Marks a throwaway test/scratch proposal. Test proposals produce a TEST
    # funnel entry (see update_sales_funnel) so the whole chain can be safely
    # deleted later without touching real pipeline.
    is_test = models.BooleanField(
        default=False,
        help_text="Marks a test/scratch proposal. Its funnel entry becomes deletable."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        if not self.proposal_number:
            today = timezone.now()
            year = today.year

            user = getattr(self, 'created_by', None)
            initials = (getattr(user, 'initials', None) or '').upper()
            if not initials:
                parts = [getattr(user, 'first_name', ''), getattr(user, 'last_name', '')]
                initials = ''.join((p[:1] or '').upper() for p in parts)
            if not initials:
                initials = (getattr(user, 'username', '') or '').upper()
            initials = (initials[:3] if initials else 'XXX').ljust(3, 'X')

            existing = Proposal.objects.filter(proposal_number__contains=f"-{year}-").values_list('proposal_number', flat=True)
            max_seq = 0
            pattern = re.compile(r"^(?P<prefix>[^-]+)-(?P<year>\d{4})-(?P<seq>\d+)$")
            for num in existing:
                m = pattern.match(num or '')
                if not m:
                    continue
                if int(m.group('year')) != year:
                    continue
                try:
                    seq = int(m.group('seq'))
                except Exception:
                    continue
                if seq > max_seq:
                    max_seq = seq

            next_seq = max_seq + 1
            candidate = f"{initials}-{year}-{next_seq:04d}"
            while Proposal.objects.filter(proposal_number=candidate).exists():
                next_seq += 1
                candidate = f"{initials}-{year}-{next_seq:04d}"
            self.proposal_number = candidate
        # Autogenerate Reference Number: III + YYYYMMDD + ### (per-salesperson sequence)
        if not self.reference_number and self.created_by_id:
            # Initials
            initials = (self.created_by.initials or "").upper()
            if not initials:
                parts = [self.created_by.first_name, self.created_by.last_name]
                initials = "".join((p[:1] or "").upper() for p in parts)[:3].ljust(3, "X")
            elif len(initials) < 3:
                initials = initials.ljust(3, "X")
            # Date string from proposal date
            date_obj = self.date or timezone.now().date()
            date_str = date_obj.strftime("%Y%m%d")
            # Sequence per salesperson
            seq = Proposal.objects.filter(created_by_id=self.created_by_id).count() + 1
            ref = f"{initials}{date_str}{seq:03d}"
            # Ensure uniqueness in rare race conditions
            while Proposal.objects.filter(reference_number=ref).exists():
                seq += 1
                ref = f"{initials}{date_str}{seq:03d}"
            self.reference_number = ref
        super().save(*args, **kwargs)
    
    def calculate_totals(self):
        priced_items = self.items.filter(is_optional=False)
        self.subtotal = sum(item.amount for item in priced_items)
        self.total_cost = sum(item.total_cost for item in priced_items)

        discount = self.effective_discount_amount
        discounted_subtotal = self.subtotal - discount
        discounted_subtotal = discounted_subtotal if discounted_subtotal > 0 else Decimal('0.00')

        # VAT: only applied when show_vat is enabled (12% on discounted subtotal)
        if self.show_vat:
            self.tax_type = 'VAT'
            self.tax_rate = Decimal('12.00')
            self.tax_amount = (discounted_subtotal * Decimal('0.12')).quantize(Decimal('0.01'))
        else:
            self.tax_type = 'ZERO'
            self.tax_rate = Decimal('0.00')
            self.tax_amount = Decimal('0.00')

        self.total_amount = discounted_subtotal + self.tax_amount

        # Gross profit is Total Revenue (excl tax if we consider net sales, but typically GP is Sales - COGS)
        self.gross_profit = self.total_amount - self.internal_cost_with_uplift
        php_total = self.total_amount
        if self.currency == 'USD':
            rate = self.exchange_rate if self.exchange_rate > 0 else Decimal('1.0')
            php_total = self.total_amount * rate
        self.approval_total_php = php_total
        need = php_total >= Decimal('500000')
        self.approval_required = need
        if need and self.approval_status in ['not_required', 'approved', 'rejected']:
            self.approval_status = 'pending'
            self.approval_version = self.approval_version + 1
        self.save()

    @property
    def internal_cost_with_uplift(self):
        return self.total_cost * Decimal('1.05')

    @property
    def target_subtotal_before_tax(self):
        uplifted_cost = self.internal_cost_with_uplift
        return uplifted_cost * (Decimal('1.00') + ((self.sales_margin_pct or Decimal('0.00')) / Decimal('100.00')))

    @property
    def target_gross_profit(self):
        return self.target_subtotal_before_tax - self.total_cost

    @property
    def has_optional_items(self):
        return self.items.filter(is_optional=True).exists()

    @property
    def effective_discount_amount(self):
        if self.show_discount and (self.discount_amount or 0) > 0:
            return self.discount_amount
        return Decimal('0.00')

    @property
    def quoted_subtotal(self):
        return sum(item.amount for item in self.items.all())

    @property
    def quoted_total_cost(self):
        return sum(item.total_cost for item in self.items.all())

    @property
    def quoted_total_amount(self):
        discounted_total = self.quoted_subtotal - self.effective_discount_amount
        return discounted_total if discounted_total > 0 else Decimal('0.00')

    @property
    def quoted_gross_profit(self):
        return self.quoted_total_amount - (self.quoted_total_cost * Decimal('1.05'))

    @property
    def quoted_amount_php(self):
        if self.currency == 'USD':
            rate = self.exchange_rate if self.exchange_rate > 0 else Decimal('1.0')
            return self.quoted_total_amount * rate
        return self.quoted_total_amount

    @property
    def quoted_cost_php(self):
        if self.currency == 'USD':
            rate = self.exchange_rate if self.exchange_rate > 0 else Decimal('1.0')
            return self.quoted_total_cost * rate
        return self.quoted_total_cost

    @property
    def has_line_items(self):
        """True if the proposal has at least one line item (single or multi-option)."""
        return self.items.exists()

    @property
    def can_be_emailed(self):
        """
        A proposal may only be emailed to a customer when it has line items
        and (if approval is required) it has been approved.
        """
        if not self.has_line_items:
            return False
        if self.approval_required and self.approval_status != 'approved':
            return False
        return True

    def get_approval_chain(self):
        chain = []
        php_total = self.approval_total_php or 0
        creator = self.created_by
        group = None
        # 1. Try standard TeamMembership (works for salespeople)
        try:
            if hasattr(creator, 'team_membership'):
                group = creator.team_membership.group
        except Exception:
            group = None
        # 2. Fallback for SM: they're linked via Group.sm_managers M2M, not TeamMembership
        if not group and creator.role == 'sm':
            try:
                group = creator.sm_groups.select_related('team').first()
            except Exception:
                group = None
        # 3. Fallback for ASM: linked via Team.asm FK
        if not group and creator.role == 'asm':
            try:
                from teams.models import Team
                team = Team.objects.filter(asm=creator).first()
                if team:
                    group = team.groups.first()
            except Exception:
                group = None
        # 4. Fallback for Supervisor: linked via Group.supervisor FK
        if not group and creator.role == 'supervisor':
            try:
                group = creator.managed_groups.select_related('team').first()
            except Exception:
                group = None
        supervisor = None
        asm = None
        avp_or_gm = None
        if group:
            try:
                supervisor = group.get_manager()
            except Exception:
                supervisor = None
            # Resolve SM/ASM: only include SM in the chain if the group
            # explicitly requires SM approval (requires_sm_approval flag).
            # This separates visibility (sm_managers M2M) from approval authority.
            try:
                if getattr(group, 'requires_sm_approval', False):
                    sm_for_group = group.sm_managers.first()
                    if sm_for_group:
                        asm = sm_for_group
                    elif group.team and group.team.asm:
                        asm = group.team.asm
                else:
                    asm = None  # 2-level: skip SM, go straight to AVP
            except Exception:
                asm = None
            try:
                avp_or_gm = group.team.avp if group.team else None
            except Exception:
                avp_or_gm = None
        try:
            tier = ProposalApprovalTier.objects.filter(active=True, min_amount_php__lte=php_total).filter(models.Q(max_amount_php__isnull=True) | models.Q(max_amount_php__gte=php_total)).order_by('order', 'min_amount_php').first()
        except Exception:
            tier = None

        # Role authority level — approvers at or below the creator's level are skipped.
        # Higher number = higher authority.
        ROLE_LEVEL = {
            'salesperson': 1,
            'teamlead': 2,
            'supervisor': 3,
            'asm': 4,
            'sm': 4,
            'avp': 5,
            'vp': 6,
            'gm': 6,
            'president': 7,
            'admin': 7,
        }
        creator_level = ROLE_LEVEL.get(creator.role, 0)

        def _approver_outranks_creator(approver):
            """Only include an approver if their role level is above the creator's."""
            if not approver:
                return False
            return ROLE_LEVEL.get(approver.role, 0) > creator_level

        if tier:
            parts = [p.strip() for p in (tier.chain or '').split(',') if p.strip()]
            for role in parts:
                if role == 'supervisor' and supervisor and supervisor != creator and supervisor not in chain and _approver_outranks_creator(supervisor):
                    chain.append(supervisor)
                elif role == 'asm' and asm and asm != creator and asm not in chain and _approver_outranks_creator(asm):
                    chain.append(asm)
                elif role in ['avp_or_gm', 'avp', 'gm'] and avp_or_gm and avp_or_gm != creator and avp_or_gm not in chain and _approver_outranks_creator(avp_or_gm):
                    chain.append(avp_or_gm)
        else:
            # Single threshold: ≥ ₱500,000 triggers approval.
            # Chain: Supervisor → SM (if group requires it) → AVP
            if php_total >= Decimal('500000'):
                if supervisor and supervisor != creator and _approver_outranks_creator(supervisor):
                    chain.append(supervisor)
                if asm and asm != creator and asm not in chain and _approver_outranks_creator(asm):
                    chain.append(asm)
                if avp_or_gm and avp_or_gm != creator and avp_or_gm not in chain and _approver_outranks_creator(avp_or_gm):
                    chain.append(avp_or_gm)

        # Escalation: if approval is required but all lower-tier approvers were skipped
        # (creator outranks them), escalate to the next higher authority.
        if not chain and self.approval_required:
            if avp_or_gm and avp_or_gm != creator and _approver_outranks_creator(avp_or_gm):
                chain.append(avp_or_gm)

        return [u for u in chain if u]

    def ensure_approval_chain(self):
        from django.db import transaction
        with transaction.atomic():
            steps = list(self.approval_steps.order_by('level'))
            if not self.approval_required:
                if steps:
                    self.approval_steps.all().delete()
                fields_to_update = []
                if self.approval_status != 'not_required':
                    self.approval_status = 'not_required'
                    fields_to_update.append('approval_status')
                if self.approval_submitted_at is not None:
                    self.approval_submitted_at = None
                    fields_to_update.append('approval_submitted_at')
                if self.approved_at is not None:
                    self.approved_at = None
                    fields_to_update.append('approved_at')
                if fields_to_update:
                    self.save(update_fields=fields_to_update)
                return

            chain = self.get_approval_chain()
            expected_ids = [user.id for user in chain if user]
            existing_ids = [step.approver_id for step in steps]
            has_decisions = any(step.status in ['approved', 'rejected'] for step in steps)
            chain_changed = expected_ids != existing_ids

            # Safest behavior: if the approver chain changes or any approver already acted,
            # restart the workflow so stale approvals do not remain attached to edited content.
            if steps and (chain_changed or has_decisions):
                self.approval_steps.all().delete()
                steps = []
                self.approval_status = 'pending'
                self.approved_at = None
                self.approval_submitted_at = None
                self.approval_version = self.approval_version + 1
                self.save(update_fields=[
                    'approval_status',
                    'approved_at',
                    'approval_submitted_at',
                    'approval_version',
                ])

            if not steps:
                for idx, user in enumerate(chain, start=1):
                    ProposalApprovalStep.objects.create(proposal=self, level=idx, approver=user, status='pending')
                if chain:
                    self.approval_status = 'in_progress'
                    self.approval_submitted_at = timezone.now()
                    self.approved_at = None
                    self.save(update_fields=['approval_status', 'approval_submitted_at', 'approved_at'])

    def get_current_pending_step(self):
        return self.approval_steps.filter(status='pending').order_by('level', 'created_at').first()

    def can_user_decide_current_step(self, user):
        if not user or not getattr(user, 'is_authenticated', False):
            return False
        current_step = self.get_current_pending_step()
        return bool(current_step and current_step.approver_id == user.id)

    def __str__(self):
        return f"{self.proposal_number} - {self.customer.company_name}"

    class Meta:
        ordering = ['-created_at']


class ProposalOptionGroup(models.Model):
    """
    Groups items under a named option (OPTION 1, OPTION 2, etc.) for multi-option proposals.
    Only used when Proposal.is_multi_option=True.
    """
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='option_groups')
    name = models.CharField(max_length=100, default='OPTION 1', help_text='Display name for this option group')
    sort_order = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, help_text='Optional notes for this option group')

    class Meta:
        ordering = ['sort_order', 'id']

    def __str__(self):
        return f"{self.name} — {self.proposal.proposal_number}"

    @property
    def subtotal(self):
        return sum(item.amount for item in self.group_items.all())

    @property
    def total_cost(self):
        return sum(item.total_cost for item in self.group_items.all())

    @property
    def profit(self):
        return self.subtotal - self.total_cost


class ProposalItem(models.Model):
    # Shared max length for the Availability / Warranty text so the value can move
    # freely between the two columns without overflowing, and so MySQL (which
    # strictly enforces VARCHAR length, unlike SQLite) accepts every row.
    AVAILABILITY_WARRANTY_MAX_LENGTH = 150

    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='items')
    option_group = models.ForeignKey(
        ProposalOptionGroup, on_delete=models.CASCADE,
        related_name='group_items', null=True, blank=True,
        help_text='Only set for multi-option proposals'
    )
    part_number = models.CharField(max_length=100, blank=True, help_text="Product Part Number")
    description = models.TextField(help_text="Item description and specifications")
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, help_text="Internal")
    availability = models.CharField(max_length=AVAILABILITY_WARRANTY_MAX_LENGTH, blank=True, help_text="Product availability (e.g. In Stock, 2-3 weeks)")
    warranty = models.CharField(max_length=AVAILABILITY_WARRANTY_MAX_LENGTH, blank=True, help_text="Per-item warranty (e.g., 1 year parts/labor)")
    is_optional = models.BooleanField(default=False, help_text="Mark this line as optional so it is excluded from the proposal total")
    is_bundle = models.BooleanField(default=False, help_text="Show bundled component part numbers under this priced item")
    bundled_items = models.TextField(blank=True, help_text="One bundled component per line. Format: PART NUMBER | Description | Qty")
    margin_pct = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True, help_text="Stored margin percentage for display consistency")
    amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    total_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)

    @staticmethod
    def _split_bundle_line(raw_line):
        line = (raw_line or '').strip()
        if not line:
            return None

        for delimiter in ('\t', '|'):
            if delimiter in line:
                parts = [p.strip() for p in line.split(delimiter)]
                # 5 columns: Part Number | Description | Qty | Unit Price | Total Price
                # 4 columns: Part Number | Description | Qty | Unit Price
                # 3 columns: Part Number | Description | Qty
                # In all cases we take the first 3 columns and ignore pricing columns.
                if len(parts) >= 5:
                    part_number = parts[0]
                    description = parts[1]
                    qty_raw = parts[2]
                    qty = None
                    if qty_raw:
                        try:
                            qty = Decimal(str(qty_raw).replace(',', '').strip())
                        except (InvalidOperation, TypeError):
                            qty = None
                    return {
                        'part_number': part_number.strip(),
                        'description': description.strip(),
                        'quantity': qty,
                    }
                if len(parts) == 4:
                    part_number = parts[0]
                    description = parts[1]
                    qty_raw = parts[2]
                    qty = None
                    if qty_raw:
                        try:
                            qty = Decimal(str(qty_raw).replace(',', '').strip())
                        except (InvalidOperation, TypeError):
                            qty = None
                    return {
                        'part_number': part_number.strip(),
                        'description': description.strip(),
                        'quantity': qty,
                    }
                if len(parts) == 3:
                    part_number = parts[0]
                    description = parts[1]
                    qty_raw = parts[2]
                    qty = None
                    if qty_raw:
                        try:
                            qty = Decimal(str(qty_raw).replace(',', '').strip())
                        except (InvalidOperation, TypeError):
                            qty = None
                    return {
                        'part_number': part_number.strip(),
                        'description': description.strip(),
                        'quantity': qty,
                    }
                if len(parts) == 2:
                    part_number, description = parts
                    return {
                        'part_number': part_number.strip(),
                        'description': description.strip(),
                        'quantity': None,
                    }

        for delimiter in (' - ', ' – ', ' — '):
            if delimiter in line:
                part_number, description = line.split(delimiter, 1)
                return {
                    'part_number': part_number.strip(),
                    'description': description.strip(),
                    'quantity': None,
                }

        if ' ' not in line:
            return {
                'part_number': line,
                'description': '',
                'quantity': None,
            }

        return {
            'part_number': '',
            'description': line,
            'quantity': None,
        }

    @property
    def bundle_components(self):
        if not self.bundled_items:
            return []

        components = []
        for raw_line in self.bundled_items.splitlines():
            component = self._split_bundle_line(raw_line)
            if component:
                components.append(component)
        return components

    @property
    def has_bundle_components(self):
        return bool(self.is_bundle and self.bundle_components)

    @property
    def optional_option_number(self):
        if not self.is_optional or not self.proposal_id or not self.pk:
            return None
        return (
            self.proposal.items
            .filter(is_optional=True, pk__lte=self.pk)
            .order_by('pk')
            .count()
        )

    def save(self, *args, **kwargs):
        if not self.is_bundle:
            self.bundled_items = ''
        self.amount = self.quantity * self.unit_price
        self.total_cost = self.quantity * self.unit_cost
        # Final safety net: hard-cap Availability/Warranty length on EVERY save path
        # (form, multi-option JSON, API, admin, shell) so a value can never exceed the
        # DB column. SQLite ignores VARCHAR length but MySQL enforces it strictly.
        limit = self.AVAILABILITY_WARRANTY_MAX_LENGTH
        if self.availability and len(self.availability) > limit:
            self.availability = self.availability[:limit]
        if self.warranty and len(self.warranty) > limit:
            self.warranty = self.warranty[:limit]
        super().save(*args, **kwargs)

class ProposalAttachment(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='proposal_attachments/')
    display_name = models.CharField(max_length=200, blank=True)
    include_in_email = models.BooleanField(default=False)
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    @property
    def base_filename(self):
        if not self.file:
            return ''
        return Path(self.file.name).name

    @property
    def file_stem(self):
        if not self.file:
            return ''
        return Path(self.base_filename).stem

    @staticmethod
    def _is_costing_matrix_name(value):
        normalized = (value or '').strip().lower()
        return bool(re.search(r'costing[\s\-_]*matrix', normalized))

    @property
    def is_costing_matrix(self):
        return self._is_costing_matrix_name(self.file_stem)

    @property
    def can_include_in_email(self):
        return bool(self.file and not self.is_costing_matrix)

    def save(self, *args, **kwargs):
        if self.is_costing_matrix:
            self.include_in_email = False
        super().save(*args, **kwargs)

    def __str__(self):
        return self.display_name or (self.file.name.split('/')[-1] if self.file else 'Attachment')

class ProposalChangeLog(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='change_logs')
    changed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    changed_at = models.DateTimeField(auto_now_add=True)
    summary = models.TextField(blank=True)
    details = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ['-changed_at']

class ProposalApprovalTier(models.Model):
    name = models.CharField(max_length=100, blank=True)
    min_amount_php = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    max_amount_php = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    chain = models.CharField(max_length=200, help_text="Comma-separated roles: supervisor,asm,avp_or_gm")
    order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'min_amount_php']

    def __str__(self):
        return self.name or f"{self.min_amount_php} - {self.max_amount_php or '∞'}"

class ProposalApprovalStep(models.Model):
    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='approval_steps')
    level = models.PositiveIntegerField()
    approver = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='proposal_approvals')
    status = models.CharField(
        max_length=20,
        choices=[
            ('pending', 'Pending'),
            ('approved', 'Approved'),
            ('rejected', 'Rejected'),
            # Set on the downstream steps when an earlier approver rejects, so a
            # later approver cannot act on (and un-reject) a dead chain.
            ('cancelled', 'Cancelled'),
        ],
        default='pending',
    )
    decided_at = models.DateTimeField(null=True, blank=True)
    comment = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['level', 'created_at']
        unique_together = ('proposal', 'level')


class ProposalEmailLog(models.Model):
    """Tracks every email send attempt for a proposal — success or failure."""
    STATUS_CHOICES = [
        ('sent', 'Sent'),
        ('failed', 'Failed'),
    ]

    proposal = models.ForeignKey(Proposal, on_delete=models.CASCADE, related_name='email_logs')
    sent_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='proposal_emails_sent')
    recipients = models.TextField(help_text='Comma-separated To addresses')
    cc = models.TextField(blank=True, help_text='Comma-separated CC addresses')
    status = models.CharField(max_length=10, choices=STATUS_CHOICES)
    error_message = models.TextField(blank=True, help_text='Error details if send failed')
    sent_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-sent_at']
        verbose_name = 'Proposal Email Log'
        verbose_name_plural = 'Proposal Email Logs'

    def __str__(self):
        return f"{self.proposal.proposal_number} → {self.recipients} [{self.status}]"
